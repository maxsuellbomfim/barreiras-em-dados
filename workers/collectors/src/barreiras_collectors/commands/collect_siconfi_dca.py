"""Preserva as contas anuais oficiais de Barreiras publicadas no SICONFI."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from ..collection_control import (
    CollectionControl,
    CollectionOutcome,
    build_execution_idempotency_key,
)
from ..connectors.siconfi import ENDPOINT_CODE, SOURCE_CODE, fetch_siconfi_dca
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import (
    SICONFI_DCA_COLLECTOR_VERSION,
    SICONFI_DCA_PARSER_VERSION,
    SiconfiDcaPersistenceService,
)
from ..resilience import PacedRateLimiter
from ..settings import CollectorSettings, PersistenceSettings
from .pncp_runtime import build_authenticated_object_store

MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
EXECUTION_NAMESPACE = "siconfi-dca"


@dataclass(frozen=True)
class SiconfiDcaCollectionSummary:
    years: int
    pages: int
    rows: int
    inserted_records: int
    existing_records: int
    artifact_hashes: tuple[str, ...]
    year_from: int
    year_to: int


def resolve_year_range(
    year_from: int,
    year_to: int,
    *,
    collected_on: date,
) -> tuple[date, date]:
    if year_from < 2013 or year_to < year_from or year_to > collected_on.year:
        raise ValueError("O intervalo DCA deve estar entre 2013 e o ano corrente.")
    period_end = (
        collected_on if year_to == collected_on.year else date(year_to, 12, 31)
    )
    return date(year_from, 1, 1), period_end


def build_siconfi_execution_key(
    *, environment: Mapping[str, str] | None = None
) -> str:
    return build_execution_idempotency_key(
        EXECUTION_NAMESPACE,
        environment=environment,
    )


def execute_controlled_siconfi_collection(
    *,
    control: CollectionControl,
    operation: Callable[[], SiconfiDcaCollectionSummary],
) -> SiconfiDcaCollectionSummary:
    with control:
        summary = operation()
        control.complete(
            outcome=(
                CollectionOutcome.COMPLETE
                if summary.rows > 0
                else CollectionOutcome.EMPTY
            ),
            observed_records=summary.rows,
            checkpoint={
                "year_from": summary.year_from,
                "year_to": summary.year_to,
                "years": summary.years,
                "pages": summary.pages,
                "artifact_hashes": list(summary.artifact_hashes),
            },
            metrics={
                "years": summary.years,
                "pages": summary.pages,
                "rows": summary.rows,
                "inserted_records": summary.inserted_records,
                "existing_records": summary.existing_records,
                "year_from": summary.year_from,
                "year_to": summary.year_to,
            },
        )
    return summary


def execute_yearly_siconfi_backfill(
    *,
    fiscal_years: Sequence[int],
    control_factory: Callable[[int], CollectionControl],
    operation_factory: Callable[
        [int], Callable[[], SiconfiDcaCollectionSummary]
    ],
    logger: logging.Logger,
) -> tuple[tuple[int, SiconfiDcaCollectionSummary], ...]:
    """Classifica cada exercício isoladamente e tenta os demais após uma falha."""
    completed: list[tuple[int, SiconfiDcaCollectionSummary]] = []
    failures: list[tuple[int, Exception]] = []
    for fiscal_year in fiscal_years:
        try:
            summary = execute_controlled_siconfi_collection(
                control=control_factory(fiscal_year),
                operation=operation_factory(fiscal_year),
            )
        except Exception as error:
            failures.append((fiscal_year, error))
            log_event(
                logger,
                logging.ERROR,
                "collector_siconfi_dca_year_failed",
                source=SOURCE_CODE,
                fiscal_year=fiscal_year,
                error_type=type(error).__name__,
            )
            continue
        completed.append((fiscal_year, summary))
        log_event(
            logger,
            logging.INFO,
            "collector_siconfi_dca_year_completed",
            source=SOURCE_CODE,
            fiscal_year=fiscal_year,
            coverage_status=("complete" if summary.rows > 0 else "empty"),
            pages=summary.pages,
            rows=summary.rows,
            inserted_records=summary.inserted_records,
            existing_records=summary.existing_records,
        )

    if failures:
        failed_years = ", ".join(str(year) for year, _error in failures)
        raise RuntimeError(
            f"A coleta anual do SICONFI falhou em: {failed_years}."
        ) from failures[0][1]
    return tuple(completed)


def main(argv: Sequence[str] | None = None) -> int:
    collected_on = datetime.now(MUNICIPAL_TIMEZONE).date()
    parser = argparse.ArgumentParser(
        description=(
            "Preserva todas as linhas da Declaração das Contas Anuais de "
            "Barreiras, sem calcular totais durante a coleta."
        )
    )
    parser.add_argument("--year-from", type=int, default=2021)
    parser.add_argument("--year-to", type=int, default=collected_on.year)
    args = parser.parse_args(argv)
    try:
        resolve_year_range(
            args.year_from,
            args.year_to,
            collected_on=collected_on,
        )
    except ValueError as error:
        parser.error(str(error))

    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    if persistence_settings.mode != "postgres-supabase":
        raise RuntimeError("A DCA requer PERSISTENCE_MODE=postgres-supabase.")
    if persistence_settings.database_url is None:
        raise RuntimeError("Configuração de banco incompleta.")

    repository = PostgresCollectionRepository.from_dsn(
        persistence_settings.database_url
    )
    logger = logging.getLogger(__name__)
    service = SiconfiDcaPersistenceService(
        object_store=build_authenticated_object_store(persistence_settings),
        repository=repository,
    )
    limiter = PacedRateLimiter(60)

    def control_factory(fiscal_year: int) -> CollectionControl:
        return CollectionControl(
            repository=repository,
            source_code=SOURCE_CODE,
            endpoint_code=ENDPOINT_CODE,
            idempotency_key=build_execution_idempotency_key(
                f"siconfi-dca-{fiscal_year}"
            ),
            collector_version=SICONFI_DCA_COLLECTOR_VERSION,
            parser_version=SICONFI_DCA_PARSER_VERSION,
            partition_key=f"fiscal-year:{fiscal_year}",
            period_start=date(fiscal_year, 1, 1),
            period_end=(
                collected_on
                if fiscal_year == collected_on.year
                else date(fiscal_year, 12, 31)
            ),
        )

    def operation_factory(
        fiscal_year: int,
    ) -> Callable[[], SiconfiDcaCollectionSummary]:
        def operation() -> SiconfiDcaCollectionSummary:
            pages = fetch_siconfi_dca(
                year=fiscal_year,
                rate_limiter=limiter,
                logger=logger,
            )
            rows = inserted_records = existing_records = 0
            hashes: list[str] = []
            for page in pages:
                result = service.persist(page)
                rows += len(page.items)
                inserted_records += result.inserted_records
                existing_records += result.existing_records
                hashes.append(result.sha256)
            return SiconfiDcaCollectionSummary(
                years=1,
                pages=len(pages),
                rows=rows,
                inserted_records=inserted_records,
                existing_records=existing_records,
                artifact_hashes=tuple(hashes),
                year_from=fiscal_year,
                year_to=fiscal_year,
            )

        return operation

    results = execute_yearly_siconfi_backfill(
        fiscal_years=tuple(range(args.year_from, args.year_to + 1)),
        control_factory=control_factory,
        operation_factory=operation_factory,
        logger=logger,
    )
    log_event(
        logger,
        logging.INFO,
        "collector_siconfi_dca_completed",
        source=SOURCE_CODE,
        years=len(results),
        pages=sum(summary.pages for _year, summary in results),
        rows=sum(summary.rows for _year, summary in results),
        inserted_records=sum(
            summary.inserted_records for _year, summary in results
        ),
        existing_records=sum(
            summary.existing_records for _year, summary in results
        ),
        year_from=args.year_from,
        year_to=args.year_to,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
