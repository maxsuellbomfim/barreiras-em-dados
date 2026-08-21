"""Publica somente os totais mensais validados da folha municipal."""

from __future__ import annotations

import argparse
import logging
import re
from collections.abc import Sequence
from datetime import date

from barreiras_docproc.canonical import CanonicalTextError

from ..payroll_publisher import (
    PayrollReportPublisher,
    PostgresPayrollPublicationRepository,
)
from ..payroll_report_pdf import PayrollReportContractError
from ..revenue_publisher import ArtifactMismatchError
from .publish_expense_reports import _cloud_client

PYPDF_LAYOUT_LOGGER = (
    "pypdf._text_extraction._layout_mode._fixed_width_page"
)
PYPDF_UNBALANCED_TARGET_PREFIX = "Unbalanced target operations, expected "


class KnownPypdfLayoutWarningFilter(logging.Filter):
    """Condensa um aviso recuperável sem esconder outros problemas do PDF."""

    def __init__(self) -> None:
        super().__init__()
        self.suppressed_count = 0

    def filter(self, record: logging.LogRecord) -> bool:
        is_known_recoverable_warning = (
            record.levelno == logging.WARNING
            and record.getMessage().startswith(
                PYPDF_UNBALANCED_TARGET_PREFIX
            )
        )
        if is_known_recoverable_warning:
            self.suppressed_count += 1
            return False
        return True


def _parse_reference_month(value: str) -> date:
    if re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", value) is None:
        raise argparse.ArgumentTypeError(
            "competência deve usar AAAA-MM, por exemplo 2026-07"
        )
    year, month = (int(part) for part in value.split("-"))
    return date(year, month, 1)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Publica totais determinísticos da folha municipal."
    )
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--fiscal-year-from", type=int, default=2021)
    parser.add_argument("--fiscal-year-to", type=int, default=date.today().year)
    parser.add_argument("--reference-month", type=_parse_reference_month)
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 20:
        parser.error("--limit deve estar entre 1 e 20")
    if not 1900 <= args.fiscal_year_from <= args.fiscal_year_to <= 2200:
        parser.error("intervalo fiscal inválido")
    if args.reference_month is not None and not (
        args.fiscal_year_from
        <= args.reference_month.year
        <= args.fiscal_year_to
    ):
        parser.error("competência fora do intervalo fiscal")

    from barreiras_collectors.persistence.storage import SupabaseStorageObjectStore
    from barreiras_collectors.settings import PersistenceSettings

    settings = PersistenceSettings.from_env()
    logging.basicConfig(level="INFO", format="%(message)s", force=True)
    client = _cloud_client(settings)
    repository = PostgresPayrollPublicationRepository.from_dsn(
        settings.database_url
    )
    reader = SupabaseStorageObjectStore(
        client.storage.from_(settings.raw_artifacts_bucket)
    )
    publisher = PayrollReportPublisher(
        object_reader=reader,
        repository=repository,
    )

    published = 0
    already_published = 0
    needs_review = 0
    artifacts = repository.pending_documents(
        limit=args.limit,
        fiscal_year_from=args.fiscal_year_from,
        fiscal_year_to=args.fiscal_year_to,
        reference_month=args.reference_month,
    )
    logger = logging.getLogger(__name__)
    pypdf_logger = logging.getLogger(PYPDF_LAYOUT_LOGGER)
    warning_filter = KnownPypdfLayoutWarningFilter()
    pypdf_logger.addFilter(warning_filter)
    try:
        for index, artifact in enumerate(artifacts, start=1):
            logger.info(
                "payroll_report_start artifact=%s period=%s progress=%s/%s",
                artifact.id,
                artifact.reference_month.isoformat(),
                index,
                len(artifacts),
            )
            try:
                result = publisher.publish(artifact)
            except (
                ArtifactMismatchError,
                CanonicalTextError,
                PayrollReportContractError,
                ValueError,
            ) as error:
                needs_review += 1
                repository.record_failure(
                    artifact,
                    error_code=type(error).__name__,
                    error_detail=str(error),
                )
                logger.error(
                    "payroll_report_needs_review artifact=%s error=%s",
                    artifact.id,
                    str(error)[:500],
                )
                continue
            if result.status == "published":
                published += 1
            else:
                already_published += 1
    finally:
        pypdf_logger.removeFilter(warning_filter)

    if warning_filter.suppressed_count:
        logger.info(
            "payroll_pdf_recoverable_warnings kind=unbalanced_target "
            "suppressed=%s",
            warning_filter.suppressed_count,
        )

    logger.info(
        "payroll_publication_completed artifacts=%s published=%s "
        "already_published=%s needs_review=%s",
        len(artifacts),
        published,
        already_published,
        needs_review,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
