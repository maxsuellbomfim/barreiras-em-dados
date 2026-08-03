"""Preserva prefeito, vice e secretarias publicados pela Prefeitura."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

from ..connectors.municipal_executive import fetch_executive_profiles
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import MunicipalExecutivePersistenceService
from ..persistence.storage import SupabaseStorageObjectStore
from ..settings import CollectorSettings, PersistenceSettings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preserva os perfis oficiais do Executivo municipal de Barreiras."
    )
    parser.parse_args(argv)
    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    logger = logging.getLogger(__name__)
    if persistence_settings.mode != "postgres-supabase":
        raise RuntimeError(
            "A coleta do Executivo requer PERSISTENCE_MODE=postgres-supabase."
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
        raise RuntimeError("Configuração de nuvem incompleta.")
    try:
        from supabase import create_client
    except ImportError as error:
        raise RuntimeError(
            "Instale a dependência opcional 'storage' para coletar."
        ) from error

    supabase_client = create_client(
        persistence_settings.supabase_url,
        persistence_settings.supabase_publishable_key,
    )
    authentication = supabase_client.auth.sign_in_with_password(
        {
            "email": persistence_settings.supabase_workload_email,
            "password": persistence_settings.supabase_workload_password,
        }
    )
    if authentication.session is None or authentication.user is None:
        raise RuntimeError("O Storage não forneceu uma sessão autenticada.")

    repository = PostgresCollectionRepository.from_dsn(
        persistence_settings.database_url
    )
    service = MunicipalExecutivePersistenceService(
        object_store=SupabaseStorageObjectStore(
            supabase_client.storage.from_(persistence_settings.raw_artifacts_bucket)
        ),
        repository=repository,
    )
    page = fetch_executive_profiles(logger=logger)
    result = service.persist(page)
    log_event(
        logger,
        logging.INFO,
        "collector_municipal_executive_completed",
        source="prefeitura-barreiras",
        profiles=len(page.items),
        inserted_records=result.inserted_records,
        existing_records=result.existing_records,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
