"""Normaliza pagamentos estaduais cujo objeto menciona Barreiras."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from barreiras_collectors.logging import log_event
from barreiras_collectors.persistence.storage import SupabaseStorageObjectStore
from barreiras_collectors.settings import CollectorSettings, PersistenceSettings

from ..bahia_special_transfer_processing import (
    SpecialTransferArtifact,
    SpecialTransferArtifactMismatchError,
    SpecialTransferExtractionService,
    SpecialTransferPersistResult,
    special_transfer_job_idempotency_key,
)
from ..bahia_special_transfer_repository import BahiaSpecialTransferRepository
from ..bahia_special_transfers import SpecialTransferNormalizationError


@dataclass(frozen=True)
class SpecialTransferBatchSummary:
    pending_found: int
    processed: int
    failed: int
    jobs_created: int
    results_inserted: int


class PendingRepository(Protocol):
    def pending_artifacts(self, limit: int) -> tuple[SpecialTransferArtifact, ...]: ...

    def persist_failure(
        self,
        artifact: SpecialTransferArtifact,
        *,
        idempotency_key: str,
        error_code: str,
        error_detail: str,
    ) -> None: ...


class ProcessingService(Protocol):
    def process(
        self,
        artifact: SpecialTransferArtifact,
    ) -> SpecialTransferPersistResult: ...


def _error_code(error: Exception) -> str:
    if isinstance(error, SpecialTransferArtifactMismatchError):
        return "artifact_mismatch"
    if isinstance(error, SpecialTransferNormalizationError):
        return "parser_contract"
    return "processing_error"


def _error_detail(error: Exception, code: str) -> str:
    safe_messages = {
        "artifact_mismatch": "bytes restaurados divergem do hash coletado",
        "parser_contract": "estrutura oficial incompatível com o parser seguro",
    }
    return f"{type(error).__name__}: {safe_messages.get(code, 'falha inesperada')}"


def run_batch(
    *,
    repository: PendingRepository,
    service: ProcessingService,
    limit: int,
    logger: logging.Logger | None = None,
) -> SpecialTransferBatchSummary:
    log = logger or logging.getLogger(__name__)
    pending = repository.pending_artifacts(limit)
    processed = 0
    failed = 0
    jobs_created = 0
    results_inserted = 0
    for artifact in pending:
        try:
            result = service.process(artifact)
        except Exception as error:
            failed += 1
            code = _error_code(error)
            detail = _error_detail(error, code)
            try:
                repository.persist_failure(
                    artifact,
                    idempotency_key=special_transfer_job_idempotency_key(
                        artifact.sha256
                    ),
                    error_code=code,
                    error_detail=detail,
                )
            except Exception:
                log.debug(
                    "special_transfer_failure_persistence_failed",
                    exc_info=True,
                )
            log_event(
                log,
                logging.ERROR,
                "normalization_bahia_special_transfers_failed",
                source="bahia-open-data",
                artifact_hash=artifact.sha256,
                error_code=code,
                error_type=type(error).__name__,
            )
            continue

        processed += 1
        jobs_created += int(result.job_created)
        results_inserted += result.results_inserted
        log_event(
            log,
            logging.INFO,
            "normalization_bahia_special_transfers_processed",
            source="bahia-open-data",
            artifact_hash=artifact.sha256,
            job_created=result.job_created,
            territorial_candidate_rows=result.results_inserted,
        )

    summary = SpecialTransferBatchSummary(
        pending_found=len(pending),
        processed=processed,
        failed=failed,
        jobs_created=jobs_created,
        results_inserted=results_inserted,
    )
    log_event(
        log,
        logging.INFO,
        "normalization_bahia_special_transfers_batch_completed",
        source="bahia-open-data",
        pending_found=summary.pending_found,
        processed=summary.processed,
        failed=summary.failed,
        jobs_created=summary.jobs_created,
        territorial_candidate_rows=summary.results_inserted,
        public_projection="blocked_pending_author_reconciliation",
    )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Normaliza pagamentos estaduais cujo objeto menciona Barreiras, "
            "sem expor credor ou identificador pessoal."
        )
    )
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 10:
        parser.error("--limit deve estar entre 1 e 10.")

    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    if persistence_settings.mode != "postgres-supabase":
        raise RuntimeError(
            "A normalização estadual requer PERSISTENCE_MODE=postgres-supabase."
        )
    if (
        persistence_settings.database_url is None
        or persistence_settings.supabase_url is None
        or persistence_settings.supabase_publishable_key is None
        or persistence_settings.supabase_workload_email is None
        or persistence_settings.supabase_workload_password is None
        or persistence_settings.raw_artifacts_bucket is None
    ):
        raise RuntimeError("Configuração de nuvem incompleta.")
    try:
        from supabase import create_client
    except ImportError as error:
        raise RuntimeError(
            "Instale as dependências opcionais 'postgres' e 'storage'."
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
            "Falha ao autenticar a identidade técnica do Storage."
        ) from error
    if authentication.session is None or authentication.user is None:
        raise RuntimeError("O Storage não forneceu uma sessão autenticada.")

    repository = BahiaSpecialTransferRepository.from_dsn(
        persistence_settings.database_url
    )
    service = SpecialTransferExtractionService(
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
