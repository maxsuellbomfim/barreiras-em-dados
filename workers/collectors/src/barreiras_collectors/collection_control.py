"""Controle auditável de execução e cobertura dos coletores."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from hashlib import sha256
from types import TracebackType
from typing import Protocol
from uuid import uuid4


class CollectionOutcome(StrEnum):
    COMPLETE = "complete"
    EMPTY = "empty"
    PARTIAL = "partial"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class PartialCollectionFailure:
    """Falha recuperável que não invalida os registros já preservados."""

    error_type: str
    error_detail: str
    retryable: bool = True


class CollectionControlRepository(Protocol):
    def start_controlled_run(self, **values: object) -> str: ...

    def complete_controlled_run(self, **values: object) -> None: ...

    def fail_controlled_run(self, **values: object) -> None: ...


_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(authorization|api[_-]?key|password|secret|token)=([^&\s]+)"
)
_BEARER_TOKEN = re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]+")


def build_execution_idempotency_key(
    namespace: str,
    *,
    environment: Mapping[str, str] | None = None,
    nonce_factory: Callable[[], str] | None = None,
) -> str:
    """Identifica uma tentativa sem expor metadados do executor.

    No GitHub Actions, a mesma tentativa é estável para tolerar replay do
    processo, enquanto ``run_attempt`` garante uma nova linha a cada retry.
    Fora do Actions, cada invocação recebe um nonce novo.
    """
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,40}", namespace):
        raise ValueError("namespace de execução inválido")
    values = environment if environment is not None else os.environ
    run_id = values.get("GITHUB_RUN_ID", "").strip()
    if run_id:
        material = "\x1f".join(
            (
                namespace,
                values.get("GITHUB_REPOSITORY", ""),
                values.get("GITHUB_WORKFLOW", ""),
                run_id,
                values.get("GITHUB_RUN_ATTEMPT", "1"),
            )
        )
    else:
        make_nonce = nonce_factory or (lambda: uuid4().hex)
        material = f"{namespace}\x1flocal\x1f{make_nonce()}"
    return f"{namespace}:execution:{sha256(material.encode('utf-8')).hexdigest()}"


def sanitize_error_detail(error: BaseException) -> str:
    detail = str(error).replace("\x00", "").replace("\r", " ").replace("\n", " ")
    detail = _SECRET_ASSIGNMENT.sub(r"\1=[REDACTED]", detail)
    detail = _BEARER_TOKEN.sub("Bearer [REDACTED]", detail)
    return detail[:500]


@dataclass
class CollectionControl:
    repository: CollectionControlRepository
    source_code: str
    endpoint_code: str
    idempotency_key: str
    collector_version: str
    partition_key: str
    period_start: date
    period_end: date
    parser_version: str = "not-applicable"
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    _run_id: str | None = field(init=False, default=None)
    _terminal: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        if self.period_start > self.period_end:
            raise ValueError("period_start não pode ser posterior a period_end")
        if len(self.idempotency_key) < 16:
            raise ValueError("idempotency_key deve ter pelo menos 16 caracteres")

    def __enter__(self) -> CollectionControl:
        started_at = self.clock()
        self._run_id = self.repository.start_controlled_run(
            source_code=self.source_code,
            endpoint_code=self.endpoint_code,
            idempotency_key=self.idempotency_key,
            collector_version=self.collector_version,
            parser_version=self.parser_version,
            period_start=self.period_start,
            period_end=self.period_end,
            started_at=started_at,
        )
        return self

    def complete(
        self,
        *,
        outcome: CollectionOutcome,
        observed_records: int,
        checkpoint: Mapping[str, object] | None = None,
        metrics: Mapping[str, object] | None = None,
        block_reason: str | None = None,
        partial_failure: PartialCollectionFailure | None = None,
    ) -> None:
        if self._run_id is None:
            raise RuntimeError("A execução ainda não foi iniciada.")
        if self._terminal:
            raise RuntimeError("A execução já foi finalizada.")
        if observed_records < 0:
            raise ValueError("observed_records não pode ser negativo")
        if outcome is CollectionOutcome.EMPTY and observed_records != 0:
            raise ValueError("Uma partição vazia deve observar zero registros.")
        if outcome is CollectionOutcome.BLOCKED and not (block_reason or "").strip():
            raise ValueError("Uma partição bloqueada exige block_reason.")
        if partial_failure is not None and outcome is not CollectionOutcome.PARTIAL:
            raise ValueError("Uma falha parcial exige cobertura parcial.")
        if partial_failure is not None and not partial_failure.error_type.strip():
            raise ValueError("Uma falha parcial exige error_type.")

        sanitized_partial_failure = None
        if partial_failure is not None:
            sanitized_partial_failure = {
                "error_type": partial_failure.error_type.strip()[:120],
                "error_detail": sanitize_error_detail(
                    RuntimeError(partial_failure.error_detail)
                ),
                "retryable": partial_failure.retryable,
            }

        self.repository.complete_controlled_run(
            run_id=self._run_id,
            partition_key=self.partition_key,
            period_start=self.period_start,
            period_end=self.period_end,
            outcome=outcome.value,
            observed_records=observed_records,
            checkpoint=dict(checkpoint or {}),
            metrics=dict(metrics or {}),
            block_reason=block_reason.strip() if block_reason else None,
            partial_failure=sanitized_partial_failure,
            completed_at=self.clock(),
        )
        self._terminal = True

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        del traceback
        if exc_value is not None and self._run_id is not None and not self._terminal:
            self.repository.fail_controlled_run(
                run_id=self._run_id,
                partition_key=self.partition_key,
                period_start=self.period_start,
                period_end=self.period_end,
                error_type=exc_type.__name__ if exc_type else "Exception",
                error_detail=sanitize_error_detail(exc_value),
                retryable=not isinstance(
                    exc_value, (AssertionError, TypeError, ValueError)
                ),
                failed_at=self.clock(),
            )
            self._terminal = True
        elif exc_value is None and self._run_id is not None and not self._terminal:
            error = RuntimeError("A execução terminou sem declarar cobertura.")
            self.repository.fail_controlled_run(
                run_id=self._run_id,
                partition_key=self.partition_key,
                period_start=self.period_start,
                period_end=self.period_end,
                error_type=type(error).__name__,
                error_detail=str(error),
                retryable=False,
                failed_at=self.clock(),
            )
            raise error
        return False
