"""Preserva o catálogo estruturado do Diário Oficial de Barreiras."""

from __future__ import annotations

import argparse
import hashlib
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
    pages: int = 1


def execute_controlled_catalog(
    *,
    control: CollectionControl,
    operation: Callable[[], OfficialDiaryCatalogSummary],
) -> OfficialDiaryCatalogSummary:
    """Registra a tentativa antes da autenticação e da consulta oficial."""
    with control:
        summary = operation()
        control.complete(
            outcome=(
                CollectionOutcome.COMPLETE
                if summary.publications
                else CollectionOutcome.EMPTY
            ),
            observed_records=summary.publications,
            checkpoint={"artifact_sha256": summary.artifact_sha256},
            metrics={
                "publications": summary.publications,
                "inserted_records": summary.inserted_records,
                "existing_records": summary.existing_records,
                "pages": summary.pages,
            },
        )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preserva o catálogo oficial com edição, título, resumo e data."
        )
    )
    parser.add_argument("--since", type=date.fromisoformat)
    parser.add_argument("--until", type=date.fromisoformat)
    arguments = parser.parse_args(argv)
    if (arguments.since is None) != (arguments.until is None):
        parser.error("--since e --until devem ser informados juntos.")
    if arguments.since is not None and arguments.since > arguments.until:
        parser.error("--since não pode ser posterior a --until.")
    if (
        arguments.since is not None
        and (arguments.until - arguments.since).days >= 7
    ):
        parser.error("A janela oficial não pode exceder sete dias.")
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
    period_start = arguments.since or today
    period_end = arguments.until or today
    partition_key = (
        f"catalog-window:{period_start.isoformat()}:{period_end.isoformat()}"
        if arguments.since is not None
        else f"catalog-snapshot:{today.isoformat()}"
    )
    control = CollectionControl(
        repository=repository,
        source_code=SOURCE_CODE,
        endpoint_code=ENDPOINT_CODE,
        idempotency_key=build_execution_idempotency_key(
            "official-diary-catalog"
        ),
        collector_version=OFFICIAL_CATALOG_COLLECTOR_VERSION,
        parser_version=PARSER_VERSION,
        partition_key=partition_key,
        period_start=period_start,
        period_end=period_end,
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
        catalog_client = OfficialDiaryCatalogClient(
            timeout_seconds=(
                collector_settings.connect_timeout_seconds
                + collector_settings.read_timeout_seconds
            ),
            max_body_bytes=8 * 1024 * 1024,
        )
        snapshots = (
            catalog_client.iter_window_pages(
                published_since=arguments.since,
                published_until=arguments.until,
            )
            if arguments.since is not None
            else iter((catalog_client.fetch(),))
        )
        publications = inserted_records = existing_records = 0
        artifact_hashes: list[str] = []
        pages = 0
        for snapshot in snapshots:
            result = service.persist(snapshot)
            pages += 1
            publications += len(snapshot.publications)
            inserted_records += result.inserted_records
            existing_records += result.existing_records
            artifact_hashes.append(snapshot.body_sha256)
        manifest = (
            artifact_hashes[0]
            if len(artifact_hashes) == 1
            else hashlib.sha256(
                "\n".join(artifact_hashes).encode("ascii")
            ).hexdigest()
        )
        return OfficialDiaryCatalogSummary(
            publications=publications,
            inserted_records=inserted_records,
            existing_records=existing_records,
            artifact_sha256=manifest,
            pages=pages,
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
        pages=summary.pages,
        artifact_hash=summary.artifact_sha256,
        coverage_status=(
            CollectionOutcome.COMPLETE.value
            if summary.publications
            else CollectionOutcome.EMPTY.value
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
