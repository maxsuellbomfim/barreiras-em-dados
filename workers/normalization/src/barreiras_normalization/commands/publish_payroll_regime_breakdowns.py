"""Publica o detalhamento agregado da folha por regime/vínculo."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

from barreiras_docproc.canonical import CanonicalTextError

from ..payroll_regime_publisher import (
    PayrollRegimePublisher,
    PostgresPayrollRegimeRepository,
)
from ..payroll_report_pdf import PayrollReportContractError
from ..revenue_publisher import ArtifactMismatchError
from .publish_expense_reports import _cloud_client
from .publish_payroll_reports import (
    PYPDF_LAYOUT_LOGGER,
    KnownPypdfLayoutWarningFilter,
    _parse_reference_month,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Publica totais por vínculo reconciliados com a folha oficial."
    )
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--reference-month", type=_parse_reference_month)
    parser.add_argument("--require-complete-month", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 20:
        parser.error("--limit deve estar entre 1 e 20")
    if args.require_complete_month and args.reference_month is None:
        parser.error("--require-complete-month exige --reference-month")

    from barreiras_collectors.persistence.storage import SupabaseStorageObjectStore
    from barreiras_collectors.settings import PersistenceSettings

    settings = PersistenceSettings.from_env()
    logging.basicConfig(level="INFO", format="%(message)s", force=True)
    client = _cloud_client(settings)
    repository = PostgresPayrollRegimeRepository.from_dsn(settings.database_url)
    reader = SupabaseStorageObjectStore(
        client.storage.from_(settings.raw_artifacts_bucket)
    )
    publisher = PayrollRegimePublisher(
        object_reader=reader,
        repository=repository,
    )
    logger = logging.getLogger(__name__)
    warning_filter = KnownPypdfLayoutWarningFilter()
    pypdf_logger = logging.getLogger(PYPDF_LAYOUT_LOGGER)
    pypdf_logger.addFilter(warning_filter)
    published = 0
    already_published = 0
    needs_review = 0
    artifacts = repository.pending_documents(
        limit=args.limit,
        reference_month=args.reference_month,
    )
    try:
        for index, artifact in enumerate(artifacts, start=1):
            logger.info(
                "payroll_regime_start aggregate=%s period=%s progress=%s/%s",
                artifact.aggregate_id,
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
                    "payroll_regime_needs_review aggregate=%s error=%s",
                    artifact.aggregate_id,
                    str(error)[:500],
                )
                continue
            if result.status == "published":
                published += 1
            else:
                already_published += 1
    finally:
        pypdf_logger.removeFilter(warning_filter)

    logger.info(
        "payroll_regime_completed artifacts=%s published=%s "
        "already_published=%s needs_review=%s warnings=%s",
        len(artifacts),
        published,
        already_published,
        needs_review,
        warning_filter.suppressed_count,
    )
    if args.require_complete_month and (
        needs_review
        or not repository.has_public_breakdown(args.reference_month)
    ):
        logger.error(
            "payroll_regime_incomplete period=%s needs_review=%s",
            args.reference_month.isoformat(),
            needs_review,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
