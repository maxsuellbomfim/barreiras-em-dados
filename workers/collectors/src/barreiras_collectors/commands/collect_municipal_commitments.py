"""Preserva empenhos e liquidações mensais da Prefeitura (WebRun), mês a mês.

Cada mês de cada estágio é uma partição controlada do seu endpoint (ADR 0086):
a grade bruta vai para o Storage privado por SHA-256 e cada linha distinta vira
registro bruto. Mês anterior a 2024 termina parcial, porque a série histórica
falha na fonte.
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
    SOURCE_CODE,
    STAGES,
    MonthlyGrid,
    fetch_monthly_grid,
    month_bounds,
)
from ..logging import log_event
from ..persistence.models import PersistenceResult
from ..persistence.municipal_commitments import (
    STAGE_PERSISTENCE,
    MunicipalCommitmentsPersistenceService,
    stage_records,
)
from .plan_payroll_backfill import parse_month, plan_months

MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
FIRST_MONTH = date(2021, 1, 1)
# Três requisições por grade; a pausa mantém a fonte bem abaixo de 10/min.
PAUSE_BETWEEN_GRIDS_SECONDS = 20.0
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
    stage: str
    month: str
    outcome: CollectionOutcome
    unique_records: int
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
    operation: Callable[[], tuple[MonthlyGrid, PersistenceResult]],
) -> MonthOutcome:
    """Declara cobertura só depois de preservar bruto e registros do mês."""
    with control:
        result, persisted = operation()
        unique = len(stage_records(result))
        key_field = STAGES[result.stage].key_field
        prefixes = Counter(row[key_field][:2] for row in result.rows)
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
                "stage": result.stage,
                "unique_records": unique,
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
        stage=result.stage,
        month=f"{result.year:04d}-{result.month:02d}",
        outcome=outcome,
        unique_records=unique,
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
    parser.add_argument(
        "--stage", choices=(*STAGES, "todos"), default="todos", help="estágio"
    )
    args = parser.parse_args(argv)
    stages = tuple(STAGES) if args.stage == "todos" else (args.stage,)

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
    grids = [(month, stage) for month in months for stage in stages]
    for position, (month, stage) in enumerate(grids):
        if position:
            time.sleep(PAUSE_BETWEEN_GRIDS_SECONDS)
        first, last = month_bounds(month.year, month.month)
        label = month.strftime("%Y-%m")
        spec = STAGES[stage]
        persistence = STAGE_PERSISTENCE[stage]
        namespace = "commitments" if stage == "empenhos" else stage
        control = CollectionControl(
            repository=repository,
            source_code=SOURCE_CODE,
            endpoint_code=spec.endpoint_code,
            idempotency_key=build_execution_idempotency_key(f"{namespace}-{label}"),
            collector_version=persistence.collector_version,
            parser_version=persistence.parser_version,
            partition_key=f"month:{label}",
            period_start=first,
            period_end=last,
        )

        def operation(
            month: date = month,
            spec=spec,
        ) -> tuple[MonthlyGrid, PersistenceResult]:
            result = fetch_monthly_grid(spec, month.year, month.month, today=today)
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
                stage=stage,
                month=label,
                error_type=type(error).__name__,
            )
            continue
        log_event(
            logger,
            logging.INFO,
            "collector_municipal_commitments_month_preserved",
            source=SOURCE_CODE,
            stage=summary.stage,
            month=summary.month,
            outcome=summary.outcome.value,
            unique_records=summary.unique_records,
            inserted_records=summary.inserted_records,
            existing_records=summary.existing_records,
            artifact_hash=summary.grid_sha256,
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
