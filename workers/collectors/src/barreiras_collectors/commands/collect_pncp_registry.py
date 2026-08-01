"""Preserva o cadastro do PNCP (órgão e unidades) como bruto verificado."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

from ..connectors.pncp import (
    REGISTRY_RESOURCES,
    SOURCE_CODE,
    fetch_registry_snapshot,
)
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import PncpRegistryPersistenceService
from ..persistence.storage import SupabaseStorageObjectStore
from ..settings import CollectorSettings, PersistenceSettings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preserva as respostas do cadastro do PNCP para Barreiras como "
            "artefatos brutos endereçados por hash."
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
            "A coleta PNCP requer PERSISTENCE_MODE=postgres-supabase."
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

    service = PncpRegistryPersistenceService(
        object_store=SupabaseStorageObjectStore(
            supabase_client.storage.from_(
                persistence_settings.raw_artifacts_bucket
            )
        ),
        repository=PostgresCollectionRepository.from_dsn(
            persistence_settings.database_url
        ),
    )

    logger = logging.getLogger(__name__)
    preserved = 0
    for resource, url in REGISTRY_RESOURCES:
        snapshot = fetch_registry_snapshot(resource, url, logger=logger)
        result = service.persist(snapshot)
        preserved += 1
        log_event(
            logger,
            logging.INFO,
            "collector_pncp_snapshot_persisted",
            source=SOURCE_CODE,
            resource=resource,
            artifact_hash=snapshot.body_sha256,
            created=result.created,
        )

    log_event(
        logger,
        logging.INFO,
        "collector_pncp_registry_completed",
        source=SOURCE_CODE,
        resources=preserved,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
