"""Preserva o RGF-Anexo 02 (dívida consolidada) de Barreiras publicado no SICONFI."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from datetime import date, datetime
from zoneinfo import ZoneInfo

from ..collection_control import (
    CollectionControl,
    CollectionOutcome,
    build_execution_idempotency_key,
)
from ..connectors.siconfi import (
    RGF_ENDPOINT_CODE,
    SOURCE_CODE,
    fetch_siconfi_rgf_annex2,
)
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import (
    SICONFI_RGF_COLLECTOR_VERSION,
    SICONFI_RGF_PARSER_VERSION,
    SiconfiDcaPersistenceService,
)
from ..resilience import PacedRateLimiter
from ..settings import CollectorSettings, PersistenceSettings
from .pncp_runtime import build_authenticated_object_store

MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
PERIOD_ENDS = ((4, 30), (8, 31), (12, 31))


def closed_periods(
    year_from: int, year_to: int, *, collected_on: date
) -> tuple[tuple[int, int], ...]:
    """Quadrimestres já encerrados; os em curso ainda não têm RGF."""
    if year_from < 2015 or year_to < year_from or year_to > collected_on.year:
        raise ValueError("O intervalo do RGF deve estar entre 2015 e o ano corrente.")
    return tuple(
        (year, period)
        for year in range(year_from, year_to + 1)
        for period, (month, day) in enumerate(PERIOD_ENDS, start=1)
        if date(year, month, day) < collected_on
    )


def main(argv: Sequence[str] | None = None) -> int:
    collected_on = datetime.now(MUNICIPAL_TIMEZONE).date()
    parser = argparse.ArgumentParser(
        description=(
            "Preserva cada linha do Anexo 02 do RGF (dívida consolidada) de "
            "Barreiras, sem calcular totais durante a coleta."
        )
    )
    parser.add_argument("--year-from", type=int, default=2019)
    parser.add_argument("--year-to", type=int, default=collected_on.year)
    args = parser.parse_args(argv)
    try:
        periods = closed_periods(
            args.year_from, args.year_to, collected_on=collected_on
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
        raise RuntimeError("O RGF requer PERSISTENCE_MODE=postgres-supabase.")
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
    failures: list[str] = []
    for year, period in periods:
        month, day = PERIOD_ENDS[period - 1]
        control = CollectionControl(
            repository=repository,
            source_code=SOURCE_CODE,
            endpoint_code=RGF_ENDPOINT_CODE,
            idempotency_key=build_execution_idempotency_key(
                f"siconfi-rgf-anexo-02-{year}-q{period}"
            ),
            collector_version=SICONFI_RGF_COLLECTOR_VERSION,
            parser_version=SICONFI_RGF_PARSER_VERSION,
            partition_key=f"fiscal-period:{year}-q{period}",
            period_start=date(year, 1, 1),
            period_end=date(year, month, day),
        )
        try:
            with control:
                pages = fetch_siconfi_rgf_annex2(
                    year=year, period=period, rate_limiter=limiter, logger=logger
                )
                rows = inserted = existing = 0
                hashes: list[str] = []
                for page in pages:
                    result = service.persist(page)
                    rows += len(page.items)
                    inserted += result.inserted_records
                    existing += result.existing_records
                    hashes.append(result.sha256)
                # Vazio é estado próprio (ainda não homologado), nunca dívida zero.
                control.complete(
                    outcome=CollectionOutcome.COMPLETE
                    if rows
                    else CollectionOutcome.EMPTY,
                    observed_records=rows,
                    checkpoint={
                        "year": year,
                        "period": period,
                        "pages": len(pages),
                        "artifact_hashes": hashes,
                    },
                    metrics={
                        "rows": rows,
                        "inserted_records": inserted,
                        "existing_records": existing,
                    },
                )
        except Exception as error:
            failures.append(f"{year}-q{period}")
            log_event(
                logger,
                logging.ERROR,
                "collector_siconfi_rgf_period_failed",
                source=SOURCE_CODE,
                year=year,
                period=period,
                error_type=type(error).__name__,
            )
            continue
        log_event(
            logger,
            logging.INFO,
            "collector_siconfi_rgf_period_completed",
            source=SOURCE_CODE,
            year=year,
            period=period,
            rows=rows,
            inserted_records=inserted,
            existing_records=existing,
        )
    if failures:
        raise RuntimeError(f"A coleta do RGF falhou em: {', '.join(failures)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
