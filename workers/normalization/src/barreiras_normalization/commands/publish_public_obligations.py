"""Publica pagamentos de restos a pagar extraídos de balancetes preservados."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from datetime import date

from barreiras_docproc.canonical import CanonicalTextError
from barreiras_docproc.ocr import OcrError, TesseractEngine
from barreiras_docproc.pdf_text import derive_pdf_layout_text

from ..public_obligation_ocr import PublicObligationOcrExtractor
from ..public_obligation_pdf import (
    PublicObligationPdfContractError,
    PublicObligationSectionAbsentError,
    PublicObligationSectionIncompleteError,
    RestosAPagarSummary,
    validate_restos_a_pagar_progression,
)
from ..public_obligation_publisher import (
    PostgresPublicObligationPublicationRepository,
    PublicObligationPublisher,
)
from ..revenue_publisher import ArtifactMismatchError
from .publish_expense_reports import _cloud_client


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Publica pagamentos de restos a pagar declarados em balancetes."
    )
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--fiscal-year-from", type=int, default=2021)
    parser.add_argument("--fiscal-year-to", type=int, default=date.today().year)
    parser.add_argument(
        "--reference-month",
        type=int,
        default=None,
        help="Restringe a seleção ao mês informado (1 a 12).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Valida e registra os valores no log sem escrever no banco.",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 20:
        parser.error("--limit deve estar entre 1 e 20")
    if not 1900 <= args.fiscal_year_from <= args.fiscal_year_to <= 2200:
        parser.error("intervalo fiscal inválido")
    if args.reference_month is not None and not 1 <= args.reference_month <= 12:
        parser.error("--reference-month deve estar entre 1 e 12")

    from barreiras_collectors.persistence.storage import SupabaseStorageObjectStore
    from barreiras_collectors.settings import PersistenceSettings

    settings = PersistenceSettings.from_env()
    logging.basicConfig(level="INFO", format="%(message)s", force=True)
    client = _cloud_client(settings)
    repository = PostgresPublicObligationPublicationRepository.from_dsn(
        settings.database_url
    )
    reader = SupabaseStorageObjectStore(
        client.storage.from_(settings.raw_artifacts_bucket)
    )
    publisher = PublicObligationPublisher(
        object_reader=reader,
        repository=repository,
        ocr_extractor=PublicObligationOcrExtractor(
            engine=TesseractEngine(page_segmentation_mode=6),
            alternative_engines=(TesseractEngine(page_segmentation_mode=3),),
            layout_text_deriver=derive_pdf_layout_text,
        ).extract,
    )

    published = 0
    already_published = 0
    validated = 0
    source_absent = 0
    source_incomplete = 0
    source_conflicts = 0
    failed = 0
    previous_dry_run_summary: RestosAPagarSummary | None = None
    artifacts = repository.pending_documents(
        limit=args.limit,
        fiscal_year_from=args.fiscal_year_from,
        fiscal_year_to=args.fiscal_year_to,
        reference_month=args.reference_month,
    )
    logger = logging.getLogger(__name__)
    for index, artifact in enumerate(artifacts, start=1):
        logger.info(
            "public_obligation_start artifact=%s progress=%s/%s source=%s",
            artifact.id,
            index,
            len(artifacts),
            artifact.source_url,
        )
        try:
            if args.dry_run:
                extraction = publisher.validate(artifact)
                summary = extraction.summary
                if (
                    previous_dry_run_summary is not None
                    and previous_dry_run_summary.fiscal_year == summary.fiscal_year
                    and previous_dry_run_summary.period_end.month + 1
                    == summary.period_end.month
                ):
                    validate_restos_a_pagar_progression(
                        summary,
                        previous_month_to_date=(
                            previous_dry_run_summary.payments_to_date_amount
                        ),
                    )
                previous_dry_run_summary = summary
                validated += 1
                logger.info(
                    "public_obligation_dry_run_validated artifact=%s period=%s "
                    "prior=%s month=%s to_date=%s method=%s pages=%s rotation=%s",
                    artifact.id,
                    summary.period_end.isoformat(),
                    summary.payments_prior_amount,
                    summary.payments_period_amount,
                    summary.payments_to_date_amount,
                    extraction.provenance.extraction_method,
                    extraction.provenance.page_numbers,
                    extraction.provenance.rotation_degrees,
                )
                continue
            result = publisher.publish(artifact)
        except PublicObligationSectionAbsentError as error:
            previous_dry_run_summary = None
            source_absent += 1
            if not args.dry_run:
                repository.record_section_absent(artifact, detail=str(error))
            logger.info(
                "public_obligation_section_absent artifact=%s period=%04d-%02d "
                "source=%s detail=%s",
                artifact.id,
                artifact.fiscal_year,
                artifact.reference_month,
                artifact.source_url,
                str(error)[:500],
            )
            continue
        except PublicObligationSectionIncompleteError as error:
            previous_dry_run_summary = None
            source_incomplete += 1
            if not args.dry_run:
                repository.record_section_incomplete(artifact, detail=str(error))
            logger.info(
                "public_obligation_section_incomplete artifact=%s period=%04d-%02d "
                "source=%s detail=%s",
                artifact.id,
                artifact.fiscal_year,
                artifact.reference_month,
                artifact.source_url,
                str(error)[:500],
            )
            continue
        except (
            ArtifactMismatchError,
            CanonicalTextError,
            OcrError,
            PublicObligationPdfContractError,
            ValueError,
        ) as error:
            previous_dry_run_summary = None
            failed += 1
            if not args.dry_run:
                repository.record_failure(
                    artifact,
                    error_code=type(error).__name__,
                    error_detail=str(error),
                )
            logger.error(
                "public_obligation_failed artifact=%s error=%s",
                artifact.id,
                str(error)[:2400] if args.dry_run else str(error)[:500],
            )
            continue
        if result.status == "published":
            published += 1
        elif result.status in ("source_conflict", "already_source_conflict"):
            source_conflicts += 1
        else:
            already_published += 1

    logger.info(
        "public_obligation_publication_completed artifacts=%s published=%s "
        "already_published=%s validated=%s source_absent=%s "
        "source_incomplete=%s source_conflicts=%s failed=%s dry_run=%s",
        len(artifacts),
        published,
        already_published,
        validated,
        source_absent,
        source_incomplete,
        source_conflicts,
        failed,
        args.dry_run,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
