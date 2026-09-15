"""Preserva contratos e empenhos do PNCP ligados a contratações já coletadas."""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from ..collection_control import (
    CollectionControl,
    CollectionOutcome,
    PartialCollectionFailure,
    build_execution_idempotency_key,
)
from ..connectors.pncp import SOURCE_CODE, fetch_contratos_page
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import PNCP_COLLECTOR_VERSION, PncpComprasPersistenceService
from ..settings import CollectorSettings, PersistenceSettings
from .pncp_runtime import build_authenticated_object_store

REFRESH_WINDOW_DAYS = 120
MAX_CONTRATACOES_PER_RUN = 50
MAX_CONTRATOS_PAGES = 30
MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
CONTRACT_CURSOR_VERSION = 1
_CONTROL = re.compile(r"[0-9]{14}-1-[0-9]{1,12}/[0-9]{4}")


@dataclass(frozen=True)
class PncpContratosCursor:
    after_control: str | None = None
    retry_controls: tuple[str, ...] = ()
    restart_reason: str | None = None


def resolve_contract_checkpoint(
    checkpoint: Mapping[str, object] | None,
) -> PncpContratosCursor:
    """Offset antigo não representa uma posição estável na fila mutável."""
    if not checkpoint:
        return PncpContratosCursor()
    retries: set[str] = set()
    for field in ("retry_controls", "contract_pages_truncated_controls"):
        values = checkpoint.get(field, [])
        if not isinstance(values, list) or any(
            not isinstance(value, str) or not _CONTROL.fullmatch(value)
            for value in values
        ):
            raise ValueError("Checkpoint PNCP contém pendências inválidas.")
        retries.update(values)
    version = checkpoint.get("cursor_version")
    if type(version) is not int or version != CONTRACT_CURSOR_VERSION:
        reason = "legacy_offset" if "next_offset" in checkpoint else "unknown_version"
        return PncpContratosCursor(None, tuple(sorted(retries)), reason)
    after = checkpoint.get("next_after_control")
    if after is not None and (
        not isinstance(after, str) or not _CONTROL.fullmatch(after)
    ):
        return PncpContratosCursor(None, tuple(sorted(retries)), "invalid_cursor")
    return PncpContratosCursor(after, tuple(sorted(retries)))


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
    start_after_control: str | None
    next_after_control: str | None
    retry_controls: tuple[str, ...] = ()
    restart_reason: str | None = None

    @property
    def checkpoint(self) -> dict[str, object]:
        return {
            "cursor_version": CONTRACT_CURSOR_VERSION,
            "next_after_control": self.next_after_control,
            "retry_controls": list(self.retry_controls),
            "pending_truncated": self.pending_truncated,
            "contract_pages_truncated_controls": list(
                self.contract_pages_truncated_controls
            ),
        }

    @property
    def observed_records(self) -> int:
        return self.contratacoes_processed

    @property
    def outcome(self) -> CollectionOutcome:
        if self.pending_truncated or self.retry_controls:
            return CollectionOutcome.PARTIAL
        if self.observed_records == 0:
            return CollectionOutcome.EMPTY
        return CollectionOutcome.COMPLETE


class PncpContratosBatchFailure(RuntimeError):
    def __init__(self, summary: PncpContratosCollectionSummary, error: Exception):
        super().__init__("Coleta PNCP interrompida; pendências mantidas para retomada.")
        self.summary = summary
        self.error = error


