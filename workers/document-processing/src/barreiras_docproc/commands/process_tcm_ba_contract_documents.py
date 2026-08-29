"""Segmenta contratos e aditivos TCM-BA em candidatos privados."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from barreiras_collectors.logging import log_event
from barreiras_collectors.settings import CollectorSettings, PostgresSettings

from ..tcm_ba_contract_document_repository import (
    TcmBaContractDocumentExtractionRepository,
    TcmBaContractDocumentPageSet,
)
from ..tcm_ba_contract_documents import (
    TcmBaContractDocumentExtractionService,
    TcmBaContractDocumentPersistResult,
    contract_document_job_idempotency_key,
)


@dataclass(frozen=True)
class TcmBaContractDocumentBatchSummary:
    pending_found: int
    processed: int
    failed: int
    jobs_created: int
    segments_inserted: int
    identified_segments: int
    unknown_segments: int


class PendingRepository(Protocol):
    def pending_page_sets(
        self,
        limit: int,
    ) -> tuple[TcmBaContractDocumentPageSet, ...]: ...

    def persist_failure(
        self,
        artifact,
        *,
        idempotency_key: str,
        error_code: str,
        error_detail: str,
    ) -> None: ...


class ProcessingService(Protocol):
    def process(self, artifact, pages) -> TcmBaContractDocumentPersistResult: ...


def run_batch(
    *,
    repository: PendingRepository,
    service: ProcessingService,
    limit: int,
    logger: logging.Logger | None = None,
) -> TcmBaContractDocumentBatchSummary:
    log = logger or logging.getLogger(__name__)
    pending = repository.pending_page_sets(limit)
    processed = 0
    failed = 0
    jobs_created = 0
    segments_inserted = 0
    identified_segments = 0
    unknown_segments = 0
    for page_set in pending:
        try:
            result = service.process(page_set.artifact, page_set.pages)
        except Exception as error:
            failed += 1
            try:
                repository.persist_failure(
                    page_set.artifact,
                    idempotency_key=contract_document_job_idempotency_key(
                        page_set.artifact.sha256
                    ),
                    error_code="processing_error",
                    error_detail=f"{type(error).__name__}: processing failure",
                )
            except Exception:
                log.debug(
                    "tcm_ba_contract_document_failure_persistence_failed",
                    exc_info=True,
                )
            log_event(
                log,
                logging.ERROR,
                "tcm_ba_contract_document_failed",
                artifact_hash=page_set.artifact.sha256,
                error_code="processing_error",
                error_type=type(error).__name__,
            )
            continue

        processed += 1
        jobs_created += int(result.job_created)
        segments_inserted += result.results_inserted
        identified_segments += result.identified_segments
        unknown_segments += result.unknown_segments
        log_event(
            log,
            logging.INFO,
            "tcm_ba_contract_document_processed",
            artifact_hash=page_set.artifact.sha256,
            pages=len(page_set.pages),
            job_created=result.job_created,
            segments=result.results_inserted,
            identified_segments=result.identified_segments,
            unknown_segments=result.unknown_segments,
        )

    summary = TcmBaContractDocumentBatchSummary(
        pending_found=len(pending),
        processed=processed,
        failed=failed,
        jobs_created=jobs_created,
        segments_inserted=segments_inserted,
        identified_segments=identified_segments,
        unknown_segments=unknown_segments,
    )
    log_event(
        log,
        logging.INFO if failed == 0 else logging.ERROR,
        "tcm_ba_contract_document_batch_completed",
        pending_found=summary.pending_found,
        processed=summary.processed,
        failed=summary.failed,
        jobs_created=summary.jobs_created,
        segments=summary.segments_inserted,
        identified_segments=summary.identified_segments,
        unknown_segments=summary.unknown_segments,
    )
    return summary


def batch_exit_code(summary: TcmBaContractDocumentBatchSummary) -> int:
    return 1 if summary.failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Segmenta a família privada de contratos e aditivos por cabeçalhos "
            "determinísticos, sem publicar texto, pessoas ou valores."
        )
    )
    parser.add_argument("--limit", type=int, default=5)
    arguments = parser.parse_args(argv)
    if not 1 <= arguments.limit <= 50:
        parser.error("--limit deve estar entre 1 e 50.")

    collector_settings = CollectorSettings.from_env()
    postgres = PostgresSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    repository = TcmBaContractDocumentExtractionRepository.from_dsn(
        postgres.database_url
    )
    summary = run_batch(
        repository=repository,
        service=TcmBaContractDocumentExtractionService(repository=repository),
        limit=arguments.limit,
    )
    return batch_exit_code(summary)


if __name__ == "__main__":
    raise SystemExit(main())
