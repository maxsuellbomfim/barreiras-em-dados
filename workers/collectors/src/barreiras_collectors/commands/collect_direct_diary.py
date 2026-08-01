"""Coleta as próximas edições do Diário Oficial direto da origem."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from ..connectors.direct_diary import SOURCE_CODE, collect_editions
from ..connectors.gazette_documents import GazetteDocumentClient
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import DirectDiaryPersistenceService
from ..persistence.storage import SupabaseStorageObjectStore
from ..resilience import RetryPolicy
from ..settings import CollectorSettings, PersistenceSettings

MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
# Cortesia com o servidor da prefeitura, alinhada ao endpoint no seed.
DIRECT_REQUESTS_PER_MINUTE = 10


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Sonda as próximas edições do Diário Oficial de Barreiras a "
            "partir do cursor derivado do banco e preserva cada PDF por hash."
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
            "A coleta direta requer PERSISTENCE_MODE=postgres-supabase."
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

    bucket_client = supabase_client.storage.from_(
        persistence_settings.raw_artifacts_bucket
    )
    repository = PostgresCollectionRepository.from_dsn(
        persistence_settings.database_url
    )
    service = DirectDiaryPersistenceService(
        object_store=SupabaseStorageObjectStore(bucket_client),
        repository=repository,
    )
    client = GazetteDocumentClient(
        max_document_bytes=collector_settings.max_document_bytes,
        requests_per_minute=DIRECT_REQUESTS_PER_MINUTE,
        timeout_seconds=(
            collector_settings.connect_timeout_seconds
            + collector_settings.read_timeout_seconds
        ),
        retry_policy=RetryPolicy(max_attempts=collector_settings.max_attempts),
    )

    logger = logging.getLogger(__name__)
    start_edition = repository.next_direct_edition_number(
        collector_settings.direct_diary_first_edition
    )
    today = datetime.now(MUNICIPAL_TIMEZONE).date()
    persisted, cursor_exhausted = collect_editions(
        client,
        service.persist,
        start_edition=start_edition,
        limit=collector_settings.direct_diary_max_editions_per_run,
        today=today,
        logger=logger,
    )
    log_event(
        logger,
        logging.INFO,
        "collector_direct_diary_completed",
        source=SOURCE_CODE,
        start_edition=start_edition,
        persisted=persisted,
        cursor_exhausted=cursor_exhausted,
        max_editions_per_run=(
            collector_settings.direct_diary_max_editions_per_run
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
