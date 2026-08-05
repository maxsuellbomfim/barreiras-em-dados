"""Coleta itens e resultados (quem ganhou, por quanto) das contratações."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from ..collection_control import (
    CollectionControl,
    CollectionOutcome,
    build_execution_idempotency_key,
)
from ..connectors.pncp import (
    SOURCE_CODE,
    fetch_itens_page,
    fetch_resultados_page,
)
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import PNCP_COLLECTOR_VERSION, PncpComprasPersistenceService
from ..settings import CollectorSettings, PersistenceSettings
from .pncp_runtime import (
    build_authenticated_object_store,
    resolve_checkpoint_offset,
)

# Homologação costuma chegar semanas depois da publicação; contratações
# publicadas nesta janela são revisitadas mesmo já tendo itens preservados.
REFRESH_WINDOW_DAYS = 120
# ponytail: teto por execução; o backlog restante fica para a próxima rodada
# e é sempre registrado em log — nunca truncamos em silêncio.
MAX_CONTRATACOES_PER_RUN = 50
MAX_ITENS_PAGES = 30
MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")


@dataclass(frozen=True)
class PncpItensPageBatch:
    pages: tuple
    truncated: bool


@dataclass(frozen=True)
class PncpItensCollectionSummary:
    contratacoes_processed: int
    itens_inserted: int
    resultados_inserted: int
    pending_truncated: bool
    item_pages_truncated_controls: tuple[str, ...]
    start_offset: int
    next_offset: int

    @property
    def observed_records(self) -> int:
        return self.contratacoes_processed

    @property
    def outcome(self) -> CollectionOutcome:
        if self.pending_truncated or self.item_pages_truncated_controls:
            return CollectionOutcome.PARTIAL
        if self.observed_records == 0:
            return CollectionOutcome.EMPTY
        return CollectionOutcome.COMPLETE


def execute_controlled_pncp_itens(
    *,
    control: CollectionControl,
    operation: Callable[[], PncpItensCollectionSummary],
) -> PncpItensCollectionSummary:
    """Controla o backlog de itens/resultados desde antes da autenticação."""
    with control:
        summary = operation()
        checkpoint = {
            "pending_truncated": summary.pending_truncated,
            "item_pages_truncated_controls": list(
                summary.item_pages_truncated_controls
            ),
            "next_offset": summary.next_offset,
        }
        control.complete(
            outcome=summary.outcome,
            observed_records=summary.observed_records,
            checkpoint=checkpoint,
            metrics={
                "contratacoes_processed": summary.contratacoes_processed,
                "itens_inserted": summary.itens_inserted,
                "resultados_inserted": summary.resultados_inserted,
                "start_offset": summary.start_offset,
                **checkpoint,
            },
        )
    return summary


def collect_itens_batch(
    *,
    ano: int,
    sequencial: int,
    logger: logging.Logger,
    transport=None,
) -> PncpItensPageBatch:
    """Percorre itens e informa quando o teto impediu confirmar o fim."""
    pages = []
    seen_itens: set[int] = set()
    for pagina in range(1, MAX_ITENS_PAGES + 1):
        page = fetch_itens_page(
            ano=ano,
            sequencial=sequencial,
            pagina=pagina,
            transport=transport,
            logger=logger,
        )
        if page is None:
            return PncpItensPageBatch(tuple(pages), False)
        numeros = {
            item.get("numeroItem")
            for item in page.items
            if isinstance(item.get("numeroItem"), int)
        }
        if numeros and numeros <= seen_itens:
            return PncpItensPageBatch(tuple(pages), False)
        seen_itens.update(numeros)
        pages.append(page)
        if len(page.items) < page.cursor["size"]:
            return PncpItensPageBatch(tuple(pages), False)
    return PncpItensPageBatch(tuple(pages), bool(pages))


def collect_itens_pages(
    *,
    ano: int,
    sequencial: int,
    logger: logging.Logger,
    transport=None,
) -> list:
    """Todas as páginas de itens, com guarda contra API sem paginação."""
    return list(
        collect_itens_batch(
            ano=ano,
            sequencial=sequencial,
            logger=logger,
            transport=transport,
        ).pages
    )


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
    if persistence_settings.database_url is None:
        raise RuntimeError("Configuração de banco incompleta.")
    repository = PostgresCollectionRepository.from_dsn(
        persistence_settings.database_url
    )
    logger = logging.getLogger(__name__)
    today = datetime.now(MUNICIPAL_TIMEZONE).date()
    partition_key = "backlog:itens-resultados"
    control = CollectionControl(
        repository=repository,
        source_code=SOURCE_CODE,
        endpoint_code="compras-api",
        idempotency_key=build_execution_idempotency_key("pncp-itens-resultados"),
        collector_version=PNCP_COLLECTOR_VERSION,
        parser_version="pncp-itens-resultados/1.0.0",
        partition_key=partition_key,
        period_start=today,
        period_end=today,
    )

    def operation() -> PncpItensCollectionSummary:
        checkpoint = repository.collection_partition_checkpoint(
            source_code=SOURCE_CODE,
            endpoint_code="compras-api",
            partition_key=partition_key,
        )
        start_offset = resolve_checkpoint_offset(checkpoint)
        service = PncpComprasPersistenceService(
            object_store=build_authenticated_object_store(persistence_settings),
            repository=repository,
        )
        return _collect_pending(
            service=service,
            repository=repository,
            logger=logger,
            start_offset=start_offset,
        )

    summary = execute_controlled_pncp_itens(
        control=control,
        operation=operation,
    )
    log_event(
        logger,
        logging.INFO,
        "collector_pncp_itens_completed",
        source=SOURCE_CODE,
        contratacoes=summary.contratacoes_processed,
        pending_truncated=summary.pending_truncated,
        item_pages_truncated_controls=list(
            summary.item_pages_truncated_controls
        ),
        itens_inserted=summary.itens_inserted,
        resultados_inserted=summary.resultados_inserted,
        start_offset=summary.start_offset,
        next_offset=summary.next_offset,
        coverage_status=summary.outcome.value,
    )
    return 0


def _collect_pending(
    *,
    service: PncpComprasPersistenceService,
    repository: PostgresCollectionRepository,
    logger: logging.Logger,
    start_offset: int,
) -> PncpItensCollectionSummary:
    pending = repository.pncp_pending_itens(
        refresh_days=REFRESH_WINDOW_DAYS,
        limit=MAX_CONTRATACOES_PER_RUN + 1,
        offset=start_offset,
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
    item_pages_truncated_controls: list[str] = []
    for control, ano, sequencial in pending:
        itens: list[dict] = []
        batch = collect_itens_batch(
            ano=ano,
            sequencial=sequencial,
            logger=logger,
        )
        if batch.truncated:
            item_pages_truncated_controls.append(control)
            log_event(
                logger,
                logging.WARNING,
                "collector_pncp_itens_pages_truncated",
                source=SOURCE_CODE,
                control=control,
                max_pages=MAX_ITENS_PAGES,
            )
        for page in batch.pages:
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

    return PncpItensCollectionSummary(
        contratacoes_processed=contratacoes_processed,
        itens_inserted=itens_inserted,
        resultados_inserted=resultados_inserted,
        pending_truncated=truncated,
        item_pages_truncated_controls=tuple(item_pages_truncated_controls),
        start_offset=start_offset,
        next_offset=(
            start_offset + contratacoes_processed if truncated else 0
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
