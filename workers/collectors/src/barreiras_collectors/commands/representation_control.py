"""Controle comum de cobertura para snapshots de representação política."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date

from ..collection_control import (
    CollectionControl,
    CollectionControlRepository,
    CollectionOutcome,
    build_execution_idempotency_key,
)


@dataclass(frozen=True)
class RepresentationCollectionSummary:
    """Resultado explícito de uma partição de representação."""

    observed_records: int
    outcome: CollectionOutcome
    metrics: Mapping[str, object] = field(default_factory=dict)
    checkpoint: Mapping[str, object] = field(default_factory=dict)
    block_reason: str | None = None

    def __post_init__(self) -> None:
        if self.observed_records < 0:
            raise ValueError("observed_records não pode ser negativo")
        if self.outcome is CollectionOutcome.EMPTY and self.observed_records != 0:
            raise ValueError("Uma partição vazia deve observar zero registros.")
        if self.outcome is CollectionOutcome.BLOCKED and not (
            self.block_reason or ""
        ).strip():
            raise ValueError("Uma partição bloqueada exige block_reason.")


def execute_controlled_representation(
    *,
    control: CollectionControl,
    operation: Callable[[], RepresentationCollectionSummary],
) -> RepresentationCollectionSummary:
    """Abre a execução antes de autenticar ou consultar uma fonte externa."""

    with control:
        summary = operation()
        control.complete(
            outcome=summary.outcome,
            observed_records=summary.observed_records,
            checkpoint=summary.checkpoint,
            metrics=summary.metrics,
            block_reason=summary.block_reason,
        )
    return summary


def build_representation_control(
    *,
    repository: CollectionControlRepository,
    source_code: str,
    endpoint_code: str,
    namespace: str,
    collector_version: str,
    parser_version: str,
    partition_key: str,
    snapshot_date: date,
) -> CollectionControl:
    """Cria uma partição diária sem misturar fonte, endpoint ou eleição."""

    return CollectionControl(
        repository=repository,
        source_code=source_code,
        endpoint_code=endpoint_code,
        idempotency_key=build_execution_idempotency_key(namespace),
        collector_version=collector_version,
        parser_version=parser_version,
        partition_key=partition_key,
        period_start=snapshot_date,
        period_end=snapshot_date,
    )
