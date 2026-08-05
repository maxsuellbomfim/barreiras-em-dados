"""Coleta contratações publicadas no PNCP por janela, com paginação completa."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from ..collection_control import (
    CollectionControl,
    CollectionOutcome,
    build_execution_idempotency_key,
)
from ..connectors.pncp import (
    CONTRATACAO_MODALIDADES,
    SOURCE_CODE,
    fetch_contratacoes_page,
)
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import (
    PNCP_COLLECTOR_VERSION,
    PncpContratacoesPersistenceService,
)
from ..settings import CollectorSettings, PersistenceSettings
from .pncp_runtime import build_authenticated_object_store

MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
MAX_WINDOW_DAYS = 31
MAX_PAGES_PER_MODALIDADE = 30
# Barreiras foi validada no PNCP em 2021-07-28; nada existe antes.
BACKFILL_HORIZON = date(2021, 7, 1)


@dataclass(frozen=True)
class PncpContratacoesCollectionSummary:
    pages: int
    inserted_records: int
    existing_records: int
    truncated_modalities: tuple[int, ...]

    @property
    def observed_records(self) -> int:
        return self.inserted_records + self.existing_records

    @property
    def outcome(self) -> CollectionOutcome:
        if self.truncated_modalities:
            return CollectionOutcome.PARTIAL
        if self.observed_records == 0:
            return CollectionOutcome.EMPTY
        return CollectionOutcome.COMPLETE


def execute_controlled_pncp_contratacoes(
    *,
    control: CollectionControl,
    operation: Callable[[], PncpContratacoesCollectionSummary],
) -> PncpContratacoesCollectionSummary:
    """Abre o controle antes da autenticação e da primeira chamada ao PNCP."""
    with control:
        summary = operation()
        control.complete(
            outcome=summary.outcome,
            observed_records=summary.observed_records,
            checkpoint={
                "truncated_modalities": list(summary.truncated_modalities),
            },
            metrics={
                "pages": summary.pages,
                "inserted_records": summary.inserted_records,
                "existing_records": summary.existing_records,
                "truncated_modalities": list(summary.truncated_modalities),
            },
        )
    return summary


def resolve_backfill_window(
    *,
    anchor: date | None,
    today: date,
    horizon: date = BACKFILL_HORIZON,
) -> tuple[str, str] | None:
    """Janela retroativa de até 30 dias; None quando o horizonte chegou."""
    effective_anchor = anchor or (today + timedelta(days=1))
    until = effective_anchor - timedelta(days=1)
    if until < horizon:
        return None
    start = max(horizon, until - timedelta(days=MAX_WINDOW_DAYS - 2))
    return start.strftime("%Y%m%d"), until.strftime("%Y%m%d")


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
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Deriva do banco a próxima janela retroativa até o horizonte.",
    )
    arguments = parser.parse_args(argv)
    if arguments.backfill and (arguments.since or arguments.until):
        parser.error("--backfill não aceita --since/--until.")
    since = until = ""
    if not arguments.backfill:
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
        raise RuntimeError("A coleta PNCP requer PERSISTENCE_MODE=postgres-supabase.")
    logger = logging.getLogger(__name__)
    if persistence_settings.database_url is None:
        raise RuntimeError("Configuração de banco incompleta.")
    repository = PostgresCollectionRepository.from_dsn(
        persistence_settings.database_url
    )
    if arguments.backfill:
        window = resolve_backfill_window(
            anchor=repository.pncp_backfill_anchor(),
            today=datetime.now(MUNICIPAL_TIMEZONE).date(),
        )
        if window is None:
            log_event(
                logger,
                logging.INFO,
                "collector_pncp_backfill_complete",
                source=SOURCE_CODE,
                horizon=BACKFILL_HORIZON.isoformat(),
            )
            return 0
        since, until = window

    period_start = datetime.strptime(since, "%Y%m%d").date()
    period_end = datetime.strptime(until, "%Y%m%d").date()
    control = CollectionControl(
        repository=repository,
        source_code=SOURCE_CODE,
        endpoint_code="consulta-contratacoes",
        idempotency_key=build_execution_idempotency_key("pncp-contratacoes"),
        collector_version=PNCP_COLLECTOR_VERSION,
        parser_version="pncp-contratacao-page/1.0.0",
        partition_key=(
            f"published:{period_start.isoformat()}:{period_end.isoformat()}"
        ),
        period_start=period_start,
        period_end=period_end,
    )

    def operation() -> PncpContratacoesCollectionSummary:
        service = _build_cloud_service(
            settings=persistence_settings,
            repository=repository,
        )
        return _collect_window(
            service=service,
            since=since,
            until=until,
            logger=logger,
        )

    summary = execute_controlled_pncp_contratacoes(
        control=control,
        operation=operation,
    )
    log_event(
        logger,
        logging.INFO,
        "collector_pncp_contratacoes_completed",
        source=SOURCE_CODE,
        window_start=since,
        window_end=until,
        pages=summary.pages,
        inserted_records=summary.inserted_records,
        existing_records=summary.existing_records,
        coverage_status=summary.outcome.value,
    )
    return 0


def _build_cloud_service(
    *,
    settings: PersistenceSettings,
    repository: PostgresCollectionRepository,
) -> PncpContratacoesPersistenceService:
    return PncpContratacoesPersistenceService(
        object_store=build_authenticated_object_store(settings),
        repository=repository,
    )


def _collect_window(
    *,
    service: PncpContratacoesPersistenceService,
    since: str,
    until: str,
    logger: logging.Logger,
) -> PncpContratacoesCollectionSummary:
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

    return PncpContratacoesCollectionSummary(
        pages=pages_persisted,
        inserted_records=records_inserted,
        existing_records=records_existing,
        truncated_modalities=tuple(truncated_modalities),
    )


if __name__ == "__main__":
    raise SystemExit(main())
