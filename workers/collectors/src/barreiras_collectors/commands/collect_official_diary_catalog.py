"""Preserva o catálogo estruturado do Diário Oficial de Barreiras."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

from ..connectors.official_diary_catalog import OfficialDiaryCatalogClient
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import OfficialDiaryCatalogPersistenceService
from ..persistence.storage import SupabaseStorageObjectStore
from ..settings import CollectorSettings, PersistenceSettings


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

    repository = PostgresCollectionRepository.from_dsn(
        persistence_settings.database_url
    )
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
    log_event(
        logging.getLogger(__name__),
        logging.INFO,
        "collector_official_diary_catalog_completed",
        source="barreiras-diario-oficial",
        publications=len(snapshot.publications),
        inserted_records=result.inserted_records,
        existing_records=result.existing_records,
        artifact_hash=snapshot.body_sha256,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
