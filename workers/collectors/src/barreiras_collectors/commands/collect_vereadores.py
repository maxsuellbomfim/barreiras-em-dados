"""Preserva a composição da Câmara Municipal de Barreiras (ADR 0014)."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from ..collection_control import CollectionOutcome
from ..connectors.camara_municipal import (
    ENDPOINT_CODE,
    SOURCE_CODE,
    fetch_councillors,
)
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import (
    VEREADORES_COLLECTOR_VERSION,
    VEREADORES_PARSER_VERSION,
    VereadoresPersistenceService,
)
from ..persistence.storage import SupabaseStorageObjectStore
from ..settings import CollectorSettings, PersistenceSettings
from .representation_control import (
    RepresentationCollectionSummary,
    build_representation_control,
    execute_controlled_representation,
)

MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")


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

    repository = PostgresCollectionRepository.from_dsn(
        persistence_settings.database_url
    )
    control = build_representation_control(
        repository=repository,
        source_code=SOURCE_CODE,
        endpoint_code=ENDPOINT_CODE,
        namespace="camara-municipal-vereadores",
        collector_version=VEREADORES_COLLECTOR_VERSION,
        parser_version=VEREADORES_PARSER_VERSION,
        partition_key="snapshot:current-legislature",
        snapshot_date=datetime.now(MUNICIPAL_TIMEZONE).date(),
    )

    def operation() -> RepresentationCollectionSummary:
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
            return RepresentationCollectionSummary(
                observed_records=0,
                outcome=CollectionOutcome.BLOCKED,
                block_reason="composição municipal não retornada pela fonte",
            )

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
        return RepresentationCollectionSummary(
            observed_records=len(page.items),
            outcome=CollectionOutcome.COMPLETE,
            metrics={
                "inserted_records": result.inserted_records,
                "existing_records": result.existing_records,
            },
        )

    execute_controlled_representation(control=control, operation=operation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
