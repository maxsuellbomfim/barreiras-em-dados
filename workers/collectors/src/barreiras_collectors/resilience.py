"""Primitivas pequenas e determinísticas de resiliência para coletores."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """O endpoint está temporariamente bloqueado após falhas consecutivas."""


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 5
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts deve ser pelo menos 1.")
        if self.base_delay_seconds < 0:
            raise ValueError("base_delay_seconds não pode ser negativo.")
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("max_delay_seconds deve ser >= base_delay_seconds.")

    def delay(self, attempt: int, random_value: float) -> float:
        """Full jitter limitado; attempt começa em 1."""
        ceiling = min(
            self.max_delay_seconds,
            self.base_delay_seconds * (2 ** max(0, attempt - 1)),
        )
        return ceiling * min(1.0, max(0.0, random_value))


class PacedRateLimiter:
    """Distribui chamadas no tempo; adequado a um único processo de worker."""

    def __init__(
        self,
        requests_per_minute: int,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if requests_per_minute < 1:
            raise ValueError("requests_per_minute deve ser pelo menos 1.")
        self._minimum_interval = 60.0 / requests_per_minute
        self._monotonic = monotonic
        self._sleep = sleep
        self._next_allowed_at = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = self._monotonic()
            wait_for = max(0.0, self._next_allowed_at - now)
            if wait_for:
                self._sleep(wait_for)
                now = self._monotonic()
            self._next_allowed_at = now + self._minimum_interval


class CircuitBreaker:
    """Circuit breaker em processo; estado compartilhado exige storage externo."""

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        recovery_timeout_seconds: float = 60.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold deve ser pelo menos 1.")
        if recovery_timeout_seconds <= 0:
            raise ValueError("recovery_timeout_seconds deve ser positivo.")
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self._monotonic = monotonic
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.opened_at: float | None = None
        self._lock = threading.Lock()

    def before_request(self) -> None:
        with self._lock:
            if self.state is not CircuitState.OPEN:
                return
            if self.opened_at is None:
                raise RuntimeError("Circuit breaker aberto sem instante de abertura.")
            elapsed = self._monotonic() - self.opened_at
            if elapsed < self.recovery_timeout_seconds:
                raise CircuitOpenError(
                    "Circuito aberto; aguarde o período de recuperação."
                )
            self.state = CircuitState.HALF_OPEN

    def record_success(self) -> None:
        with self._lock:
            self.state = CircuitState.CLOSED
            self.failures = 0
            self.opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self.failures += 1
            if (
                self.state is CircuitState.HALF_OPEN
                or self.failures >= self.failure_threshold
            ):
                self.state = CircuitState.OPEN
                self.opened_at = self._monotonic()
