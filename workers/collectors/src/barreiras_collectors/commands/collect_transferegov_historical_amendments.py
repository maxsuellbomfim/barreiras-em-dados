"""Preserva emendas históricas ligadas às propostas comprovadas de Barreiras."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from ..collection_control import (
    CollectionControl,
    CollectionOutcome,
    build_execution_idempotency_key,
)
from ..connectors.transferegov_download_catalog import fetch_download_catalog
from ..connectors.transferegov_historical_amendments import (
    ARCHIVE_NAME,
    ENDPOINT_CODE,
    SOURCE_CODE,
    fetch_historical_amendments,
)
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import (
    TRANSFEREGOV_HISTORICAL_AMENDMENT_COLLECTOR_VERSION,
    TRANSFEREGOV_HISTORICAL_AMENDMENT_PARSER_VERSION,
    TransferegovHistoricalAmendmentPersistenceService,
)
from ..settings import CollectorSettings, PersistenceSettings
from .collect_transferegov_historical_proposals import resolve_coverage_period
from .pncp_runtime import build_authenticated_object_store

MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
EXECUTION_NAMESPACE = "transferegov-historical-amendments"


@dataclass(frozen=True)
class HistoricalAmendmentCollectionSummary:
    amendments: int
    matched_proposals: int
    proposal_scope: int
    archive_bytes: int
    inserted_records: int
    existing_records: int
    archive_sha256: str
    catalog_etag: str
    year_from: int
    year_to: int


def build_historical_amendments_execution_key(
    *, environment: Mapping[str, str] | None = None
) -> str:
    return build_execution_idempotency_key(
        EXECUTION_NAMESPACE,
        environment=environment,
    )


def execute_controlled_historical_amendments(
    *,
    control: CollectionControl,
    operation: Callable[[], HistoricalAmendmentCollectionSummary],
) -> HistoricalAmendmentCollectionSummary:
    """Nunca classifica ausência da dependência como cobertura vazia."""
    with control:
        summary = operation()
        if summary.proposal_scope < 1:
            raise RuntimeError(
                "Não há propostas históricas preservadas para recortar as emendas."
            )
        control.complete(
            outcome=(
                CollectionOutcome.COMPLETE
                if summary.amendments > 0
                else CollectionOutcome.EMPTY
            ),
            observed_records=summary.amendments,
            checkpoint={
                "catalog_etag": summary.catalog_etag,
                "archive_sha256": summary.archive_sha256,
                "year_from": summary.year_from,
                "year_to": summary.year_to,
                "proposal_scope": summary.proposal_scope,
            },
            metrics={
                "amendments": summary.amendments,
                "matched_proposals": summary.matched_proposals,
                "proposal_scope": summary.proposal_scope,
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
    parser = argparse.ArgumentParser(
        description=(
            "Preserva siconv_emenda.zip e materializa somente emendas ligadas "
            "às propostas históricas comprovadas de Barreiras."
        )
    )
    parser.add_argument("--year-from", type=int, default=2021)
    parser.add_argument("--year-to", type=int, default=collected_on.year)
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
            "As emendas históricas requerem PERSISTENCE_MODE=postgres-supabase."
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
        idempotency_key=build_historical_amendments_execution_key(),
        collector_version=TRANSFEREGOV_HISTORICAL_AMENDMENT_COLLECTOR_VERSION,
        parser_version=TRANSFEREGOV_HISTORICAL_AMENDMENT_PARSER_VERSION,
        partition_key=f"historical-amendments:{args.year_from}:{args.year_to}",
        period_start=period_start,
        period_end=period_end,
    )

    def operation() -> HistoricalAmendmentCollectionSummary:
        proposal_ids = repository.historical_proposal_ids(
            year_from=args.year_from,
            year_to=args.year_to,
        )
        if not proposal_ids:
            raise RuntimeError(
                "Não há propostas históricas preservadas para recortar as emendas."
            )
        catalog = fetch_download_catalog(logger=logging.getLogger(__name__))
        entry = next(
            (item for item in catalog.items if item.get("name") == ARCHIVE_NAME),
            None,
        )
        if entry is None:
            raise RuntimeError("O catálogo oficial não publicou siconv_emenda.zip.")
        snapshot = fetch_historical_amendments(
            catalog_entry=entry,
            proposal_ids=proposal_ids,
            logger=logging.getLogger(__name__),
        )
        result = TransferegovHistoricalAmendmentPersistenceService(
            object_store=build_authenticated_object_store(persistence_settings),
            repository=repository,
        ).persist(snapshot)
        matched_proposals = len(
            {str(item["id_proposta"]) for item in snapshot.items}
        )
        return HistoricalAmendmentCollectionSummary(
            amendments=len(snapshot.items),
            matched_proposals=matched_proposals,
            proposal_scope=len(proposal_ids),
            archive_bytes=snapshot.body_size_bytes,
            inserted_records=result.inserted_records,
            existing_records=result.existing_records,
            archive_sha256=result.sha256,
            catalog_etag=snapshot.catalog_etag,
            year_from=args.year_from,
            year_to=args.year_to,
        )

    summary = execute_controlled_historical_amendments(
        control=control,
        operation=operation,
    )
    log_event(
        logging.getLogger(__name__),
        logging.INFO,
        "collector_transferegov_historical_amendments_completed",
        source=SOURCE_CODE,
        amendments=summary.amendments,
        matched_proposals=summary.matched_proposals,
        proposal_scope=summary.proposal_scope,
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
