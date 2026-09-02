"""Coleta mensal controlada do catálogo de prestações do TCM-BA."""

from __future__ import annotations

import argparse
import calendar
import hashlib
import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from ..collection_control import (
    CollectionControl,
    CollectionOutcome,
    build_execution_idempotency_key,
)
from ..connectors.tcm_ba import (
    ENDPOINT_CODE,
    SOURCE_CODE,
    TcmBaContractError,
    TcmBaMonthlyCatalog,
    TcmBaPublicAccountsClient,
)
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.tcm_ba import (
    TCM_BA_COLLECTOR_VERSION,
    TCM_BA_PARSER_VERSION,
    TcmBaCatalogPersistenceService,
)
from ..resilience import PacedRateLimiter
from ..settings import CollectorSettings, PersistenceSettings
from .pncp_runtime import build_authenticated_object_store

MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")


@dataclass(frozen=True)
class TcmBaMonthlyCollectionSummary:
    year: int
    month: int
    documents: int
    artifacts: int
    inserted_records: int
    existing_records: int
    artifact_hashes: tuple[str, ...]


def fetch_tcm_ba_monthly_catalog_with_contract_retry(
    *,
    year: int,
    month: int,
    requests_per_minute: int,
    logger: logging.Logger,
) -> TcmBaMonthlyCatalog:
    """Refaz uma captura completa uma única vez após falha de contrato."""
    rate_limiter = PacedRateLimiter(requests_per_minute)
    competence = f"{month:02d}/{year}"
    for attempt in range(1, 3):
        client = TcmBaPublicAccountsClient(
            requests_per_minute=requests_per_minute,
            rate_limiter=rate_limiter,
        )
        try:
            return client.fetch_monthly_catalog(year=year, month=month)
        except TcmBaContractError as error:
            if _unpublished_competence(error) is not None:
                raise
            if attempt == 2:
                raise
            log_event(
                logger,
                logging.WARNING,
                "collector_tcm_ba_contract_retry",
                source=SOURCE_CODE,
                competence=competence,
                next_attempt=attempt + 1,
                error_type=type(error).__name__,
            )
    raise AssertionError("A captura do TCM-BA não produziu catálogo.")


def month_range(
    month_from: str,
    month_to: str,
    *,
    collected_on: date,
) -> tuple[tuple[int, int], ...]:
    start = _parse_month(month_from)
    end = _parse_month(month_to)
    current = (collected_on.year, collected_on.month)
    if start < (2021, 1) or end < start or end > current:
        raise ValueError(
            "O intervalo mensal deve estar entre 2021-01 e o mês corrente."
        )
    months: list[tuple[int, int]] = []
    year, month = start
    while (year, month) <= end:
        months.append((year, month))
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return tuple(months)


def previous_closed_month(collected_on: date) -> tuple[int, int]:
    if collected_on.month == 1:
        return collected_on.year - 1, 12
    return collected_on.year, collected_on.month - 1


def _unpublished_competence(error: TcmBaContractError) -> str | None:
    match = re.fullmatch(
        r"Opção '((?:0[1-9]|1[0-2])/\d{4})' ausente no campo "
        r"consultaPublicaTabPanel:consultaPublicaPCSearchForm:"
        r"competenciaPCMes_input\.",
        str(error),
    )
    return match.group(1) if match else None


def execute_controlled_tcm_month(
    *,
    control: CollectionControl,
    operation: Callable[[], TcmBaMonthlyCollectionSummary],
) -> TcmBaMonthlyCollectionSummary | None:
    with control:
        try:
            summary = operation()
        except TcmBaContractError as error:
            competence = _unpublished_competence(error)
            if competence is None:
                raise
            control.complete(
                outcome=CollectionOutcome.BLOCKED,
                observed_records=0,
                checkpoint={"competence": competence},
                metrics={"documents_catalogued": 0, "artifacts_preserved": 0},
                block_reason=(
                    "O e-TCM ainda não disponibilizou a competência mensal "
                    "no catálogo público."
                ),
            )
            return None
        if summary.artifacts < 1 or summary.documents < 0:
            raise RuntimeError("A captura mensal do TCM-BA está incompleta.")
        competence = f"{summary.month:02d}/{summary.year}"
        manifest_sha256 = hashlib.sha256(
            "\n".join(summary.artifact_hashes).encode("ascii")
        ).hexdigest()
        control.complete(
            outcome=(
                CollectionOutcome.COMPLETE
                if summary.documents > 0
                else CollectionOutcome.EMPTY
            ),
            observed_records=summary.documents,
            checkpoint={
                "competence": competence,
                "documents_catalogued": summary.documents,
                "artifacts_preserved": summary.artifacts,
                "artifact_manifest_sha256": manifest_sha256,
            },
            metrics={
                "documents_catalogued": summary.documents,
                "artifacts_preserved": summary.artifacts,
                "inserted_records": summary.inserted_records,
                "existing_records": summary.existing_records,
            },
        )
    return summary