def execute_controlled_pncp_contratos(
    *,
    control: CollectionControl,
    operation: Callable[[], PncpContratosCollectionSummary],
) -> PncpContratosCollectionSummary:
    """Controla o backlog de contratos desde antes da autenticação."""
    with control:
        failure = None
        try:
            summary = operation()
        except PncpContratosBatchFailure as error:
            summary = error.summary
            failure = error
        partial_failure = None
        if failure:
            partial_failure = PartialCollectionFailure(
                type(failure.error).__name__,
                str(failure.error),
                retryable=not isinstance(
                    failure.error, (ValueError, TypeError, AssertionError)
                ),
            )
        elif summary.retry_controls:
            partial_failure = PartialCollectionFailure(
                "PncpContractsPending",
                "Há contratos com leitura ou preservação pendente.",
            )
        control.complete(
            outcome=summary.outcome,
            observed_records=summary.observed_records,
            checkpoint=summary.checkpoint,
            partial_failure=partial_failure,
            metrics={
                "contratacoes_processed": summary.contratacoes_processed,
                "pages": summary.pages,
                "inserted_records": summary.inserted_records,
                "existing_records": summary.existing_records,
                "pending_truncated": summary.pending_truncated,
                "start_after_control": summary.start_after_control,
                "next_after_control": summary.next_after_control,
                "cursor_version": CONTRACT_CURSOR_VERSION,
                "cursor_restart_reason": summary.restart_reason,
                "retry_controls": list(summary.retry_controls),
                "contract_pages_truncated_controls": list(
                    summary.contract_pages_truncated_controls
                ),
            },
        )
        if failure:
            raise failure from None
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
        collector_version=PNCP_COLLECTOR_VERSION,
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
        cursor = resolve_contract_checkpoint(checkpoint)
        if cursor.restart_reason:
            log_event(
                logger,
                logging.WARNING,
                "collector_pncp_contratos_cursor_restarted",
                source=SOURCE_CODE,
                reason=cursor.restart_reason,
            )
        service = PncpComprasPersistenceService(
            object_store=build_authenticated_object_store(persistence_settings),
            repository=repository,
        )
        return _collect_pending(
            service=service,
            repository=repository,
            logger=logger,
            cursor=cursor,
            checkpoint_progress=lambda checkpoint: (
                repository.pncp_contract_checkpoint_progress(
                    run_id=control.run_id,
                    checkpoint=checkpoint,
                )
            ),
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
        start_after_control=summary.start_after_control,
        next_after_control=summary.next_after_control,
        cursor_version=CONTRACT_CURSOR_VERSION,
        retry_controls=list(summary.retry_controls),
        coverage_status=summary.outcome.value,
    )
    return 1 if summary.retry_controls else 0


def _collect_pending(
    *,
    service: PncpComprasPersistenceService,
    repository: PostgresCollectionRepository,
    logger: logging.Logger,
    cursor: PncpContratosCursor,
    checkpoint_progress: Callable[[dict[str, object]], None],
) -> PncpContratosCollectionSummary:
    pending = repository.pncp_pending_contratos(
        refresh_days=REFRESH_WINDOW_DAYS,
        limit=MAX_CONTRATACOES_PER_RUN + 1,
        after_control=cursor.after_control,
        include_controls=cursor.retry_controls,
    )
    previous = cursor.after_control
    for control, ano, sequencial in pending:
        if (
            not isinstance(control, str)
            or not _CONTROL.fullmatch(control)
            or int(control.rsplit("/", 1)[1]) != ano
            or int(control.split("-", 2)[2].split("/", 1)[0]) != sequencial
            or (previous is not None and control <= previous)
        ):
            raise ValueError("Fila PNCP contém chave inválida ou ordem inconsistente.")
        previous = control
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

    # Reserva durável ANTES de qualquer requisição/persistência: mesmo um
    # encerramento abrupto não pode perder controles que saírem da fila.
    checkpoint_progress(
        {
            "cursor_version": CONTRACT_CURSOR_VERSION,
            "next_after_control": cursor.after_control,
            "retry_controls": sorted(
                set(cursor.retry_controls) | {row[0] for row in pending}
            ),
            "pending_truncated": True,
            "contract_pages_truncated_controls": [],
        }
    )
    processed = 0
    pages_persisted = 0
    records_inserted = 0
    records_existing = 0
    contract_pages_truncated_controls: list[str] = []
    retries = set(cursor.retry_controls)
    last_control = cursor.after_control

    def summarize(*, interrupted=False):
        return PncpContratosCollectionSummary(
            contratacoes_processed=processed,
            pages=pages_persisted,
            inserted_records=records_inserted,
            existing_records=records_existing,
            pending_truncated=truncated or interrupted,
            contract_pages_truncated_controls=tuple(contract_pages_truncated_controls),
            start_after_control=cursor.after_control,
            next_after_control=last_control if truncated or interrupted else None,
            retry_controls=tuple(sorted(retries)),
            restart_reason=cursor.restart_reason,
        )

    for control, ano, sequencial in pending:
        try:
            batch = collect_contratos_batch(
                ano=ano, sequencial=sequencial, logger=logger
            )
            if batch.truncated:
                retries.add(control)
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
        except Exception as error:
            retries.add(control)
            raise PncpContratosBatchFailure(
                summarize(interrupted=True), error
            ) from None
        if batch.pages and not batch.truncated:
            retries.discard(control)
        # Um retorno sem páginas pode ser 404/204. Não apaga retry conhecido.
        if not batch.pages:
            log_event(
                logger,
                logging.INFO,
                "collector_pncp_contratos_empty",
                source=SOURCE_CODE,
                control=control,
            )
        processed += 1
        last_control = control

    return summarize()


if __name__ == "__main__":
    raise SystemExit(main())
