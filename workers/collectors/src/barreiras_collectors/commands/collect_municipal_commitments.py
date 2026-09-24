"""Preserva os empenhos mensais da Prefeitura (WebRun), um mês fechado por vez.

Cada mês é uma partição controlada (ADR 0086): a grade bruta vai para o
Storage privado por SHA-256 e cada chave oficial vira um registro bruto. Mês
anterior a 2024 termina parcial, porque a série histórica falha na fonte.
"""

from __future__ import annotations

import argparse
import logging
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from ..collection_control import (
    CollectionControl,
    CollectionOutcome,
    PartialCollectionFailure,
    build_execution_idempotency_key,
)
from ..connectors.municipal_expenses import (
    ENDPOINT_CODE,
    FIELD_KEY,
    SOURCE_CODE,
    MonthlyCommitments,
    fetch_monthly_commitments,
    month_bounds,
)
from ..logging import log_event
from ..persistence.models import PersistenceResult
from ..persistence.municipal_commitments import (
    COLLECTOR_VERSION,
    PARSER_VERSION,
    MunicipalCommitmentsPersistenceService,
    commitment_records,
)
from .plan_payroll_backfill import parse_month, plan_months

MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
FIRST_MONTH = date(2021, 1, 1)
# Três requisições por mês; a pausa mantém a fonte bem abaixo de 10/min.
PAUSE_BETWEEN_MONTHS_SECONDS = 20.0
HISTORY_UNAVAILABLE = PartialCollectionFailure(
    error_type="SourceHistoryUnavailable",
    error_detail=(
        "A série histórica anterior a 2024 falha na fonte (SQLException "
        "NUMERO_DESPESA_2); o sistema atual traz só parte do mês."
    ),
    retryable=False,
)


@dataclass(frozen=True)
class MonthOutcome:
    month: str
    outcome: CollectionOutcome
    unique_commitments: int
    inserted_records: int
    existing_records: int
    grid_sha256: str


def previous_closed_month(today: date) -> date:
    if today.month == 1:
        return date(today.year - 1, 12, 1)
    return date(today.year, today.month - 1, 1)


def resolve_months(
    *,
    month: str | None,
    start_month: str | None,
    end_month: str | None,
    max_months: int,
    today: date,
) -> tuple[date, ...]:
    if month and (start_month or end_month):
        raise ValueError("Use --month ou --start-month/--end-month, não ambos.")
    if month:
        months = (parse_month(month),)
    elif start_month or end_month:
        if not (start_month and end_month):
            raise ValueError("Janela exige --start-month e --end-month.")
        months = tuple(
            parse_month(value)
            for value in plan_months(
                start_month=start_month,
                end_month=end_month,
                max_months=max_months,
            )
        )
    else:
        months = (previous_closed_month(today),)
    for value in months:
        if value < FIRST_MONTH:
            raise ValueError("A coleta de empenhos começa em 2021-01.")
        if month_bounds(value.year, value.month)[1] >= today:
            raise ValueError("Somente meses fechados podem ser coletados.")
    return months


def execute_controlled_month(
    *,
    control: CollectionControl,
    operation: Callable[[], tuple[MonthlyCommitments, PersistenceResult]],
) -> MonthOutcome:
    """Declara cobertura só depois de preservar bruto e registros do mês."""
    with control:
        result, persisted = operation()
        unique = len(commitment_records(result))
        prefixes = Counter(row[FIELD_KEY][:2] for row in result.rows)
        complete = result.coverage == "complete"
        outcome = CollectionOutcome.COMPLETE if complete else CollectionOutcome.PARTIAL
        control.complete(
            outcome=outcome,
            observed_records=unique,
            checkpoint={"grid_sha256": result.grid_sha256},
            metrics={
                "coverage": result.coverage,
                "declared_total": result.declared_total,
                "repeated_rows": result.repeated_rows,
                "unique_commitments": unique,
                "budget_rows": prefixes.get("O-", 0),
                "extra_budget_rows": prefixes.get("E-", 0),
                "inserted_records": persisted.inserted_records,
                "existing_records": persisted.existing_records,
                "raw_artifact_id": persisted.raw_artifact_id,
                "grid_bytes": len(result.grid_body),
                "object_created": persisted.object_created,
            },
            partial_failure=None if complete else HISTORY_UNAVAILABLE,
        )
    return MonthOutcome(
        month=f"{result.year:04d}-{result.month:02d}",
        outcome=outcome,
        unique_commitments=unique,
        inserted_records=persisted.inserted_records,
        existing_records=persisted.existing_records,
        grid_sha256=result.grid_sha256,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--month", help="AAAA-MM de um mês fechado")
    parser.add_argument("--start-month")
    parser.add_argument("--end-month")
    parser.add_argument("--max-months", type=int, default=1, choices=(1, 3, 6))
    args = parser.parse_args(argv)

    from ..persistence.postgres import PostgresCollectionRepository
    from ..persistence.storage import SupabaseStorageObjectStore
    from ..settings import CollectorSettings, PersistenceSettings
    from .collect_municipal_transparency import _cloud_client

    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    logger = logging.getLogger(__name__)
    today = datetime.now(MUNICIPAL_TIMEZONE).date()
    months = resolve_months(
        month=args.month,
        start_month=args.start_month,
        end_month=args.end_month,
        max_months=args.max_months,
        today=today,
    )
    if persistence_settings.database_url is None:
        raise RuntimeError("DATABASE_URL é obrigatório para preservar empenhos.")
    repository = PostgresCollectionRepository.from_dsn(
        persistence_settings.database_url
    )
    services: list[MunicipalCommitmentsPersistenceService] = []

    def service() -> MunicipalCommitmentsPersistenceService:
        # Autentica no Storage dentro da primeira partição já aberta.
        if not services:
            client = _cloud_client(persistence_settings)
            bucket = client.storage.from_(persistence_settings.raw_artifacts_bucket)
            services.append(
                MunicipalCommitmentsPersistenceService(
                    object_store=SupabaseStorageObjectStore(bucket),
                    repository=repository,
                )
            )
        return services[0]

    failures = 0
    for position, month in enumerate(months):
        if position:
            time.sleep(PAUSE_BETWEEN_MONTHS_SECONDS)
        first, last = month_bounds(month.year, month.month)
        label = month.strftime("%Y-%m")
        control = CollectionControl(
            repository=repository,
            source_code=SOURCE_CODE,
            endpoint_code=ENDPOINT_CODE,
            idempotency_key=build_execution_idempotency_key(f"commitments-{label}"),
            collector_version=COLLECTOR_VERSION,
            parser_version=PARSER_VERSION,
            partition_key=f"month:{label}",
            period_start=first,
            period_end=last,
        )

        def operation(
            month: date = month,
        ) -> tuple[MonthlyCommitments, PersistenceResult]:
            result = fetch_monthly_commitments(month.year, month.month, today=today)
            return result, service().persist(result)

        try:
            summary = execute_controlled_month(control=control, operation=operation)
        except Exception as error:
            failures += 1
            log_event(
                logger,
                logging.ERROR,
                "collector_municipal_commitments_month_failed",
                source=SOURCE_CODE,
                month=label,
                error_type=type(error).__name__,
            )
            continue
        log_event(
            logger,
            logging.INFO,
            "collector_municipal_commitments_month_preserved",
            source=SOURCE_CODE,
            month=summary.month,
            outcome=summary.outcome.value,
            unique_commitments=summary.unique_commitments,
            inserted_records=summary.inserted_records,
            existing_records=summary.existing_records,
            artifact_hash=summary.grid_sha256,
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
