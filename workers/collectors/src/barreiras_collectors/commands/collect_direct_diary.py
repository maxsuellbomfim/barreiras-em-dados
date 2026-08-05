"""Coleta as próximas edições do Diário Oficial direto da origem."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable, Sequence
from datetime import date, datetime
from zoneinfo import ZoneInfo

from ..collection_control import (
    CollectionControl,
    CollectionOutcome,
    build_execution_idempotency_key,
)
from ..connectors.direct_diary import (
    ENDPOINT_CODE,
    SOURCE_CODE,
    DirectEdition,
    collect_editions,
)
from ..connectors.gazette_documents import GazetteDocumentClient
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import (
    DIRECT_COLLECTOR_VERSION,
    DirectDiaryPersistenceService,
)
from ..persistence.storage import SupabaseStorageObjectStore
from ..resilience import RetryPolicy
from ..settings import CollectorSettings, PersistenceSettings

MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
# Cortesia com o servidor da prefeitura, alinhada ao endpoint no seed.
DIRECT_REQUESTS_PER_MINUTE = 10


def collect_direct_diary_window(
    *,
    client: GazetteDocumentClient,
    persist: Callable[[DirectEdition], object],
    start_edition: int,
    limit: int,
    today: date,
    logger: logging.Logger,
) -> tuple[int, bool]:
    """Coleta uma janela já protegida pelo controle de execução."""
    return collect_editions(
        client,
        persist,
        start_edition=start_edition,
        limit=limit,
        today=today,
        logger=logger,
    )


def execute_controlled_direct_diary(
    *,
    control: CollectionControl,
    operation: Callable[[], tuple[int, bool, int]],
) -> tuple[int, bool, int]:
    """Abre o controle antes do setup externo e registra a cobertura."""
    with control:
        persisted, cursor_exhausted, next_edition = operation()
        if cursor_exhausted and persisted == 0:
            outcome = CollectionOutcome.EMPTY
        elif cursor_exhausted:
            outcome = CollectionOutcome.COMPLETE
        else:
            outcome = CollectionOutcome.PARTIAL
        control.complete(
            outcome=outcome,
            observed_records=persisted,
            checkpoint={"next_edition": next_edition},
            metrics={
                "persisted_editions": persisted,
                "cursor_exhausted": cursor_exhausted,
            },
        )
    return persisted, cursor_exhausted, next_edition


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
    repository = PostgresCollectionRepository.from_dsn(
        persistence_settings.database_url
    )
    logger = logging.getLogger(__name__)
    today = datetime.now(MUNICIPAL_TIMEZONE).date()
    control = CollectionControl(
        repository=repository,
        source_code=SOURCE_CODE,
        endpoint_code=ENDPOINT_CODE,
        idempotency_key=build_execution_idempotency_key("direct-diary"),
        collector_version=DIRECT_COLLECTOR_VERSION,
        partition_key=f"daily-probe:{today.isoformat()}",
        period_start=today,
        period_end=today,
    )

    def operation() -> tuple[int, bool, int]:
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
        start_edition = repository.next_direct_edition_number(
            collector_settings.direct_diary_first_edition
        )
        persisted, cursor_exhausted = collect_direct_diary_window(
            client=client,
            persist=service.persist,
            start_edition=start_edition,
            limit=collector_settings.direct_diary_max_editions_per_run,
            today=today,
            logger=logger,
        )
        return persisted, cursor_exhausted, start_edition + persisted

    persisted, cursor_exhausted, next_edition = execute_controlled_direct_diary(
        control=control,
        operation=operation,
    )
    log_event(
        logger,
        logging.INFO,
        "collector_direct_diary_completed",
        source=SOURCE_CODE,
        start_edition=next_edition - persisted,
        persisted=persisted,
        cursor_exhausted=cursor_exhausted,
        max_editions_per_run=(
            collector_settings.direct_diary_max_editions_per_run
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
