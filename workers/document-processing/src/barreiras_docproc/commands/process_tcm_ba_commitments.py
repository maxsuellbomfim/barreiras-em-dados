"""Cria candidatos privados de notas de empenho a partir de páginas TCM-BA."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from barreiras_collectors.logging import log_event
from barreiras_collectors.settings import CollectorSettings, PersistenceSettings

from ..tcm_ba_commitment_repository import (
    TcmBaCommitmentExtractionRepository,
    TcmBaCommitmentPageSet,
)
from ..tcm_ba_commitments import (
    TcmBaCommitmentExtractionService,
    TcmBaCommitmentPersistResult,
    commitment_job_idempotency_key,
)


@dataclass(frozen=True)
class TcmBaCommitmentBatchSummary:
    pending_found: int
    processed: int
    failed: int
    jobs_created: int
    results_inserted: int


class PendingRepository(Protocol):
    def pending_page_sets(
        self,
        limit: int,
    ) -> tuple[TcmBaCommitmentPageSet, ...]: ...

    def persist_failure(
        self,
        artifact,
        *,
        idempotency_key: str,
        error_code: str,
        error_detail: str,
    ) -> None: ...


class ProcessingService(Protocol):
    def process(self, artifact, pages) -> TcmBaCommitmentPersistResult: ...


def run_batch(
    *,
    repository: PendingRepository,
    service: ProcessingService,
    limit: int,
    logger: logging.Logger | None = None,
) -> TcmBaCommitmentBatchSummary:
    log = logger or logging.getLogger(__name__)
    pending = repository.pending_page_sets(limit)
    processed = 0
    failed = 0
    jobs_created = 0
    results_inserted = 0
    for page_set in pending:
        try:
            result = service.process(page_set.artifact, page_set.pages)
        except Exception as error:
            failed += 1
            detail = f"{type(error).__name__}: processing failure"
            try:
                repository.persist_failure(
                    page_set.artifact,
                    idempotency_key=commitment_job_idempotency_key(
                        page_set.artifact.sha256
                    ),
                    error_code="processing_error",
                    error_detail=detail,
                )
            except Exception:
                log.debug(
                    "tcm_ba_commitment_failure_persistence_failed",
                    exc_info=True,
                )
            log_event(
                log,
                logging.ERROR,
                "tcm_ba_commitment_candidate_failed",
                artifact_hash=page_set.artifact.sha256,
                error_code="processing_error",
                error_type=type(error).__name__,
            )
            continue

        processed += 1
        jobs_created += int(result.job_created)
        results_inserted += result.results_inserted
        log_event(
            log,
            logging.INFO,
            "tcm_ba_commitment_candidates_processed",
            artifact_hash=page_set.artifact.sha256,
            pages=len(page_set.pages),
            job_created=result.job_created,
            candidates=result.results_inserted,
        )

    summary = TcmBaCommitmentBatchSummary(
        pending_found=len(pending),
        processed=processed,
        failed=failed,
        jobs_created=jobs_created,
        results_inserted=results_inserted,
    )
    log_event(
        log,
        logging.INFO if failed == 0 else logging.ERROR,
        "tcm_ba_commitment_candidate_batch_completed",
        pending_found=summary.pending_found,
        processed=summary.processed,
        failed=summary.failed,
        jobs_created=summary.jobs_created,
        candidates=summary.results_inserted,
    )
    return summary


def batch_exit_code(summary: TcmBaCommitmentBatchSummary) -> int:
    return 1 if summary.failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Cria candidatos privados de notas de empenho nas páginas TCM-BA, "
            "sem publicar nem normalizar valores."
        )
    )
    parser.add_argument("--limit", type=int, default=5)
    arguments = parser.parse_args(argv)
    if not 1 <= arguments.limit <= 50:
        parser.error("--limit deve estar entre 1 e 50.")

    collector_settings = CollectorSettings.from_env()
    persistence = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    if persistence.mode != "postgres-supabase":
        raise RuntimeError(
            "A extração TCM-BA requer PERSISTENCE_MODE=postgres-supabase."
        )
    if persistence.database_url is None:
        raise RuntimeError("DATABASE_URL não configurada.")

    repository = TcmBaCommitmentExtractionRepository.from_dsn(persistence.database_url)
    summary = run_batch(
        repository=repository,
        service=TcmBaCommitmentExtractionService(repository=repository),
        limit=arguments.limit,
    )
    return batch_exit_code(summary)


if __name__ == "__main__":
    raise SystemExit(main())
