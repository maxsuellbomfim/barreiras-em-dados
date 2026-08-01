"""Preserva a composição da Câmara Municipal de Barreiras (ADR 0014)."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

from ..connectors.camara_municipal import SOURCE_CODE, fetch_councillors
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import VereadoresPersistenceService
from ..persistence.storage import SupabaseStorageObjectStore
from ..settings import CollectorSettings, PersistenceSettings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preserva a lista de vereadores publicada pela Câmara "
            "Municipal, com nome, partido, mandatos e foto oficial."
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
    logger = logging.getLogger(__name__)
    if persistence_settings.mode != "postgres-supabase":
        raise RuntimeError(
            "A coleta de vereadores requer PERSISTENCE_MODE=postgres-supabase."
        )
    if (
        persistence_settings.database_url is None
        or persistence_settings.supabase_url is None
        or persistence_settings.supabase_publishable_key is None
        or persistence_settings.supabase_workload_email is None
        or persistence_settings.supabase_workload_password is None
        or persistence_settings.raw_artifacts_bucket is None
    ):
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
    try:
        authentication = supabase_client.auth.sign_in_with_password(
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
    service = VereadoresPersistenceService(
        object_store=SupabaseStorageObjectStore(
            supabase_client.storage.from_(
                persistence_settings.raw_artifacts_bucket
            )
        ),
        repository=repository,
    )

    page = fetch_councillors(logger=logger)
    if page is None:
        log_event(
            logger,
            logging.WARNING,
            "collector_vereadores_empty",
            source=SOURCE_CODE,
        )
        return 0

    result = service.persist(page)
    log_event(
        logger,
        logging.INFO,
        "collector_vereadores_completed",
        source=SOURCE_CODE,
        vereadores=len(page.items),
        inserted_records=result.inserted_records,
        existing_records=result.existing_records,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
