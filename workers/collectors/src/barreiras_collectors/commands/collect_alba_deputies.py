"""Preserva a composição da Assembleia Legislativa da Bahia (ADR 0014)."""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from ..collection_control import CollectionOutcome
from ..connectors.alba import (
    ENDPOINT_CODE,
    PROFILE_DELAY_SECONDS,
    PROFILE_ENDPOINT_CODE,
    SOURCE_CODE,
    AlbaError,
    fetch_deputies,
    fetch_profile,
)
from ..connectors.pncp import PncpPage
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import (
    ALBA_COLLECTOR_VERSION,
    ALBA_PARSER_VERSION,
    ALBA_PROFILE_COLLECTOR_VERSION,
    ALBA_PROFILE_PARSER_VERSION,
    AlbaPersistenceService,
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
    snapshot_date = datetime.now(MUNICIPAL_TIMEZONE).date()
    list_control = build_representation_control(
        repository=repository,
        source_code=SOURCE_CODE,
        endpoint_code=ENDPOINT_CODE,
        namespace="alba-deputies-list",
        collector_version=ALBA_COLLECTOR_VERSION,
        parser_version=ALBA_PARSER_VERSION,
        partition_key="snapshot:current-composition",
        snapshot_date=snapshot_date,
    )
    collected_page: PncpPage | None = None
    persistence_service: AlbaPersistenceService | None = None

    def collect_list() -> RepresentationCollectionSummary:
        nonlocal collected_page, persistence_service
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
            return RepresentationCollectionSummary(
                observed_records=0,
                outcome=CollectionOutcome.BLOCKED,
                block_reason="composição estadual não retornada pela fonte",
            )
        result = service.persist(page)
        collected_page = page
        persistence_service = service
        return RepresentationCollectionSummary(
            observed_records=len(page.items),
            outcome=CollectionOutcome.COMPLETE,
            metrics={
                "inserted_records": result.inserted_records,
                "existing_records": result.existing_records,
            },
        )

    list_summary = execute_controlled_representation(
        control=list_control,
        operation=collect_list,
    )
    profile_control = build_representation_control(
        repository=repository,
        source_code=SOURCE_CODE,
        endpoint_code=PROFILE_ENDPOINT_CODE,
        namespace="alba-deputy-profiles",
        collector_version=ALBA_PROFILE_COLLECTOR_VERSION,
        parser_version=ALBA_PROFILE_PARSER_VERSION,
        partition_key="snapshot:current-profiles",
        snapshot_date=snapshot_date,
    )

    def collect_profiles() -> RepresentationCollectionSummary:
        if list_summary.outcome is CollectionOutcome.BLOCKED:
            return RepresentationCollectionSummary(
                observed_records=0,
                outcome=CollectionOutcome.BLOCKED,
                block_reason="lista oficial de deputados não disponível",
            )
        if collected_page is None or persistence_service is None:
            raise RuntimeError("A lista da ALBA terminou sem estado persistível.")
        profiles_succeeded = 0
        profiles_failed = 0
        for index, deputy in enumerate(collected_page.items):
            if index > 0:
                time.sleep(PROFILE_DELAY_SECONDS)
            try:
                profile_page = fetch_profile(deputy, logger=logger)
                persistence_service.persist_profile(profile_page)
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
            deputados=list_summary.observed_records,
            profiles_succeeded=profiles_succeeded,
            profiles_failed=profiles_failed,
        )
        return RepresentationCollectionSummary(
            observed_records=profiles_succeeded,
            outcome=(
                CollectionOutcome.PARTIAL
                if profiles_failed
                else CollectionOutcome.COMPLETE
            ),
            metrics={
                "profiles_expected": list_summary.observed_records,
                "profiles_succeeded": profiles_succeeded,
                "profiles_failed": profiles_failed,
            },
            checkpoint={"remaining_profiles": profiles_failed},
        )

    execute_controlled_representation(
        control=profile_control,
        operation=collect_profiles,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
