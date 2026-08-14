"""Extrai emendas autorizadas para Barreiras dos anexos estaduais preservados."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from barreiras_collectors.logging import log_event
from barreiras_collectors.persistence.storage import SupabaseStorageObjectStore
from barreiras_collectors.settings import CollectorSettings, PersistenceSettings

from ..bahia_state_loa import LoaParseError
from ..bahia_state_loa_processing import (
    BahiaStateLoaArtifact,
    BahiaStateLoaExtractionService,
    BahiaStateLoaPersistResult,
    LoaArtifactMismatchError,
    LoaIncompleteTextError,
    loa_job_idempotency_key,
)
from ..bahia_state_loa_repository import BahiaStateLoaExtractionRepository
from ..canonical import CanonicalTextError


@dataclass(frozen=True)
class LoaBatchSummary:
    pending_found: int
    processed: int
    failed: int
    jobs_created: int
    results_inserted: int
    scope_rows_inserted: int


class PendingRepository(Protocol):
    def pending_artifacts(self, limit: int) -> tuple[BahiaStateLoaArtifact, ...]: ...

    def persist_failure(
        self,
        artifact: BahiaStateLoaArtifact,
        *,
        idempotency_key: str,
        error_code: str,
        error_detail: str,
    ) -> None: ...


class ProcessingService(Protocol):
    def process(
        self,
        artifact: BahiaStateLoaArtifact,
    ) -> BahiaStateLoaPersistResult: ...


def _error_code(error: Exception) -> str:
    if isinstance(error, LoaArtifactMismatchError):
        return "artifact_mismatch"
    if isinstance(error, LoaIncompleteTextError):
        return "incomplete_text"
    if isinstance(error, LoaParseError):
        return "parser_contract"
    if isinstance(error, CanonicalTextError):
        return "unreadable_document"
    return "processing_error"


def run_batch(
    *,
    repository: PendingRepository,
    service: ProcessingService,
    limit: int,
    logger: logging.Logger | None = None,
) -> LoaBatchSummary:
    log = logger or logging.getLogger(__name__)
    pending = repository.pending_artifacts(limit)
    processed = 0
    failed = 0
    jobs_created = 0
    results_inserted = 0
    scope_rows_inserted = 0
    for artifact in pending:
        try:
            result = service.process(artifact)
        except Exception as error:
            failed += 1
            code = _error_code(error)
            detail = (
                f"{type(error).__name__}: {error}"
                if code != "processing_error"
                else f"{type(error).__name__}: unexpected processing failure"
            )
            try:
                repository.persist_failure(
                    artifact,
                    idempotency_key=loa_job_idempotency_key(artifact.sha256),
                    error_code=code,
                    error_detail=detail,
                )
            except Exception:
                log.debug("loa_failure_persistence_failed", exc_info=True)
            log_event(
                log,
                logging.ERROR,
                "docproc_bahia_state_loa_failed",
                source="bahia-seplan-budget",
                fiscal_year=artifact.fiscal_year,
                artifact_hash=artifact.sha256,
                error_code=code,
                error_type=type(error).__name__,
            )
            continue

        processed += 1
        jobs_created += int(result.job_created)
        results_inserted += result.results_inserted
        scope_rows_inserted += result.scope_rows_inserted
        log_event(
            log,
            logging.INFO,
            "docproc_bahia_state_loa_processed",
            source="bahia-seplan-budget",
            fiscal_year=artifact.fiscal_year,
            artifact_hash=artifact.sha256,
            job_created=result.job_created,
            authorized_amendments=result.results_inserted,
            statewide_scope_rows=result.scope_rows_inserted,
        )

    summary = LoaBatchSummary(
        pending_found=len(pending),
        processed=processed,
        failed=failed,
        jobs_created=jobs_created,
        results_inserted=results_inserted,
        scope_rows_inserted=scope_rows_inserted,
    )
    log_event(
        log,
        logging.INFO,
        "docproc_bahia_state_loa_batch_completed",
        source="bahia-seplan-budget",
        pending_found=summary.pending_found,
        processed=summary.processed,
        failed=summary.failed,
        jobs_created=summary.jobs_created,
        authorized_amendments=summary.results_inserted,
        statewide_scope_rows=summary.scope_rows_inserted,
    )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Extrai deterministicamente valores autorizados para Barreiras "
            "dos anexos oficiais da LOA da Bahia."
        )
    )
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 50:
        parser.error("--limit deve estar entre 1 e 50.")

    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    if persistence_settings.mode != "postgres-supabase":
        raise RuntimeError(
            "O processamento da LOA requer PERSISTENCE_MODE=postgres-supabase."
        )
    if (
        persistence_settings.database_url is None
        or persistence_settings.supabase_url is None
        or persistence_settings.supabase_publishable_key is None
        or persistence_settings.supabase_workload_email is None
        or persistence_settings.supabase_workload_password is None
        or persistence_settings.raw_artifacts_bucket is None
    ):
        raise RuntimeError("Configuracao de nuvem incompleta.")
    try:
        from supabase import create_client
    except ImportError as error:
        raise RuntimeError(
            "Instale as dependencias opcionais 'storage' e 'pdf'."
        ) from error

    client = create_client(
        persistence_settings.supabase_url,
        persistence_settings.supabase_publishable_key,
    )
    try:
        authentication = client.auth.sign_in_with_password(
            {
                "email": persistence_settings.supabase_workload_email,
                "password": persistence_settings.supabase_workload_password,
            }
        )
    except Exception as error:
        raise RuntimeError(
            "Falha ao autenticar a identidade tecnica do Storage."
        ) from error
    if authentication.session is None or authentication.user is None:
        raise RuntimeError("O Storage nao forneceu uma sessao autenticada.")

    repository = BahiaStateLoaExtractionRepository.from_dsn(
        persistence_settings.database_url
    )
    service = BahiaStateLoaExtractionService(
        object_reader=SupabaseStorageObjectStore(
            client.storage.from_(persistence_settings.raw_artifacts_bucket)
        ),
        repository=repository,
    )
    summary = run_batch(
        repository=repository,
        service=service,
        limit=args.limit,
    )
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
