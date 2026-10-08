"""Backfill das edições antigas do Diário Oficial que o cursor nunca sondou.

A sonda direta só anda para a frente a partir da última edição preservada;
as edições 3353-3988 (meados de 2021 a início de 2023) existem no site da
Prefeitura e nunca foram buscadas. Cada execução pega os próximos números
faltantes do intervalo, tenta os anos candidatos e registra no checkpoint
os números sem PDF em nenhum ano, para não sondá-los de novo.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from datetime import date

from ..collection_control import (
    CollectionControl,
    CollectionOutcome,
    build_execution_idempotency_key,
)
from ..connectors.direct_diary import (
    DIRECT_DIARY_ALLOWED_HOSTS,
    ENDPOINT_CODE,
    SOURCE_CODE,
    collect_missing_editions,
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
from .collect_direct_diary import DIRECT_REQUESTS_PER_MINUTE


def parse_years(value: str) -> tuple[int, ...]:
    years = tuple(int(part) for part in value.split(",") if part.strip())
    if not years or any(year < 2000 or year > 2100 for year in years):
        raise ValueError("--years deve listar anos entre 2000 e 2100.")
    return years


def run_backfill(
    *,
    repository: PostgresCollectionRepository,
    control: CollectionControl,
    first_edition: int,
    last_edition: int,
    years: tuple[int, ...],
    limit: int,
    collect,
    logger: logging.Logger,
) -> dict[str, object]:
    """Abre o controle antes de qualquer chamada externa e fecha a cobertura."""
    partition_key = f"backfill:{first_edition}-{last_edition}"
    with control:
        candidates, known_missing = repository.missing_direct_editions(
            first_edition=first_edition,
            last_edition=last_edition,
            partition_key=partition_key,
            limit=limit,
        )
        result = collect(editions=candidates)
        missing = tuple(sorted(set(known_missing) | set(result.not_found)))
        remaining = len(candidates) - result.persisted - len(result.not_found)
        exhausted = not result.deferred and len(candidates) < limit
        if exhausted:
            outcome = CollectionOutcome.COMPLETE
        else:
            outcome = CollectionOutcome.PARTIAL
        preserved = (
            (last_edition - first_edition + 1)
            - len(missing)
            - (remaining if exhausted else 0)
        )
        checkpoint = {
            "next_edition": (candidates[-1] + 1) if candidates else last_edition + 1,
            "missing_editions": list(missing),
            "years": list(years),
        }
        control.complete(
            outcome=outcome,
            observed_records=max(0, preserved) if exhausted else result.persisted,
            checkpoint=checkpoint,
            metrics={
                "persisted_editions": result.persisted,
                "not_found_editions": list(result.not_found),
                "deferred": result.deferred,
                "candidates": list(candidates),
            },
        )
    log_event(
        logger,
        logging.INFO,
        "collector_direct_diary_backfill_completed",
        source=SOURCE_CODE,
        partition_key=partition_key,
        persisted=result.persisted,
        not_found=list(result.not_found),
        deferred=result.deferred,
        exhausted=exhausted,
    )
    return {"persisted": result.persisted, "exhausted": exhausted}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preserva edições antigas do Diário fora do cursor direto."
    )
    parser.add_argument("--first-edition", type=int, default=3353)
    parser.add_argument("--last-edition", type=int, default=3988)
    parser.add_argument("--years", default="2021,2022,2023")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    if args.first_edition < 1 or args.last_edition < args.first_edition:
        parser.error("--first-edition e --last-edition devem formar um intervalo.")
    try:
        years = parse_years(args.years)
    except ValueError as error:
        parser.error(str(error))

    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    limit = args.limit or collector_settings.direct_diary_max_editions_per_run
    if limit < 1 or limit > 50:
        parser.error("--limit deve estar entre 1 e 50.")
    if persistence_settings.mode != "postgres-supabase":
        raise RuntimeError(
            "O backfill direto requer PERSISTENCE_MODE=postgres-supabase."
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
    control = CollectionControl(
        repository=repository,
        source_code=SOURCE_CODE,
        endpoint_code=ENDPOINT_CODE,
        idempotency_key=build_execution_idempotency_key("direct-diary-backfill"),
        collector_version=DIRECT_COLLECTOR_VERSION,
        partition_key=f"backfill:{args.first_edition}-{args.last_edition}",
        period_start=date(min(years), 1, 1),
        period_end=date(max(years), 12, 31),
    )

    def collect(*, editions: tuple[int, ...]):
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
            allowed_hosts=DIRECT_DIARY_ALLOWED_HOSTS,
            requests_per_minute=DIRECT_REQUESTS_PER_MINUTE,
            timeout_seconds=(
                collector_settings.connect_timeout_seconds
                + collector_settings.read_timeout_seconds
            ),
            retry_policy=RetryPolicy(max_attempts=collector_settings.max_attempts),
        )
        return collect_missing_editions(
            client,
            service.persist,
            editions=editions,
            years=years,
            logger=logger,
        )

    run_backfill(
        repository=repository,
        control=control,
        first_edition=args.first_edition,
        last_edition=args.last_edition,
        years=years,
        limit=limit,
        collect=collect,
        logger=logger,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
