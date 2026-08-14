"""Preserva o catálogo estruturado do Diário Oficial de Barreiras."""

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
from ..connectors.official_diary_catalog import (
    ENDPOINT_CODE,
    PARSER_VERSION,
    SOURCE_CODE,
    OfficialDiaryCatalogClient,
)
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import (
    OFFICIAL_CATALOG_COLLECTOR_VERSION,
    OfficialDiaryCatalogPersistenceService,
)
from ..persistence.storage import SupabaseStorageObjectStore
from ..settings import CollectorSettings, PersistenceSettings

MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")


@dataclass(frozen=True)
class OfficialDiaryCatalogSummary:
    publications: int
    inserted_records: int
    existing_records: int
    artifact_sha256: str


def execute_controlled_catalog(
    *,
    control: CollectionControl,
    operation: Callable[[], OfficialDiaryCatalogSummary],
) -> OfficialDiaryCatalogSummary:
    """Registra a tentativa antes da autenticação e da consulta oficial."""
    with control:
        summary = operation()
        control.complete(
            outcome=CollectionOutcome.COMPLETE,
            observed_records=summary.publications,
            checkpoint={"artifact_sha256": summary.artifact_sha256},
            metrics={
                "publications": summary.publications,
                "inserted_records": summary.inserted_records,
                "existing_records": summary.existing_records,
            },
        )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preserva o catálogo oficial com edição, título, resumo e data."
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
            "O catálogo oficial requer PERSISTENCE_MODE=postgres-supabase."
        )
    required = (
        persistence_settings.database_url,
        persistence_settings.supabase_url,
        persistence_settings.supabase_publishable_key,
        persistence_settings.supabase_workload_email,
        persistence_settings.supabase_workload_password,
        persistence_settings.raw_artifacts_bucket,
    )
    if any(value is None for value in required):
        raise RuntimeError(
            "Configuração de nuvem incompleta para o catálogo oficial."
        )

    repository = PostgresCollectionRepository.from_dsn(
        persistence_settings.database_url
    )
    today = datetime.now(MUNICIPAL_TIMEZONE).date()
    control = CollectionControl(
        repository=repository,
        source_code=SOURCE_CODE,
        endpoint_code=ENDPOINT_CODE,
        idempotency_key=build_execution_idempotency_key(
            "official-diary-catalog"
        ),
        collector_version=OFFICIAL_CATALOG_COLLECTOR_VERSION,
        parser_version=PARSER_VERSION,
        partition_key=f"catalog-snapshot:{today.isoformat()}",
        period_start=today,
        period_end=today,
    )

    def operation() -> OfficialDiaryCatalogSummary:
        try:
            from supabase import create_client
        except ImportError as error:
            raise RuntimeError(
                "Instale a dependência opcional 'storage' para coletar."
            ) from error

        client = create_client(
            persistence_settings.supabase_url,
            persistence_settings.supabase_publishable_key,
        )
        try:
            authentication = client.auth.sign_in_with_password(
                {
                    "email": persistence_settings.supabase_workload_email,
                    "password": persistence_settings.supabase_workload_password,
                }
            )
        except Exception as error:
            raise RuntimeError(
                "Falha ao autenticar a identidade técnica do Storage."
            ) from error
        if authentication.session is None or authentication.user is None:
            raise RuntimeError("O Storage não forneceu uma sessão autenticada.")

        service = OfficialDiaryCatalogPersistenceService(
            object_store=SupabaseStorageObjectStore(
                client.storage.from_(persistence_settings.raw_artifacts_bucket)
            ),
            repository=repository,
        )
        snapshot = OfficialDiaryCatalogClient(
            timeout_seconds=(
                collector_settings.connect_timeout_seconds
                + collector_settings.read_timeout_seconds
            ),
            max_body_bytes=8 * 1024 * 1024,
        ).fetch()
        result = service.persist(snapshot)
        return OfficialDiaryCatalogSummary(
            publications=len(snapshot.publications),
            inserted_records=result.inserted_records,
            existing_records=result.existing_records,
            artifact_sha256=snapshot.body_sha256,
        )

    summary = execute_controlled_catalog(control=control, operation=operation)
    log_event(
        logging.getLogger(__name__),
        logging.INFO,
        "collector_official_diary_catalog_completed",
        source=SOURCE_CODE,
        publications=summary.publications,
        inserted_records=summary.inserted_records,
        existing_records=summary.existing_records,
        artifact_hash=summary.artifact_sha256,
        coverage_status=CollectionOutcome.COMPLETE.value,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
