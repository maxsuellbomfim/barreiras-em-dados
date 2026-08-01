"""Preserva a votação nominal recebida em Barreiras num pleito."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

from ..connectors.tse import SOURCE_CODE, fetch_votes
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import TseVotesPersistenceService
from ..persistence.storage import SupabaseStorageObjectStore
from ..settings import CollectorSettings, PersistenceSettings

# 2022: deputados federais e estaduais (vínculo territorial dos mandatos
# em curso). 2024: prefeito e vereadores. Pleitos anteriores entram por
# --ano quando houver interesse.
DEFAULT_YEARS = (2024, 2022)


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
        raise RuntimeError(
            "A coleta do TSE requer PERSISTENCE_MODE=postgres-supabase."
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
    service = TseVotesPersistenceService(
        object_store=SupabaseStorageObjectStore(
            supabase_client.storage.from_(
                persistence_settings.raw_artifacts_bucket
            )
        ),
        repository=repository,
    )

    preserved = 0
    for year in years:
        page = fetch_votes(year, logger=logger)
        if page is None:
            log_event(
                logger,
                logging.INFO,
                "collector_tse_year_unavailable",
                source=SOURCE_CODE,
                year=year,
            )
            continue
        result = service.persist(page)
        preserved += 1
        log_event(
            logger,
            logging.INFO,
            "collector_tse_year_preserved",
            source=SOURCE_CODE,
            year=year,
            candidaturas=len(page.items),
            inserted_records=result.inserted_records,
            existing_records=result.existing_records,
        )

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
