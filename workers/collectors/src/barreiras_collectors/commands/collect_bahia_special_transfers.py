"""Preserva catálogo e ZIP oficial de Transferências Especiais da Bahia."""

from __future__ import annotations

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
from ..connectors.bahia_special_transfers import (
    ENDPOINT_CODE,
    SOURCE_CODE,
    fetch_special_transfer_archive,
    fetch_special_transfer_catalog,
)
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import (
    BAHIA_SPECIAL_TRANSFER_ARCHIVE_PARSER_VERSION,
    BAHIA_SPECIAL_TRANSFER_COLLECTOR_VERSION,
    BahiaSpecialTransferArchivePersistenceService,
    BahiaSpecialTransferCatalogPersistenceService,
)
from ..settings import CollectorSettings, PersistenceSettings
from .pncp_runtime import build_authenticated_object_store

MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")


@dataclass(frozen=True)
class BahiaSpecialTransferCollectionSummary:
    archive_members: int
    archive_rows: int
    source_warning_rows: int
    archive_bytes: int
    inserted_records: int
    existing_records: int
    catalog_sha256: str
    archive_sha256: str
    resource_last_modified: str


def execute_controlled_special_transfers(
    *,
    control: CollectionControl,
    operation: Callable[[], BahiaSpecialTransferCollectionSummary],
) -> BahiaSpecialTransferCollectionSummary:
    """Registra a execução antes de autenticar ou baixar a fonte."""
    with control:
        summary = operation()
        if summary.archive_members != 5:
            raise RuntimeError(
                "A coleta não preservou as cinco views obrigatórias."
            )
        control.complete(
            outcome=CollectionOutcome.COMPLETE,
            observed_records=summary.archive_members,
            checkpoint={
                "archive_members": summary.archive_members,
                "resource_last_modified": summary.resource_last_modified,
                "territorial_scope": "payment_object_text_only",
                "public_projection": "blocked_pending_deterministic_reconciliation",
            },
            metrics={
                "archive_members": summary.archive_members,
                "archive_rows": summary.archive_rows,
                "source_warning_rows": summary.source_warning_rows,
                "archive_bytes": summary.archive_bytes,
                "inserted_records": summary.inserted_records,
                "existing_records": summary.existing_records,
                "catalog_sha256": summary.catalog_sha256,
                "archive_sha256": summary.archive_sha256,
                "resource_last_modified": summary.resource_last_modified,
                "restricted_identifier_column": True,
                "raw_visibility": "private",
            },
        )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    if argv:
        raise SystemExit("Este coletor não aceita argumentos.")
    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    if persistence_settings.mode != "postgres-supabase":
        raise RuntimeError(
            "Transferências especiais requerem PERSISTENCE_MODE=postgres-supabase."
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
            "bahia-special-transfers"
        ),
        collector_version=BAHIA_SPECIAL_TRANSFER_COLLECTOR_VERSION,
        parser_version=BAHIA_SPECIAL_TRANSFER_ARCHIVE_PARSER_VERSION,
        partition_key=f"archive-snapshot:{collected_on.isoformat()}",
        period_start=collected_on,
        period_end=collected_on,
    )

    def operation() -> BahiaSpecialTransferCollectionSummary:
        object_store = build_authenticated_object_store(persistence_settings)
        catalog = fetch_special_transfer_catalog(logger=logging.getLogger(__name__))
        catalog_result = BahiaSpecialTransferCatalogPersistenceService(
            object_store=object_store,
            repository=repository,
        ).persist(catalog)
        archive = fetch_special_transfer_archive(
            catalog=catalog,
            logger=logging.getLogger(__name__),
        )
        archive_result = BahiaSpecialTransferArchivePersistenceService(
            object_store=object_store,
            repository=repository,
        ).persist(archive)
        return BahiaSpecialTransferCollectionSummary(
            archive_members=len(archive.items),
            archive_rows=sum(int(item["row_count"]) for item in archive.items),
            source_warning_rows=sum(
                int(warnings.get("missing_check_digit_rows", 0))
                for item in archive.items
                if isinstance(warnings := item.get("validation_warnings"), dict)
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
        )

    summary = execute_controlled_special_transfers(
        control=control,
        operation=operation,
    )
    log_event(
        logging.getLogger(__name__),
        logging.INFO,
        "collector_bahia_special_transfers_completed",
        source=SOURCE_CODE,
        archive_members=summary.archive_members,
        archive_rows=summary.archive_rows,
        source_warning_rows=summary.source_warning_rows,
        archive_bytes=summary.archive_bytes,
        inserted_records=summary.inserted_records,
        existing_records=summary.existing_records,
        artifact_hash=summary.archive_sha256,
        catalog_hash=summary.catalog_sha256,
        resource_last_modified=summary.resource_last_modified,
        territorial_scope="payment_object_text_only",
        public_projection="blocked_pending_deterministic_reconciliation",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
