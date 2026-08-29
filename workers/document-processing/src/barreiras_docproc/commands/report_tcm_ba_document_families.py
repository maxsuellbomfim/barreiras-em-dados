"""Reconcilia PDFs TCM-BA preservados com o inventário privado de famílias."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from barreiras_collectors.logging import log_event
from barreiras_collectors.settings import CollectorSettings, PostgresSettings

from ..tcm_ba_document_families import TcmBaDocumentFamilyCoverage
from ..tcm_ba_document_family_repository import (
    TcmBaDocumentFamilyExtractionRepository,
)


def coverage_exit_code(coverage: TcmBaDocumentFamilyCoverage) -> int:
    return 0 if coverage.complete else 1


def main(_argv: Sequence[str] | None = None) -> int:
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
    coverage = repository.document_family_coverage()
    exit_code = coverage_exit_code(coverage)
    log_event(
        logging.getLogger(__name__),
        logging.INFO if exit_code == 0 else logging.ERROR,
        "tcm_ba_document_family_coverage",
        preserved_documents=coverage.preserved_documents,
        classified_documents=coverage.classified_documents,
        unknown_documents=coverage.unknown_documents,
        missing_documents=coverage.missing_documents,
        duplicate_results=coverage.duplicate_results,
        invalid_results=coverage.invalid_results,
        open_failures=coverage.open_failures,
        gate="PASS" if exit_code == 0 else "BLOCK",
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())