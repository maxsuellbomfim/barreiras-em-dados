"""Coleta contratações publicadas no PNCP por janela, com paginação completa."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from ..connectors.pncp import (
    CONTRATACAO_MODALIDADES,
    SOURCE_CODE,
    fetch_contratacoes_page,
)
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import PncpContratacoesPersistenceService
from ..persistence.storage import SupabaseStorageObjectStore
from ..settings import CollectorSettings, PersistenceSettings

MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
MAX_WINDOW_DAYS = 31
MAX_PAGES_PER_MODALIDADE = 30


def resolve_window(since: str, until: str) -> tuple[str, str]:
    if bool(since.strip()) != bool(until.strip()):
        raise ValueError("--since e --until devem ser informados juntos.")
    if not since.strip():
        today = datetime.now(MUNICIPAL_TIMEZONE).date()
        start = today - timedelta(days=7)
        return start.strftime("%Y%m%d"), today.strftime("%Y%m%d")
    start = date.fromisoformat(since)
    end = date.fromisoformat(until)
    if start > end:
        raise ValueError("--since não pode ser posterior a --until.")
    if (end - start).days >= MAX_WINDOW_DAYS:
        raise ValueError(f"A janela não pode exceder {MAX_WINDOW_DAYS} dias.")
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preserva as contratações publicadas no PNCP para Barreiras em "
            "uma janela curta, percorrendo todas as modalidades e páginas."
        )
    )
    parser.add_argument("--since", default="")
    parser.add_argument("--until", default="")
    arguments = parser.parse_args(argv)
    try:
        since, until = resolve_window(arguments.since, arguments.until)
    except ValueError as error:
        parser.error(str(error))

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

    service = PncpContratacoesPersistenceService(
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
    pages_persisted = 0
    records_inserted = 0
    records_existing = 0
    truncated_modalities: list[int] = []
    for modalidade in CONTRATACAO_MODALIDADES:
        pagina = 1
        while pagina <= MAX_PAGES_PER_MODALIDADE:
            page = fetch_contratacoes_page(
                since=since,
                until=until,
                modalidade=modalidade,
                pagina=pagina,
                logger=logger,
            )
            if page is None:
                break
            result = service.persist(page)
            pages_persisted += 1
            records_inserted += result.inserted_records
            records_existing += result.existing_records
            log_event(
                logger,
                logging.INFO,
                "collector_pncp_page_persisted",
                source=SOURCE_CODE,
                modalidade=modalidade,
                pagina=pagina,
                total_paginas=page.total_paginas,
                inserted_records=result.inserted_records,
                existing_records=result.existing_records,
            )
            if pagina >= page.total_paginas:
                break
            pagina += 1
        else:
            # Nunca truncar em silêncio: registra e segue para replay manual.
            truncated_modalities.append(modalidade)

    if truncated_modalities:
        log_event(
            logger,
            logging.WARNING,
            "collector_pncp_pagination_truncated",
            source=SOURCE_CODE,
            modalidades=truncated_modalities,
            max_pages=MAX_PAGES_PER_MODALIDADE,
        )

    log_event(
        logger,
        logging.INFO,
        "collector_pncp_contratacoes_completed",
        source=SOURCE_CODE,
        window_start=since,
        window_end=until,
        pages=pages_persisted,
        inserted_records=records_inserted,
        existing_records=records_existing,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
