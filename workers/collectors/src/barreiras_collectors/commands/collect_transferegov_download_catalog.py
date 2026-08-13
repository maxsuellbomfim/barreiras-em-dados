"""Preserva o catálogo dos downloads históricos oficiais do Transferegov."""

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
from ..connectors.transferegov_download_catalog import (
    ENDPOINT_CODE,
    SOURCE_CODE,
    fetch_download_catalog,
)
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import (
    TRANSFEREGOV_DOWNLOAD_CATALOG_COLLECTOR_VERSION,
    TRANSFEREGOV_DOWNLOAD_CATALOG_PARSER_VERSION,
    TransferegovDownloadCatalogPersistenceService,
)
from ..settings import CollectorSettings, PersistenceSettings
from .pncp_runtime import build_authenticated_object_store

MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")


@dataclass(frozen=True)
class TransferegovDownloadCatalogSummary:
    selected_files: int
    selected_bytes: int
    inserted_records: int
    existing_records: int
    artifact_sha256: str


def execute_controlled_catalog(
    *,
    control: CollectionControl,
    operation: Callable[[], TransferegovDownloadCatalogSummary],
) -> TransferegovDownloadCatalogSummary:
    """Abre a execução antes de autenticar ou chamar a fonte."""
    with control:
        summary = operation()
        control.complete(
            outcome=CollectionOutcome.COMPLETE,
            observed_records=summary.selected_files,
            checkpoint={"selected_files": summary.selected_files},
            metrics={
                "selected_files": summary.selected_files,
                "selected_bytes": summary.selected_bytes,
                "inserted_records": summary.inserted_records,
                "existing_records": summary.existing_records,
                "artifact_sha256": summary.artifact_sha256,
            },
        )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preserva o XML oficial que cataloga os arquivos históricos do "
            "Transferegov; não baixa os ZIPs nesta etapa."
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
            "O catálogo Transferegov requer PERSISTENCE_MODE=postgres-supabase."
        )
    if persistence_settings.database_url is None:
        raise RuntimeError("Configuração de banco incompleta.")

    repository = PostgresCollectionRepository.from_dsn(
        persistence_settings.database_url
    )
    today = datetime.now(MUNICIPAL_TIMEZONE).date()
    control = CollectionControl(
        repository=repository,
        source_code=SOURCE_CODE,
        endpoint_code=ENDPOINT_CODE,
        idempotency_key=build_execution_idempotency_key(
            "transferegov-download-catalog"
        ),
        collector_version=TRANSFEREGOV_DOWNLOAD_CATALOG_COLLECTOR_VERSION,
        parser_version=TRANSFEREGOV_DOWNLOAD_CATALOG_PARSER_VERSION,
        partition_key=f"catalog-snapshot:{today.isoformat()}",
        period_start=today,
        period_end=today,
    )

    def operation() -> TransferegovDownloadCatalogSummary:
        snapshot = fetch_download_catalog(logger=logging.getLogger(__name__))
        result = TransferegovDownloadCatalogPersistenceService(
            object_store=build_authenticated_object_store(persistence_settings),
            repository=repository,
        ).persist(snapshot)
        return TransferegovDownloadCatalogSummary(
            selected_files=len(snapshot.items),
            selected_bytes=sum(int(item["byte_size"]) for item in snapshot.items),
            inserted_records=result.inserted_records,
            existing_records=result.existing_records,
            artifact_sha256=result.sha256,
        )

    summary = execute_controlled_catalog(control=control, operation=operation)
    log_event(
        logging.getLogger(__name__),
        logging.INFO,
        "collector_transferegov_download_catalog_completed",
        source=SOURCE_CODE,
        selected_files=summary.selected_files,
        selected_bytes=summary.selected_bytes,
        inserted_records=summary.inserted_records,
        existing_records=summary.existing_records,
        artifact_hash=summary.artifact_sha256,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
