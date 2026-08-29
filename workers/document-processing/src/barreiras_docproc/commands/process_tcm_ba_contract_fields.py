"""Extrai candidatos privados de campos dos segmentos contratuais TCM-BA."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from barreiras_collectors.logging import log_event
from barreiras_collectors.settings import CollectorSettings, PostgresSettings

from ..tcm_ba_contract_documents import segment_contract_documents
from ..tcm_ba_contract_field_repository import (
    TcmBaContractFieldExtractionRepository,
    TcmBaContractFieldPageSet,
)
from ..tcm_ba_contract_fields import (
    TcmBaContractFieldExtractionService,
    TcmBaContractFieldPersistResult,
    contract_field_job_idempotency_key,
)


@dataclass(frozen=True)
class TcmBaContractFieldBatchSummary:
    pending_found: int
    processed: int
    failed: int
    jobs_created: int
    candidates_inserted: int
    fields_observed: int
    empty_candidates: int


class PendingRepository(Protocol):
    def pending_page_sets(
        self,
        limit: int,
    ) -> tuple[TcmBaContractFieldPageSet, ...]: ...

    def persist_failure(
        self,
        artifact,
        *,
        idempotency_key: str,
        error_code: str,
        error_detail: str,
    ) -> None: ...


class ProcessingService(Protocol):
    def process(
        self,
        artifact,
        pages,
        segments,
    ) -> TcmBaContractFieldPersistResult: ...


def run_batch(
    *,
    repository: PendingRepository,
    service: ProcessingService,
    limit: int,
    logger: logging.Logger | None = None,
) -> TcmBaContractFieldBatchSummary:
    log = logger or logging.getLogger(__name__)
    pending = repository.pending_page_sets(limit)
    processed = 0
    failed = 0
    jobs_created = 0
    candidates_inserted = 0
    fields_observed = 0
    empty_candidates = 0
    for page_set in pending:
        try:
            segments = segment_contract_documents(page_set.pages)
            result = service.process(
                page_set.artifact,
                page_set.pages,
                segments,
            )
        except Exception as error:
            failed += 1
            detail = f"{type(error).__name__}: processing failure"
            try:
                repository.persist_failure(
                    page_set.artifact,
                    idempotency_key=contract_field_job_idempotency_key(
                        page_set.artifact.sha256
                    ),
                    error_code="processing_error",
                    error_detail=detail,
                )
            except Exception:
                log.debug(
                    "tcm_ba_contract_field_failure_persistence_failed",
                    exc_info=True,
                )
            log_event(
                log,
                logging.ERROR,
                "tcm_ba_contract_field_failed",
                artifact_hash=page_set.artifact.sha256,
                error_code="processing_error",
                error_type=type(error).__name__,
            )
            continue

        processed += 1
        jobs_created += int(result.job_created)
        candidates_inserted += result.results_inserted
        fields_observed += result.fields_observed
        empty_candidates += result.empty_candidates
        log_event(
            log,
            logging.INFO,
            "tcm_ba_contract_fields_processed",
            artifact_hash=page_set.artifact.sha256,
            pages=len(page_set.pages),
            segments=len(segments),
            job_created=result.job_created,
            candidates=result.results_inserted,
            fields_observed=result.fields_observed,
            empty_candidates=result.empty_candidates,
        )

    summary = TcmBaContractFieldBatchSummary(
        pending_found=len(pending),
        processed=processed,
        failed=failed,
        jobs_created=jobs_created,
        candidates_inserted=candidates_inserted,
        fields_observed=fields_observed,
        empty_candidates=empty_candidates,
    )
    log_event(
        log,
        logging.INFO if failed == 0 else logging.ERROR,
        "tcm_ba_contract_field_batch_completed",
        pending_found=summary.pending_found,
        processed=summary.processed,
        failed=summary.failed,
        jobs_created=summary.jobs_created,
        candidates=summary.candidates_inserted,
        fields_observed=summary.fields_observed,
        empty_candidates=summary.empty_candidates,
    )
    return summary


def batch_exit_code(summary: TcmBaContractFieldBatchSummary) -> int:
    return 1 if summary.failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Extrai campos contratuais privados e citados, sem publicação "
            "automática nem inferência de valores ausentes."
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
    repository = TcmBaContractFieldExtractionRepository.from_dsn(
        postgres.database_url
    )
    summary = run_batch(
        repository=repository,
        service=TcmBaContractFieldExtractionService(repository=repository),
        limit=arguments.limit,
    )
    return batch_exit_code(summary)


if __name__ == "__main__":
    raise SystemExit(main())
