"""Preserva a votação nominal recebida em Barreiras num pleito."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from ..collection_control import CollectionOutcome
from ..connectors.tse import ENDPOINT_CODE, SOURCE_CODE, fetch_votes
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import (
    TSE_COLLECTOR_VERSION,
    TSE_PARSER_VERSION,
    TseVotesPersistenceService,
)
from ..persistence.storage import SupabaseStorageObjectStore
from ..settings import CollectorSettings, PersistenceSettings
from .representation_control import (
    RepresentationCollectionSummary,
    build_representation_control,
    execute_controlled_representation,
)

DEFAULT_YEARS = (2024, 2022)
MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preserva quantos votos cada candidatura recebeu em Barreiras, "
            "que é o vínculo territorial verificável do ADR 0014."
        )
    )
    parser.add_argument(
        "--ano",
        type=int,
        action="append",
        help="Ano do pleito; pode repetir. Padrão: 2024 e 2022.",
    )
    arguments = parser.parse_args(argv)
    years = tuple(arguments.ano) if arguments.ano else DEFAULT_YEARS
    for year in years:
        if not 1994 <= year <= 2100:
            parser.error(f"Ano fora do intervalo aceito: {year}.")

    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    logger = logging.getLogger(__name__)
    if persistence_settings.mode != "postgres-supabase":
        raise RuntimeError("A coleta do TSE requer PERSISTENCE_MODE=postgres-supabase.")
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
    preserved = 0
    for year in years:
        control = build_representation_control(
            repository=repository,
            source_code=SOURCE_CODE,
            endpoint_code=ENDPOINT_CODE,
            namespace=f"tse-votes-{year}",
            collector_version=TSE_COLLECTOR_VERSION,
            parser_version=TSE_PARSER_VERSION,
            partition_key=f"election:{year}:barreiras",
            snapshot_date=snapshot_date,
        )

        def operation(election_year: int = year) -> RepresentationCollectionSummary:
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
            service = TseVotesPersistenceService(
                object_store=SupabaseStorageObjectStore(
                    supabase_client.storage.from_(
                        persistence_settings.raw_artifacts_bucket
                    )
                ),
                repository=repository,
            )
            page = fetch_votes(election_year, logger=logger)
            if page is None:
                log_event(
                    logger,
                    logging.INFO,
                    "collector_tse_year_unavailable",
                    source=SOURCE_CODE,
                    year=election_year,
                )
                return RepresentationCollectionSummary(
                    observed_records=0,
                    outcome=CollectionOutcome.BLOCKED,
                    block_reason="arquivo eleitoral ainda não publicado pela fonte",
                    metrics={"election_year": election_year},
                )
            result = service.persist(page)
            log_event(
                logger,
                logging.INFO,
                "collector_tse_year_preserved",
                source=SOURCE_CODE,
                year=election_year,
                candidaturas=len(page.items),
                inserted_records=result.inserted_records,
                existing_records=result.existing_records,
            )
            return RepresentationCollectionSummary(
                observed_records=len(page.items),
                outcome=(
                    CollectionOutcome.COMPLETE
                    if page.items
                    else CollectionOutcome.EMPTY
                ),
                metrics={
                    "election_year": election_year,
                    "inserted_records": result.inserted_records,
                    "existing_records": result.existing_records,
                },
            )

        summary = execute_controlled_representation(
            control=control,
            operation=operation,
        )
        if summary.outcome in {CollectionOutcome.COMPLETE, CollectionOutcome.EMPTY}:
            preserved += 1

    log_event(
        logger,
        logging.INFO,
        "collector_tse_completed",
        source=SOURCE_CODE,
        years=list(years),
        preserved=preserved,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
