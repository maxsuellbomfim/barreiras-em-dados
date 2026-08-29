"""Relata cobertura documental TCM-BA sem expor texto ou credenciais."""

from __future__ import annotations

import logging

from barreiras_collectors.logging import log_event
from barreiras_collectors.settings import CollectorSettings, PostgresSettings

from ..postgres import PostgresExtractionRepository


def main() -> int:
    collector_settings = CollectorSettings.from_env()
    postgres = PostgresSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    report = PostgresExtractionRepository.from_dsn(
        postgres.database_url
    ).tcm_ba_document_processing_report()
    log_event(
        logging.getLogger(__name__),
        logging.INFO if report.approved else logging.ERROR,
        "tcm_ba_document_processing_report",
        total_pdfs=report.total_pdfs,
        pdfs_with_pages=report.pdfs_with_pages,
        pages_total=report.pages_total,
        pages_embedded=report.pages_embedded,
        pages_ocr=report.pages_ocr,
        pages_awaiting_ocr=report.pages_awaiting_ocr,
        failed_jobs=report.failed_jobs,
        approved=report.approved,
    )
    return 0 if report.approved else 1


if __name__ == "__main__":
    raise SystemExit(main())
