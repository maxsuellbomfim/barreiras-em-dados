"""Inventaria, em área privada, as famílias documentais oficiais do TCM-BA."""

from __future__ import annotations

import argparse
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from barreiras_collectors.logging import log_event
from barreiras_collectors.settings import CollectorSettings, PostgresSettings

from ..tcm_ba_document_families import (
    TcmBaCatalogDocument,
    TcmBaDocumentFamilyPersistResult,
    TcmBaDocumentFamilyService,
    document_family_job_idempotency_key,
)
from ..tcm_ba_document_family_repository import (
    TcmBaDocumentFamilyExtractionRepository,
)


@dataclass(frozen=True)
class TcmBaDocumentFamilyBatchSummary:
    pending_found: int
    processed: int
    failed: int
    classified: int
    unknown: int
    jobs_created: int
    results_inserted: int


class PendingRepository(Protocol):
    def pending_documents(
        self,
        limit: int,
        *,
        artifact_sha256: str | None = None,
    ) -> tuple[TcmBaCatalogDocument, ...]: ...

    def persist_failure(
        self,
        document: TcmBaCatalogDocument,
        *,
        idempotency_key: str,
        error_code: str,
        error_detail: str,
    ) -> None: ...


class ProcessingService(Protocol):
    def process(
        self,
        document: TcmBaCatalogDocument,
    ) -> TcmBaDocumentFamilyPersistResult: ...


def run_batch(
    *,
    repository: PendingRepository,
    service: ProcessingService,
    limit: int,
    artifact_sha256: str | None = None,
    logger: logging.Logger | None = None,
) -> TcmBaDocumentFamilyBatchSummary:
    log = logger or logging.getLogger(__name__)
    pending = repository.pending_documents(
        limit,
        artifact_sha256=artifact_sha256,
    )
    processed = 0
    failed = 0
    classified = 0
    unknown = 0
    jobs_created = 0
    results_inserted = 0
    for document in pending:
        try:
            result = service.process(document)
        except Exception as error:
            failed += 1
            detail = f"{type(error).__name__}: processing failure"
            try:
                repository.persist_failure(
                    document,
                    idempotency_key=document_family_job_idempotency_key(
                        document.artifact.sha256
                    ),
                    error_code="processing_error",
                    error_detail=detail,
                )
            except Exception:
                log.debug(
                    "tcm_ba_document_family_failure_persistence_failed",
                    exc_info=True,
                )
            log_event(
                log,
                logging.ERROR,
                "tcm_ba_document_family_failed",
                artifact_hash=document.artifact.sha256,
                error_code="processing_error",
                error_type=type(error).__name__,
            )
            continue

        processed += 1
        jobs_created += int(result.job_created)
        results_inserted += result.results_inserted
        if result.family == "unknown":
            unknown += 1
        else:
            classified += 1
        log_event(
            log,
            logging.INFO,
            "tcm_ba_document_family_processed",
            artifact_hash=document.artifact.sha256,
            family=result.family,
            job_created=result.job_created,
        )

    summary = TcmBaDocumentFamilyBatchSummary(
        pending_found=len(pending),
        processed=processed,
        failed=failed,
        classified=classified,
        unknown=unknown,
        jobs_created=jobs_created,
        results_inserted=results_inserted,
    )
    log_event(
        log,
        logging.INFO if failed == 0 else logging.ERROR,
        "tcm_ba_document_family_batch_completed",
        pending_found=summary.pending_found,
        processed=summary.processed,
        failed=summary.failed,
        classified=summary.classified,
        unknown=summary.unknown,
        jobs_created=summary.jobs_created,
        results_inserted=summary.results_inserted,
    )
    return summary


def batch_exit_code(summary: TcmBaDocumentFamilyBatchSummary) -> int:
    return 1 if summary.failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Classifica documentos TCM-BA somente pela categoria do catálogo "
            "oficial e grava um inventário privado; categorias novas ficam unknown."
        )
    )
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--artifact-sha256", default="")
    arguments = parser.parse_args(argv)
    if not 1 <= arguments.limit <= 50:
        parser.error("--limit deve estar entre 1 e 50.")
    artifact_sha256 = arguments.artifact_sha256.strip().lower() or None
    if artifact_sha256 is not None and not re.fullmatch(
        r"[0-9a-f]{64}", artifact_sha256
    ):
        parser.error("--artifact-sha256 deve ser um SHA-256 hexadecimal.")

    collector_settings = CollectorSettings.from_env()
    postgres = PostgresSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    repository = TcmBaDocumentFamilyExtractionRepository.from_dsn(
        postgres.database_url
    )
    summary = run_batch(
        repository=repository,
        service=TcmBaDocumentFamilyService(repository=repository),
        limit=arguments.limit,
        artifact_sha256=artifact_sha256,
    )
    return batch_exit_code(summary)


if __name__ == "__main__":
    raise SystemExit(main())
