"""Preserva contratos e empenhos do PNCP ligados a contratações já coletadas."""

from __future__ import annotations

import argparse
import json
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
from ..connectors.pncp import SOURCE_CODE, fetch_contratos_page
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import PncpComprasPersistenceService
from ..settings import CollectorSettings, PersistenceSettings
from .pncp_runtime import (
    build_authenticated_object_store,
    resolve_checkpoint_offset,
)

REFRESH_WINDOW_DAYS = 120
MAX_CONTRATACOES_PER_RUN = 50
MAX_CONTRATOS_PAGES = 30
MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")


@dataclass(frozen=True)
class PncpContratosPageBatch:
    pages: tuple
    truncated: bool


@dataclass(frozen=True)
class PncpContratosCollectionSummary:
    contratacoes_processed: int
    pages: int
    inserted_records: int
    existing_records: int
    pending_truncated: bool
    contract_pages_truncated_controls: tuple[str, ...]
    start_offset: int
    next_offset: int

    @property
    def observed_records(self) -> int:
        return self.contratacoes_processed

    @property
    def outcome(self) -> CollectionOutcome:
        if self.pending_truncated or self.contract_pages_truncated_controls:
            return CollectionOutcome.PARTIAL
        if self.observed_records == 0:
            return CollectionOutcome.EMPTY
        return CollectionOutcome.COMPLETE


def execute_controlled_pncp_contratos(
    *,
    control: CollectionControl,
    operation: Callable[[], PncpContratosCollectionSummary],
) -> PncpContratosCollectionSummary:
    """Controla o backlog de contratos desde antes da autenticação."""
    with control:
        summary = operation()
        control.complete(
            outcome=summary.outcome,
            observed_records=summary.observed_records,
            checkpoint={
                "pending_truncated": summary.pending_truncated,
                "contract_pages_truncated_controls": list(
                    summary.contract_pages_truncated_controls
                ),
                "next_offset": summary.next_offset,
            },
            metrics={
                "contratacoes_processed": summary.contratacoes_processed,
                "pages": summary.pages,
                "inserted_records": summary.inserted_records,
                "existing_records": summary.existing_records,
                "pending_truncated": summary.pending_truncated,
                "start_offset": summary.start_offset,
                "contract_pages_truncated_controls": list(
                    summary.contract_pages_truncated_controls
                ),
            },
        )
    return summary


def collect_contratos_batch(
    *,
    ano: int,
    sequencial: int,
    logger: logging.Logger,
    transport=None,
) -> PncpContratosPageBatch:
    """Percorre contratos e informa quando o teto impede confirmar o fim."""
    pages = []
    list_page_hashes: set[str] = set()
    for pagina in range(1, MAX_CONTRATOS_PAGES + 1):
        page = fetch_contratos_page(
            ano=ano,
            sequencial=sequencial,
            pagina=pagina,
            logger=logger,
            transport=transport,
        )
        if page is None:
            return PncpContratosPageBatch(tuple(pages), False)
        try:
            root = json.loads(page.raw_body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            root = None
        paginated_root = isinstance(root, dict)
        if not paginated_root and page.body_sha256 in list_page_hashes:
            return PncpContratosPageBatch(tuple(pages), False)
        if not paginated_root:
            list_page_hashes.add(page.body_sha256)
        pages.append(page)
        if paginated_root and pagina >= page.total_paginas:
            return PncpContratosPageBatch(tuple(pages), False)
        if not paginated_root and len(page.items) < page.cursor["size"]:
            return PncpContratosPageBatch(tuple(pages), False)
    return PncpContratosPageBatch(tuple(pages), bool(pages))


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
    if persistence_settings.database_url is None:
        raise RuntimeError("Configuração de banco incompleta.")
    repository = PostgresCollectionRepository.from_dsn(
        persistence_settings.database_url
    )
    logger = logging.getLogger(__name__)
    today = datetime.now(MUNICIPAL_TIMEZONE).date()
    partition_key = "backlog:contratos"
    control = CollectionControl(
        repository=repository,
        source_code=SOURCE_CODE,
        endpoint_code="contratos-api",
        idempotency_key=build_execution_idempotency_key("pncp-contratos"),
        collector_version=collector_settings.collector_version,
        parser_version="pncp-contratos/1.0.0",
        partition_key=partition_key,
        period_start=today,
        period_end=today,
    )

    def operation() -> PncpContratosCollectionSummary:
        checkpoint = repository.collection_partition_checkpoint(
            source_code=SOURCE_CODE,
            endpoint_code="contratos-api",
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

    summary = execute_controlled_pncp_contratos(
        control=control,
        operation=operation,
    )
    log_event(
        logger,
        logging.INFO,
        "collector_pncp_contratos_completed",
        source=SOURCE_CODE,
        contratacoes=summary.contratacoes_processed,
        pages=summary.pages,
        pending_truncated=summary.pending_truncated,
        contract_pages_truncated_controls=list(
            summary.contract_pages_truncated_controls
        ),
        inserted_records=summary.inserted_records,
        existing_records=summary.existing_records,
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
) -> PncpContratosCollectionSummary:
    pending = repository.pncp_pending_contratos(
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
            "collector_pncp_contratos_truncated",
            source=SOURCE_CODE,
            max_contratacoes=MAX_CONTRATACOES_PER_RUN,
        )

    processed = 0
    pages_persisted = 0
    records_inserted = 0
    records_existing = 0
    contract_pages_truncated_controls: list[str] = []
    for control, ano, sequencial in pending:
        batch = collect_contratos_batch(
            ano=ano,
            sequencial=sequencial,
            logger=logger,
        )
        if not batch.pages:
            processed += 1
            log_event(
                logger,
                logging.INFO,
                "collector_pncp_contratos_empty",
                source=SOURCE_CODE,
                control=control,
            )
            continue
        if batch.truncated:
            contract_pages_truncated_controls.append(control)
            log_event(
                logger,
                logging.WARNING,
                "collector_pncp_contratos_pages_truncated",
                source=SOURCE_CODE,
                control=control,
                max_pages=MAX_CONTRATOS_PAGES,
            )
        for page in batch.pages:
            result = service.persist_contratos(page, control=control)
            pages_persisted += 1
            records_inserted += result.inserted_records
            records_existing += result.existing_records
            log_event(
                logger,
                logging.INFO,
                "collector_pncp_contratos_persisted",
                source=SOURCE_CODE,
                control=control,
                pagina=page.cursor["pagina"],
                total_paginas=page.total_paginas,
                records=len(page.items),
                inserted_records=result.inserted_records,
                existing_records=result.existing_records,
            )
        processed += 1

    return PncpContratosCollectionSummary(
        contratacoes_processed=processed,
        pages=pages_persisted,
        inserted_records=records_inserted,
        existing_records=records_existing,
        pending_truncated=truncated,
        contract_pages_truncated_controls=tuple(
            contract_pages_truncated_controls
        ),
        start_offset=start_offset,
        next_offset=(start_offset + processed if truncated else 0),
    )


if __name__ == "__main__":
    raise SystemExit(main())
