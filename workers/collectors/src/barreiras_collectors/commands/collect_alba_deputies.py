"""Preserva a composição da Assembleia Legislativa da Bahia (ADR 0014)."""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Sequence

from ..connectors.alba import (
    PROFILE_DELAY_SECONDS,
    SOURCE_CODE,
    AlbaError,
    fetch_deputies,
    fetch_profile,
)
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import AlbaPersistenceService
from ..persistence.storage import SupabaseStorageObjectStore
from ..settings import CollectorSettings, PersistenceSettings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preserva a lista de deputados estaduais publicada pela "
            "Assembleia, com o identificador oficial de cada parlamentar."
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
            "A coleta da Assembleia requer PERSISTENCE_MODE=postgres-supabase."
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
    service = AlbaPersistenceService(
        object_store=SupabaseStorageObjectStore(
            supabase_client.storage.from_(
                persistence_settings.raw_artifacts_bucket
            )
        ),
        repository=repository,
    )

    page = fetch_deputies(logger=logger)
    if page is None:
        log_event(
            logger,
            logging.WARNING,
            "collector_alba_empty",
            source=SOURCE_CODE,
        )
        return 0

    result = service.persist(page)
    profiles_succeeded = 0
    profiles_failed = 0
    for index, deputy in enumerate(page.items):
        if index > 0:
            time.sleep(PROFILE_DELAY_SECONDS)
        try:
            profile_page = fetch_profile(deputy, logger=logger)
            service.persist_profile(profile_page)
            profiles_succeeded += 1
        except AlbaError as error:
            profiles_failed += 1
            log_event(
                logger,
                logging.WARNING,
                "collector_alba_profile_failed",
                source=SOURCE_CODE,
                identifier=deputy.get("id_alba"),
                error_type=type(error).__name__,
            )
    log_event(
        logger,
        logging.INFO,
        "collector_alba_completed",
        source=SOURCE_CODE,
        deputados=len(page.items),
        inserted_records=result.inserted_records,
        existing_records=result.existing_records,
        profiles_succeeded=profiles_succeeded,
        profiles_failed=profiles_failed,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
