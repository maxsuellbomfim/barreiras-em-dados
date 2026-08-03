"""Preserva contratos e empenhos do PNCP ligados a contratações já coletadas."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

from ..connectors.pncp import SOURCE_CODE, fetch_contratos_page
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import PncpComprasPersistenceService
from ..persistence.storage import SupabaseStorageObjectStore
from ..settings import CollectorSettings, PersistenceSettings

REFRESH_WINDOW_DAYS = 120
MAX_CONTRATACOES_PER_RUN = 50


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preserva contratos e empenhos publicados no PNCP para Barreiras, "
            "sem ainda convertê-los em execução financeira normalizada."
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
        raise RuntimeError("A coleta PNCP requer PERSISTENCE_MODE=postgres-supabase.")
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
        raise RuntimeError(
            "O Storage não forneceu uma sessão autenticada."
        )

    repository = PostgresCollectionRepository.from_dsn(
        persistence_settings.database_url
    )
    service = PncpComprasPersistenceService(
        object_store=SupabaseStorageObjectStore(
            supabase_client.storage.from_(
                persistence_settings.raw_artifacts_bucket
            )
        ),
        repository=repository,
    )
    logger = logging.getLogger(__name__)
    pending = repository.pncp_pending_contratos(
        refresh_days=REFRESH_WINDOW_DAYS,
        limit=MAX_CONTRATACOES_PER_RUN + 1,
    )
    truncated = len(pending) > MAX_CONTRATACOES_PER_RUN
    if truncated:
        pending = pending[:MAX_CONTRATACOES_PER_RUN]
        log_event(
            logger,
            logging.WARNING,
            "collector_pncp_contratos_truncated",
            source=SOURCE_CODE,
            max_contratacoes=MAX_CONTRATACOES_PER_RUN,
        )

    processed = 0
    pages_persisted = 0
    records_inserted = 0
    records_existing = 0
    for control, ano, sequencial in pending:
        page = fetch_contratos_page(
            ano=ano,
            sequencial=sequencial,
            logger=logger,
        )
        if page is None:
            processed += 1
            log_event(
                logger,
                logging.INFO,
                "collector_pncp_contratos_empty",
                source=SOURCE_CODE,
                control=control,
            )
            continue
        result = service.persist_contratos(page, control=control)
        pages_persisted += 1
        records_inserted += result.inserted_records
        records_existing += result.existing_records
        processed += 1
        log_event(
            logger,
            logging.INFO,
            "collector_pncp_contratos_persisted",
            source=SOURCE_CODE,
            control=control,
            records=len(page.items),
            inserted_records=result.inserted_records,
            existing_records=result.existing_records,
        )

    log_event(
        logger,
        logging.INFO,
        "collector_pncp_contratos_completed",
        source=SOURCE_CODE,
        contratacoes=processed,
        pages=pages_persisted,
        pending_truncated=truncated,
        inserted_records=records_inserted,
        existing_records=records_existing,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