def execute_tcm_monthly_backfill(
    *,
    months: Sequence[tuple[int, int]],
    control_factory: Callable[[int, int], CollectionControl],
    operation_factory: Callable[
        [int, int], Callable[[], TcmBaMonthlyCollectionSummary]
    ],
    logger: logging.Logger,
) -> tuple[TcmBaMonthlyCollectionSummary, ...]:
    completed: list[TcmBaMonthlyCollectionSummary] = []
    failures: list[tuple[int, int, Exception]] = []
    for year, month in months:
        try:
            summary = execute_controlled_tcm_month(
                control=control_factory(year, month),
                operation=operation_factory(year, month),
            )
        except Exception as error:
            failures.append((year, month, error))
            log_event(
                logger,
                logging.ERROR,
                "collector_tcm_ba_month_failed",
                source=SOURCE_CODE,
                competence=f"{month:02d}/{year}",
                error_type=type(error).__name__,
            )
            continue
        if summary is None:
            log_event(
                logger,
                logging.INFO,
                "collector_tcm_ba_month_completed",
                source=SOURCE_CODE,
                competence=f"{month:02d}/{year}",
                coverage_status="blocked",
                documents=0,
                artifacts=0,
                inserted_records=0,
                existing_records=0,
            )
            continue
        completed.append(summary)
        log_event(
            logger,
            logging.INFO,
            "collector_tcm_ba_month_completed",
            source=SOURCE_CODE,
            competence=f"{month:02d}/{year}",
            coverage_status="complete" if summary.documents else "empty",
            documents=summary.documents,
            artifacts=summary.artifacts,
            inserted_records=summary.inserted_records,
            existing_records=summary.existing_records,
        )
    if failures:
        failed = ", ".join(
            f"{year:04d}-{month:02d}" for year, month, _error in failures
        )
        raise RuntimeError(f"A coleta mensal do TCM-BA falhou em: {failed}.") from (
            failures[0][2]
        )
    return tuple(completed)


def main(argv: Sequence[str] | None = None) -> int:
    collected_on = datetime.now(MUNICIPAL_TIMEZONE).date()
    parser = argparse.ArgumentParser(
        description=(
            "Preserva o catálogo mensal do e-TCM e seus documentos listados; "
            "não extrai valores financeiros nesta etapa."
        )
    )
    parser.add_argument("--month-from", help="Competência YYYY-MM")
    parser.add_argument("--month-to", help="Competência YYYY-MM")
    parser.add_argument(
        "--automatic-closed-month",
        action="store_true",
        help="Retoma somente a última competência mensal já encerrada.",
    )
    parser.add_argument("--requests-per-minute", type=int, default=30)
    args = parser.parse_args(argv)
    if args.automatic_closed_month:
        if args.month_from is not None or args.month_to is not None:
            parser.error(
                "--automatic-closed-month não aceita intervalo mensal explícito."
            )
        months = (previous_closed_month(collected_on),)
    else:
        if args.month_from is None or args.month_to is None:
            parser.error("--month-from e --month-to são obrigatórios no modo manual.")
        try:
            months = month_range(
                args.month_from,
                args.month_to,
                collected_on=collected_on,
            )
        except ValueError as error:
            parser.error(str(error))
    if not 1 <= args.requests_per_minute <= 30:
        parser.error("--requests-per-minute deve estar entre 1 e 30.")

    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    if persistence_settings.mode != "postgres-supabase":
        raise RuntimeError(
            "O catálogo TCM-BA requer PERSISTENCE_MODE=postgres-supabase."
        )
    if persistence_settings.database_url is None:
        raise RuntimeError("Configuração de banco incompleta.")

    repository = PostgresCollectionRepository.from_dsn(
        persistence_settings.database_url
    )
    if args.automatic_closed_month:
        year, month = months[0]
        if repository.tcm_ba_monthly_catalog_complete(
            competence=f"{month:02d}/{year}"
        ):
            log_event(
                logging.getLogger(__name__),
                logging.INFO,
                "collector_tcm_ba_month_skipped",
                source=SOURCE_CODE,
                competence=f"{month:02d}/{year}",
                reason="partition_already_complete",
            )
            return 0
    object_store = build_authenticated_object_store(persistence_settings)
    service = TcmBaCatalogPersistenceService(
        object_store=object_store,
        repository=repository,
    )
    logger = logging.getLogger(__name__)

    def control_factory(year: int, month: int) -> CollectionControl:
        start = date(year, month, 1)
        end = _month_end(year, month)
        return CollectionControl(
            repository=repository,
            source_code=SOURCE_CODE,
            endpoint_code=ENDPOINT_CODE,
            idempotency_key=build_execution_idempotency_key(
                f"tcm-ba-monthly-{year:04d}-{month:02d}"
            ),
            collector_version=TCM_BA_COLLECTOR_VERSION,
            parser_version=TCM_BA_PARSER_VERSION,
            partition_key=f"competence:{year:04d}-{month:02d}",
            period_start=start,
            period_end=end,
        )

    def operation_factory(
        year: int,
        month: int,
    ) -> Callable[[], TcmBaMonthlyCollectionSummary]:
        def operation() -> TcmBaMonthlyCollectionSummary:
            catalog = fetch_tcm_ba_monthly_catalog_with_contract_retry(
                year=year,
                month=month,
                requests_per_minute=args.requests_per_minute,
                logger=logger,
            )
            persisted = service.persist(catalog)
            return TcmBaMonthlyCollectionSummary(
                year=year,
                month=month,
                documents=catalog.total_documents,
                artifacts=persisted.artifacts,
                inserted_records=persisted.inserted_records,
                existing_records=persisted.existing_records,
                artifact_hashes=persisted.artifact_hashes,
            )

        return operation

    execute_tcm_monthly_backfill(
        months=months,
        control_factory=control_factory,
        operation_factory=operation_factory,
        logger=logger,
    )
    return 0


def _parse_month(value: str) -> tuple[int, int]:
    if re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", value) is None:
        raise ValueError("Competência inválida; use YYYY-MM.")
    year, month = value.split("-", 1)
    return int(year), int(month)


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


if __name__ == "__main__":
    raise SystemExit(main())
