"""Preserva os deputados federais da Bahia e o detalhe de cada um."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

from ..connectors.camara import (
    SOURCE_CODE,
    fetch_deputies_page,
    fetch_deputy_detail,
)
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import CamaraPersistenceService
from ..persistence.storage import SupabaseStorageObjectStore
from ..settings import CollectorSettings, PersistenceSettings

MAX_PAGES = 10
# ponytail: teto por execução; o restante entra na próxima e o corte é
# sempre registrado em log.
MAX_DETAILS_PER_RUN = 60


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preserva a lista de deputados federais da Bahia e o detalhe "
            "de cada um, como bruto verificável por hash."
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
            "A coleta da Câmara requer PERSISTENCE_MODE=postgres-supabase."
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
    service = CamaraPersistenceService(
        object_store=SupabaseStorageObjectStore(
            supabase_client.storage.from_(
                persistence_settings.raw_artifacts_bucket
            )
        ),
        repository=repository,
    )

    deputy_ids: list[int] = []
    pagina = 1
    while pagina <= MAX_PAGES:
        page = fetch_deputies_page(pagina, logger=logger)
        if page is None:
            break
        service.persist(page, record_type="camara_deputado")
        for item in page.items:
            identifier = item.get("id")
            if isinstance(identifier, int):
                deputy_ids.append(identifier)
        log_event(
            logger,
            logging.INFO,
            "collector_camara_page_persisted",
            source=SOURCE_CODE,
            pagina=pagina,
            deputados=len(page.items),
        )
        if len(page.items) < 100:
            break
        pagina += 1

    truncated = len(deputy_ids) > MAX_DETAILS_PER_RUN
    if truncated:
        log_event(
            logger,
            logging.WARNING,
            "collector_camara_details_truncated",
            source=SOURCE_CODE,
            max_details=MAX_DETAILS_PER_RUN,
        )
    details = 0
    for deputy_id in deputy_ids[:MAX_DETAILS_PER_RUN]:
        detail = fetch_deputy_detail(deputy_id, logger=logger)
        if detail is None:
            continue
        service.persist(detail, record_type="camara_deputado_detalhe")
        details += 1

    log_event(
        logger,
        logging.INFO,
        "collector_camara_completed",
        source=SOURCE_CODE,
        deputados=len(deputy_ids),
        detalhes=details,
        truncated=truncated,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
