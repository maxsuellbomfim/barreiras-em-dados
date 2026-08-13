"""Preserva e recorta o arquivo histórico de propostas do Transferegov."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from ..collection_control import (
    CollectionControl,
    CollectionOutcome,
    build_execution_idempotency_key,
)
from ..connectors.transferegov_download_catalog import fetch_download_catalog
from ..connectors.transferegov_historical_proposals import (
    ARCHIVE_NAME,
    ENDPOINT_CODE,
    SOURCE_CODE,
    fetch_historical_proposals,
)
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import (
    TRANSFEREGOV_HISTORICAL_PROPOSAL_COLLECTOR_VERSION,
    TRANSFEREGOV_HISTORICAL_PROPOSAL_PARSER_VERSION,
    TransferegovHistoricalProposalPersistenceService,
)
from ..settings import CollectorSettings, PersistenceSettings
from .pncp_runtime import build_authenticated_object_store

MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")


@dataclass(frozen=True)
class HistoricalProposalCollectionSummary:
    proposals: int
    archive_bytes: int
    inserted_records: int
    existing_records: int
    archive_sha256: str
    catalog_etag: str
    year_from: int
    year_to: int


def resolve_coverage_period(
    *,
    year_from: int,
    year_to: int,
    collected_on: date,
) -> tuple[date, date]:
    """Não declara cobertura para dias que ainda não ocorreram."""
    if year_from < 2008 or year_to < year_from:
        raise ValueError("período histórico inválido")
    if year_to > collected_on.year:
        raise ValueError("ano futuro não pode ser classificado")
    period_end = (
        collected_on
        if year_to == collected_on.year
        else date(year_to, 12, 31)
    )
    return date(year_from, 1, 1), period_end


def execute_controlled_historical_proposals(
    *,
    control: CollectionControl,
    operation: Callable[[], HistoricalProposalCollectionSummary],
) -> HistoricalProposalCollectionSummary:
    """Só fecha cobertura depois de preservar, restaurar e gravar registros."""
    with control:
        summary = operation()
        control.complete(
            outcome=(
                CollectionOutcome.COMPLETE
                if summary.proposals > 0
                else CollectionOutcome.EMPTY
            ),
            observed_records=summary.proposals,
            checkpoint={
                "catalog_etag": summary.catalog_etag,
                "archive_sha256": summary.archive_sha256,
                "year_from": summary.year_from,
                "year_to": summary.year_to,
            },
            metrics={
                "proposals": summary.proposals,
                "archive_bytes": summary.archive_bytes,
                "inserted_records": summary.inserted_records,
                "existing_records": summary.existing_records,
                "archive_sha256": summary.archive_sha256,
                "catalog_etag": summary.catalog_etag,
                "year_from": summary.year_from,
                "year_to": summary.year_to,
            },
        )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    collected_on = datetime.now(MUNICIPAL_TIMEZONE).date()
    current_year = collected_on.year
    parser = argparse.ArgumentParser(
        description=(
            "Preserva siconv_proposta.zip e materializa somente propostas de "
            "Barreiras no período contratado."
        )
    )
    parser.add_argument("--year-from", type=int, default=2021)
    parser.add_argument("--year-to", type=int, default=current_year)
    args = parser.parse_args(argv)
    try:
        period_start, period_end = resolve_coverage_period(
            year_from=args.year_from,
            year_to=args.year_to,
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
        raise RuntimeError(
            "As propostas históricas requerem PERSISTENCE_MODE=postgres-supabase."
        )
    if persistence_settings.database_url is None:
        raise RuntimeError("Configuração de banco incompleta.")

    repository = PostgresCollectionRepository.from_dsn(
        persistence_settings.database_url
    )
    control = CollectionControl(
        repository=repository,
        source_code=SOURCE_CODE,
        endpoint_code=ENDPOINT_CODE,
        idempotency_key=build_execution_idempotency_key(
            f"transferegov-historical-proposals:{args.year_from}:{args.year_to}"
        ),
        collector_version=TRANSFEREGOV_HISTORICAL_PROPOSAL_COLLECTOR_VERSION,
        parser_version=TRANSFEREGOV_HISTORICAL_PROPOSAL_PARSER_VERSION,
        partition_key=f"historical-proposals:{args.year_from}:{args.year_to}",
        period_start=period_start,
        period_end=period_end,
    )

    def operation() -> HistoricalProposalCollectionSummary:
        catalog = fetch_download_catalog(logger=logging.getLogger(__name__))
        entry = next(
            item for item in catalog.items if item.get("name") == ARCHIVE_NAME
        )
        snapshot = fetch_historical_proposals(
            catalog_entry=entry,
            year_from=args.year_from,
            year_to=args.year_to,
            logger=logging.getLogger(__name__),
        )
        result = TransferegovHistoricalProposalPersistenceService(
            object_store=build_authenticated_object_store(persistence_settings),
            repository=repository,
        ).persist(snapshot)
        return HistoricalProposalCollectionSummary(
            proposals=len(snapshot.items),
            archive_bytes=snapshot.body_size_bytes,
            inserted_records=result.inserted_records,
            existing_records=result.existing_records,
            archive_sha256=result.sha256,
            catalog_etag=snapshot.catalog_etag,
            year_from=args.year_from,
            year_to=args.year_to,
        )

    summary = execute_controlled_historical_proposals(
        control=control,
        operation=operation,
    )
    log_event(
        logging.getLogger(__name__),
        logging.INFO,
        "collector_transferegov_historical_proposals_completed",
        source=SOURCE_CODE,
        proposals=summary.proposals,
        archive_bytes=summary.archive_bytes,
        inserted_records=summary.inserted_records,
        existing_records=summary.existing_records,
        artifact_hash=summary.archive_sha256,
        catalog_etag=summary.catalog_etag,
        year_from=summary.year_from,
        year_to=summary.year_to,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
