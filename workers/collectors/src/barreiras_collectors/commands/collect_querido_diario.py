"""Coleta uma janela curta do Querido Diário e preserva o bruto."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from datetime import date

from ..connectors.querido_diario import QueridoDiarioClient
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import QueridoDiarioPersistenceService
from ..persistence.storage import SupabaseStorageObjectStore
from ..resilience import RetryPolicy
from ..settings import CollectorSettings, PersistenceSettings

MAX_WINDOW_DAYS = 7


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preserva no Storage e no PostgreSQL uma janela curta de metadados "
            "do Querido Diário para Barreiras."
        )
    )
    parser.add_argument("--since", type=date.fromisoformat, required=True)
    parser.add_argument("--until", type=date.fromisoformat, required=True)
    parser.add_argument("--page-size", type=int, default=100)
    arguments = parser.parse_args(argv)

    if arguments.since > arguments.until:
        parser.error("--since não pode ser posterior a --until.")
    if (arguments.until - arguments.since).days > MAX_WINDOW_DAYS:
        parser.error(f"A janela inicial não pode exceder {MAX_WINDOW_DAYS} dias.")
    if not 1 <= arguments.page_size <= 100:
        parser.error("--page-size deve estar entre 1 e 100.")

    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()

    try:
        from supabase import create_client
    except ImportError as error:
        raise RuntimeError(
            "Instale a dependência opcional 'storage' para executar a coleta."
        ) from error

    supabase_client = create_client(
        persistence_settings.supabase_url,
        persistence_settings.supabase_secret_key,
    )
    bucket_client = supabase_client.storage.from_(
        persistence_settings.raw_artifacts_bucket
    )
    service = QueridoDiarioPersistenceService(
        object_store=SupabaseStorageObjectStore(bucket_client),
        repository=PostgresCollectionRepository.from_dsn(
            persistence_settings.database_url
        ),
    )
    source = QueridoDiarioClient(
        base_url=collector_settings.querido_diario_base_url,
        territory_id=collector_settings.querido_diario_territory_id,
        requests_per_minute=collector_settings.requests_per_minute,
        timeout_seconds=(
            collector_settings.connect_timeout_seconds
            + collector_settings.read_timeout_seconds
        ),
        retry_policy=RetryPolicy(max_attempts=collector_settings.max_attempts),
    )

    logger = logging.getLogger(__name__)
    pages = 0
    inserted_records = 0
    existing_records = 0
    for page in source.iter_gazette_pages(
        published_since=arguments.since,
        published_until=arguments.until,
        page_size=arguments.page_size,
    ):
        result = service.persist(page)
        pages += 1
        inserted_records += result.inserted_records
        existing_records += result.existing_records
        log_event(
            logger,
            logging.INFO,
            "collector_page_persisted",
            source=page.source_code,
            endpoint=page.endpoint_code,
            artifact_hash=result.sha256,
            object_created=result.object_created,
            inserted_records=result.inserted_records,
            existing_records=result.existing_records,
        )

    log_event(
        logger,
        logging.INFO,
        "collector_window_completed",
        source="querido-diario",
        territory_id=collector_settings.querido_diario_territory_id,
        window_start=arguments.since.isoformat(),
        window_end=arguments.until.isoformat(),
        pages=pages,
        inserted_records=inserted_records,
        existing_records=existing_records,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
