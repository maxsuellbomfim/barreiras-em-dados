"""Baixa PDF/texto de edições anunciadas pela API, com limites explícitos."""

from __future__ import annotations

import hashlib
import logging
import random
import time
import urllib.error
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from ..http import HttpTransport, UrllibTransport, validate_https_url
from ..logging import log_event
from ..resilience import (
    CircuitBreaker,
    CircuitOpenError,
    PacedRateLimiter,
    RetryPolicy,
)
from .querido_diario import (
    ALLOWED_ARTIFACT_HOSTS,
    RETRYABLE_STATUSES,
    PermanentHttpError,
    QueridoDiarioClient,
    SourceContractError,
    SourceUnavailableError,
)

DOCUMENT_ROLES = frozenset({"pdf", "txt"})
# O CDN devolve tipos imprecisos (ex.: binary/octet-stream); classificamos o
# artefato pelo papel anunciado e preservamos o header observado nos metadados.
DOCUMENT_MEDIA_TYPES = {"pdf": "application/pdf", "txt": "text/plain"}
MUNICIPAL_ARTIFACT_HOSTS = frozenset({"barreiras.mtransparente.com.br"})


@dataclass(frozen=True)
class CollectedDocument:
    role: str
    source_url: str
    final_url: str
    requested_at: str
    received_at: str
    attempts: int
    http_status: int
    body_sha256: str
    body_size_bytes: int
    media_type: str
    response_headers: Mapping[str, str]
    raw_body: bytes


class GazetteDocumentClient:
    """Baixa um documento por vez, somente de hosts oficiais permitidos."""

    def __init__(
        self,
        *,
        max_document_bytes: int,
        allowed_hosts: frozenset[str] = ALLOWED_ARTIFACT_HOSTS,
        source_name: str = "querido-diario",
        endpoint_name: str = "gazette-documents",
        requests_per_minute: int = 30,
        timeout_seconds: float = 35.0,
        retry_policy: RetryPolicy | None = None,
        transport: HttpTransport | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        rate_limiter: PacedRateLimiter | None = None,
        sleep: Callable[[float], None] = time.sleep,
        random_value: Callable[[], float] = random.random,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        logger: logging.Logger | None = None,
    ) -> None:
        if max_document_bytes < 1:
            raise ValueError("max_document_bytes deve ser pelo menos 1.")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds deve ser positivo.")
        self.max_document_bytes = max_document_bytes
        self.allowed_hosts = allowed_hosts
        self.source_name = source_name
        self.endpoint_name = endpoint_name
        self.timeout_seconds = timeout_seconds
        self.retry_policy = retry_policy or RetryPolicy()
        self.transport = transport or UrllibTransport(allowed_hosts)
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.rate_limiter = rate_limiter or PacedRateLimiter(requests_per_minute)
        self.sleep = sleep
        self.random_value = random_value
        self.now = now
        self.logger = logger or logging.getLogger(__name__)

    def fetch(self, url: str, *, role: str) -> CollectedDocument:
        if role not in DOCUMENT_ROLES:
            raise ValueError(f"Papel de documento desconhecido: {role}.")
        validate_https_url(url, self.allowed_hosts)

        try:
            self.circuit_breaker.before_request()
        except CircuitOpenError:
            log_event(
                self.logger,
                logging.WARNING,
                "collector_circuit_open",
                source=self.source_name,
                endpoint=self.endpoint_name,
            )
            raise

        last_error: BaseException | None = None
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            self.rate_limiter.acquire()
            requested_at = self.now().isoformat()
            try:
                response = self.transport.get(
                    url,
                    headers={"User-Agent": "BarreirasEmDados-Collector/0.1"},
                    timeout_seconds=self.timeout_seconds,
                    max_body_bytes=self.max_document_bytes,
                )
            except (OSError, TimeoutError, urllib.error.URLError) as error:
                last_error = error
                if attempt == self.retry_policy.max_attempts:
                    break
                self._backoff(attempt)
                continue

            received_at = self.now().isoformat()
            log_event(
                self.logger,
                logging.INFO,
                "collector_http_response",
                source=self.source_name,
                endpoint=self.endpoint_name,
                status=response.status,
                attempt=attempt,
                body_size_bytes=len(response.body),
            )

            if response.status == 200:
                self.circuit_breaker.record_success()
                self._validate_body(response.body, role=role, url=url)
                return CollectedDocument(
                    role=role,
                    source_url=url,
                    final_url=response.final_url,
                    requested_at=requested_at,
                    received_at=received_at,
                    attempts=attempt,
                    http_status=response.status,
                    body_sha256=hashlib.sha256(response.body).hexdigest(),
                    body_size_bytes=len(response.body),
                    media_type=DOCUMENT_MEDIA_TYPES[role],
                    response_headers=QueridoDiarioClient._safe_response_headers(
                        response.headers
                    ),
                    raw_body=response.body,
                )

            if response.status not in RETRYABLE_STATUSES:
                self.circuit_breaker.record_success()
                raise PermanentHttpError(
                    f"Documento respondeu HTTP {response.status}.",
                    status_code=response.status,
                )

            last_error = SourceUnavailableError(
                f"Documento respondeu HTTP {response.status}."
            )
            if attempt < self.retry_policy.max_attempts:
                self._backoff(attempt)

        self.circuit_breaker.record_failure()
        log_event(
            self.logger,
            logging.ERROR,
            "collector_source_unavailable",
            source=self.source_name,
            endpoint=self.endpoint_name,
            attempts=self.retry_policy.max_attempts,
            error_type=type(last_error).__name__ if last_error else "unknown",
        )
        raise SourceUnavailableError(
            "Documento indisponível após "
            f"{self.retry_policy.max_attempts} tentativas."
        ) from last_error

    @staticmethod
    def _validate_body(body: bytes, *, role: str, url: str) -> None:
        if not body:
            raise SourceContractError(f"Documento vazio em {url}.")
        if role == "pdf" and not body.startswith(b"%PDF-"):
            raise SourceContractError(
                f"O corpo baixado de {url} não é um PDF válido."
            )

    def _backoff(self, attempt: int) -> None:
        self.sleep(self.retry_policy.delay(attempt, self.random_value()))


class MunicipalTransparencyDocumentClient(GazetteDocumentClient):
    """Baixa documentos apontados pela API municipal, com allowlist própria."""

    def __init__(self, **kwargs) -> None:
        super().__init__(
            allowed_hosts=MUNICIPAL_ARTIFACT_HOSTS,
            source_name="municipal-transparency",
            endpoint_name="financial-documents",
            **kwargs,
        )
