"""Preserva a execução federal de emendas regionalizada para Barreiras."""

from __future__ import annotations

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
from ..connectors.cgu_federal_amendments import (
    ENDPOINT_CODE,
    SOURCE_CODE,
    fetch_cgu_federal_amendments,
)
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import (
    CGU_FEDERAL_AMENDMENT_COLLECTOR_VERSION,
    CGU_FEDERAL_AMENDMENT_PARSER_VERSION,
    CGUFederalAmendmentPersistenceService,
)
from ..settings import CollectorSettings, PersistenceSettings
from .pncp_runtime import build_authenticated_object_store

MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
EXECUTION_NAMESPACE = "cgu-federal-amendments"


@dataclass(frozen=True)
class CGUFederalAmendmentCollectionSummary:
    amendments: int
    amendment_codes: int
    authors: int
    archive_bytes: int
    inserted_records: int
    existing_records: int
    archive_sha256: str
    source_etag: str
    first_fiscal_year: int
    last_fiscal_year: int


def build_cgu_execution_key(
    *, environment: Mapping[str, str] | None = None
) -> str:
    return build_execution_idempotency_key(
        EXECUTION_NAMESPACE,
        environment=environment,
    )


def execute_controlled_cgu_collection(
    *,
    control: CollectionControl,
    operation: Callable[[], CGUFederalAmendmentCollectionSummary],
) -> CGUFederalAmendmentCollectionSummary:
    with control:
        summary = operation()
        control.complete(
            outcome=(
                CollectionOutcome.COMPLETE
                if summary.amendments > 0
                else CollectionOutcome.EMPTY
            ),
            observed_records=summary.amendments,
            checkpoint={
                "archive_sha256": summary.archive_sha256,
                "source_etag": summary.source_etag,
                "first_fiscal_year": summary.first_fiscal_year,
                "last_fiscal_year": summary.last_fiscal_year,
            },
            metrics={
                "amendments": summary.amendments,
                "amendment_codes": summary.amendment_codes,
                "authors": summary.authors,
                "archive_bytes": summary.archive_bytes,
                "inserted_records": summary.inserted_records,
                "existing_records": summary.existing_records,
                "archive_sha256": summary.archive_sha256,
                "source_etag": summary.source_etag,
                "first_fiscal_year": summary.first_fiscal_year,
                "last_fiscal_year": summary.last_fiscal_year,
            },
        )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    collected_on = datetime.now(MUNICIPAL_TIMEZONE).date()
    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    if persistence_settings.mode != "postgres-supabase":
        raise RuntimeError(
            "As emendas federais requerem PERSISTENCE_MODE=postgres-supabase."
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
        idempotency_key=build_cgu_execution_key(),
        collector_version=CGU_FEDERAL_AMENDMENT_COLLECTOR_VERSION,
        parser_version=CGU_FEDERAL_AMENDMENT_PARSER_VERSION,
        partition_key="federal-amendments:all-years:barreiras-2903201",
        period_start=date(2014, 1, 1),
        period_end=collected_on,
    )

    def operation() -> CGUFederalAmendmentCollectionSummary:
        snapshot = fetch_cgu_federal_amendments(
            logger=logging.getLogger(__name__)
        )
        result = CGUFederalAmendmentPersistenceService(
            object_store=build_authenticated_object_store(persistence_settings),
            repository=repository,
        ).persist(snapshot)
        return CGUFederalAmendmentCollectionSummary(
            amendments=len(snapshot.items),
            amendment_codes=len(
                {str(item["amendment_code"]) for item in snapshot.items}
            ),
            authors=len({str(item["author_name"]) for item in snapshot.items}),
            archive_bytes=snapshot.body_size_bytes,
            inserted_records=result.inserted_records,
            existing_records=result.existing_records,
            archive_sha256=result.sha256,
            source_etag=snapshot.source_etag,
            first_fiscal_year=snapshot.first_fiscal_year,
            last_fiscal_year=snapshot.last_fiscal_year,
        )

    summary = execute_controlled_cgu_collection(
        control=control,
        operation=operation,
    )
    log_event(
        logging.getLogger(__name__),
        logging.INFO,
        "collector_cgu_federal_amendments_completed",
        source=SOURCE_CODE,
        amendments=summary.amendments,
        amendment_codes=summary.amendment_codes,
        authors=summary.authors,
        archive_bytes=summary.archive_bytes,
        inserted_records=summary.inserted_records,
        existing_records=summary.existing_records,
        artifact_hash=summary.archive_sha256,
        source_etag=summary.source_etag,
        first_fiscal_year=summary.first_fiscal_year,
        last_fiscal_year=summary.last_fiscal_year,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
