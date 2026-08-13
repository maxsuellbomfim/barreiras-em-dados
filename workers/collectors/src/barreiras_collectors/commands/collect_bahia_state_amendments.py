"""Preserva o catálogo e o ZIP diário de emendas estaduais da Bahia."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from ..collection_control import (
    CollectionControl,
    CollectionOutcome,
    build_execution_idempotency_key,
)
from ..connectors.bahia_state_amendments import (
    ENDPOINT_CODE,
    SOURCE_CODE,
    fetch_state_amendment_archive,
    fetch_state_amendment_catalog,
)
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import (
    BAHIA_STATE_AMENDMENT_ARCHIVE_PARSER_VERSION,
    BAHIA_STATE_AMENDMENT_COLLECTOR_VERSION,
    BahiaStateAmendmentArchivePersistenceService,
    BahiaStateAmendmentCatalogPersistenceService,
)
from ..settings import CollectorSettings, PersistenceSettings
from .pncp_runtime import build_authenticated_object_store

MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")


@dataclass(frozen=True)
class BahiaStateAmendmentCollectionSummary:
    archive_members: int
    archive_rows: int
    unparseable_members: tuple[str, ...]
    archive_bytes: int
    inserted_records: int
    existing_records: int
    catalog_sha256: str
    archive_sha256: str
    resource_last_modified: str
    source_warning_rows: int = 0


def execute_controlled_state_amendments(
    *,
    control: CollectionControl,
    operation: Callable[[], BahiaStateAmendmentCollectionSummary],
) -> BahiaStateAmendmentCollectionSummary:
    """Registra a execução antes da autenticação, do catálogo e do ZIP."""
    with control:
        summary = operation()
        if summary.archive_members != 5:
            raise RuntimeError(
                "A coleta estadual não preservou as cinco views obrigatórias."
            )
        outcome = (
            CollectionOutcome.PARTIAL
            if summary.unparseable_members
            else CollectionOutcome.COMPLETE
        )
        control.complete(
            outcome=outcome,
            observed_records=summary.archive_members,
            checkpoint={
                "archive_members": summary.archive_members,
                "resource_last_modified": summary.resource_last_modified,
                "territorial_scope": "not_available_in_archive",
            },
            metrics={
                "archive_members": summary.archive_members,
                "archive_rows": summary.archive_rows,
                "unparseable_members": list(summary.unparseable_members),
                "source_warning_rows": summary.source_warning_rows,
                "archive_bytes": summary.archive_bytes,
                "inserted_records": summary.inserted_records,
                "existing_records": summary.existing_records,
                "catalog_sha256": summary.catalog_sha256,
                "archive_sha256": summary.archive_sha256,
                "resource_last_modified": summary.resource_last_modified,
                "territorial_scope": "not_available_in_archive",
            },
        )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preserva catálogo e ZIP das emendas estaduais; valida as cinco "
            "views, sem atribuir registros a Barreiras nesta etapa."
        )
    )
    parser.parse_args(argv)
    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    if persistence_settings.mode != "postgres-supabase":
        raise RuntimeError(
            "As emendas estaduais requerem PERSISTENCE_MODE=postgres-supabase."
        )
    if persistence_settings.database_url is None:
        raise RuntimeError("Configuração de banco incompleta.")

    repository = PostgresCollectionRepository.from_dsn(
        persistence_settings.database_url
    )
    collected_on = datetime.now(MUNICIPAL_TIMEZONE).date()
    control = CollectionControl(
        repository=repository,
        source_code=SOURCE_CODE,
        endpoint_code=ENDPOINT_CODE,
        idempotency_key=build_execution_idempotency_key(
            "bahia-state-amendments"
        ),
        collector_version=BAHIA_STATE_AMENDMENT_COLLECTOR_VERSION,
        parser_version=BAHIA_STATE_AMENDMENT_ARCHIVE_PARSER_VERSION,
        partition_key=f"archive-snapshot:{collected_on.isoformat()}",
        period_start=collected_on,
        period_end=collected_on,
    )

    def operation() -> BahiaStateAmendmentCollectionSummary:
        object_store = build_authenticated_object_store(persistence_settings)
        catalog = fetch_state_amendment_catalog(logger=logging.getLogger(__name__))
        catalog_result = BahiaStateAmendmentCatalogPersistenceService(
            object_store=object_store,
            repository=repository,
        ).persist(catalog)
        archive = fetch_state_amendment_archive(
            catalog=catalog,
            logger=logging.getLogger(__name__),
        )
        archive_result = BahiaStateAmendmentArchivePersistenceService(
            object_store=object_store,
            repository=repository,
        ).persist(archive)
        return BahiaStateAmendmentCollectionSummary(
            archive_members=len(archive.items),
            archive_rows=sum(
                int(item["row_count"])
                for item in archive.items
                if item["row_count"] is not None
            ),
            unparseable_members=tuple(
                str(item["member_name"])
                for item in archive.items
                if item["row_count"] is None
            ),
            archive_bytes=archive.body_size_bytes,
            inserted_records=(
                catalog_result.inserted_records + archive_result.inserted_records
            ),
            existing_records=(
                catalog_result.existing_records + archive_result.existing_records
            ),
            catalog_sha256=catalog.body_sha256,
            archive_sha256=archive.body_sha256,
            resource_last_modified=archive.resource_last_modified,
            source_warning_rows=sum(
                int(warnings.get("missing_check_digit_rows", 0))
                for item in archive.items
                if isinstance(
                    warnings := item.get("validation_warnings"),
                    dict,
                )
            ),
        )

    summary = execute_controlled_state_amendments(
        control=control,
        operation=operation,
    )
    log_event(
        logging.getLogger(__name__),
        logging.INFO,
        "collector_bahia_state_amendments_completed",
        source=SOURCE_CODE,
        archive_members=summary.archive_members,
        archive_rows=summary.archive_rows,
        unparseable_members=list(summary.unparseable_members),
        source_warning_rows=summary.source_warning_rows,
        archive_bytes=summary.archive_bytes,
        inserted_records=summary.inserted_records,
        existing_records=summary.existing_records,
        artifact_hash=summary.archive_sha256,
        catalog_hash=summary.catalog_sha256,
        resource_last_modified=summary.resource_last_modified,
        territorial_scope="not_available_in_archive",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
