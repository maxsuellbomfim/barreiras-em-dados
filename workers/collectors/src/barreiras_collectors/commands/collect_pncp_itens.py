"""Coleta itens e resultados (quem ganhou, por quanto) das contratações."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

from ..connectors.pncp import (
    SOURCE_CODE,
    fetch_itens_page,
    fetch_resultados_page,
)
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import PncpComprasPersistenceService
from ..persistence.storage import SupabaseStorageObjectStore
from ..settings import CollectorSettings, PersistenceSettings

# Homologação costuma chegar semanas depois da publicação; contratações
# publicadas nesta janela são revisitadas mesmo já tendo itens preservados.
REFRESH_WINDOW_DAYS = 120
# ponytail: teto por execução; o backlog restante fica para a próxima rodada
# e é sempre registrado em log — nunca truncamos em silêncio.
MAX_CONTRATACOES_PER_RUN = 50
MAX_ITENS_PAGES = 30


def collect_itens_pages(
    *,
    ano: int,
    sequencial: int,
    logger: logging.Logger,
    transport=None,
) -> list:
    """Todas as páginas de itens, com guarda contra API sem paginação."""
    pages = []
    seen_itens: set[int] = set()
    pagina = 1
    while pagina <= MAX_ITENS_PAGES:
        page = fetch_itens_page(
            ano=ano,
            sequencial=sequencial,
            pagina=pagina,
            transport=transport,
            logger=logger,
        )
        if page is None:
            break
        numeros = {
            item.get("numeroItem")
            for item in page.items
            if isinstance(item.get("numeroItem"), int)
        }
        if numeros and numeros <= seen_itens:
            # A API repetiu a página anterior: não há paginação real aqui.
            break
        seen_itens.update(numeros)
        pages.append(page)
        if len(page.items) < page.cursor["size"]:
            break
        pagina += 1
    return pages


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preserva itens e resultados homologados das contratações já "
            "coletadas do PNCP, derivando do banco o que está pendente."
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
    pending = repository.pncp_pending_itens(
        refresh_days=REFRESH_WINDOW_DAYS,
        limit=MAX_CONTRATACOES_PER_RUN + 1,
    )
    truncated = len(pending) > MAX_CONTRATACOES_PER_RUN
    if truncated:
        pending = pending[:MAX_CONTRATACOES_PER_RUN]
        log_event(
            logger,
            logging.WARNING,
            "collector_pncp_itens_truncated",
            source=SOURCE_CODE,
            max_contratacoes=MAX_CONTRATACOES_PER_RUN,
        )

    contratacoes_processed = 0
    itens_inserted = 0
    resultados_inserted = 0
    for control, ano, sequencial in pending:
        itens: list[dict] = []
        for page in collect_itens_pages(
            ano=ano,
            sequencial=sequencial,
            logger=logger,
        ):
            result = service.persist_itens(page, control=control)
            itens_inserted += result.inserted_records
            itens.extend(page.items)

        ja_com_resultado = repository.pncp_itens_com_resultado(control)
        for item in itens:
            numero_item = item.get("numeroItem")
            if not isinstance(numero_item, int):
                continue
            if not item.get("temResultado"):
                continue
            if numero_item in ja_com_resultado:
                continue
            resultado_page = fetch_resultados_page(
                ano=ano,
                sequencial=sequencial,
                numero_item=numero_item,
                logger=logger,
            )
            if resultado_page is None:
                continue
            result = service.persist_resultados(
                resultado_page,
                control=control,
                numero_item=numero_item,
            )
            resultados_inserted += result.inserted_records

        contratacoes_processed += 1
        log_event(
            logger,
            logging.INFO,
            "collector_pncp_itens_contratacao",
            source=SOURCE_CODE,
            control=control,
            itens=len(itens),
        )

    log_event(
        logger,
        logging.INFO,
        "collector_pncp_itens_completed",
        source=SOURCE_CODE,
        contratacoes=contratacoes_processed,
        pending_truncated=truncated,
        itens_inserted=itens_inserted,
        resultados_inserted=resultados_inserted,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
