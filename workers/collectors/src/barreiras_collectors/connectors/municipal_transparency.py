"""Cliente paginado para as APIs de dados abertos municipais de Barreiras.

Esta etapa preserva a resposta oficial como JSON bruto. Ela não converte
valores monetários nem publica totais: a normalização financeira terá um
contrato próprio depois que a cobertura e o formato vivo forem confirmados.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import time
import urllib.error
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlencode, urlparse

from ..http import HttpTransport, UrllibTransport, validate_https_url
from ..logging import log_event
from ..resilience import (
    CircuitBreaker,
    CircuitOpenError,
    PacedRateLimiter,
    RetryPolicy,
)

PREFEITURA_BASE_URL = "https://portaldatransparencia.barreiras.ba.gov.br/api"
CAMARA_BASE_URL = "https://portaldatransparencia.cmbarreiras.ba.gov.br/api"
ALLOWED_HOSTS = frozenset(
    {
        "portaldatransparencia.barreiras.ba.gov.br",
        "portaldatransparencia.cmbarreiras.ba.gov.br",
    }
)
SOURCE_CODES = frozenset(
    {
        "prefeitura-barreiras-transparencia",
        "camara-barreiras-transparencia",
    }
)
SOURCE_HOSTS = {
    "prefeitura-barreiras-transparencia":
    "portaldatransparencia.barreiras.ba.gov.br",
    "camara-barreiras-transparencia":
    "portaldatransparencia.cmbarreiras.ba.gov.br",
}
RETRYABLE_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
RESOURCE_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class MunicipalTransparencyError(RuntimeError):
    """Falha explícita no contrato ou na disponibilidade da fonte."""


class MunicipalTransparencyAvailabilityError(MunicipalTransparencyError):
    """A fonte não respondeu após todas as tentativas de transporte."""


class MunicipalTransparencyContractError(MunicipalTransparencyError):
    """A resposta não atende ao contrato observado da API."""


@dataclass(frozen=True)
class MunicipalTransparencyPage:
    schema_name: str
    schema_version: str
    source_code: str
    endpoint_code: str
    resource: str
    idempotency_key: str
    request_url: str
    final_url: str
    requested_at: str
    received_at: str
    attempts: int
    http_status: int
    collection_status: str
    body_sha256: str
    body_size_bytes: int
    media_type: str
    response_headers: Mapping[str, str]
    cursor: Mapping[str, int]
    raw_body: bytes
    items: tuple[dict, ...]
    window_start: str | None = None
    window_end: str | None = None


def iter_resource_pages(
    *,
    base_url: str,
    source_code: str,
    resource: str,
    limit: int = 50,
    offset: int = 0,
    query: Mapping[str, str] | None = None,
    transport: HttpTransport | None = None,
    retry_policy: RetryPolicy | None = None,
    requests_per_minute: int = 10,
    timeout_seconds: float = 30.0,
    max_body_bytes: int = 16 * 1024 * 1024,
    circuit_breaker: CircuitBreaker | None = None,
    rate_limiter: PacedRateLimiter | None = None,
    sleep: Callable[[float], None] = time.sleep,
    random_value: Callable[[], float] = random.random,
    logger: logging.Logger | None = None,
) -> Iterator[MunicipalTransparencyPage]:
    """Percorre páginas até a fonte retornar menos que ``limit`` registros."""
    _validate_inputs(base_url, source_code, resource, limit, offset)
    if timeout_seconds <= 0 or max_body_bytes < 1:
        raise ValueError("timeout_seconds e max_body_bytes devem ser positivos.")

    active_transport = transport or UrllibTransport(ALLOWED_HOSTS)
    policy = retry_policy or RetryPolicy(max_attempts=4)
    breaker = circuit_breaker or CircuitBreaker()
    limiter = rate_limiter or PacedRateLimiter(requests_per_minute)
    log = logger or logging.getLogger(__name__)
    current_offset = offset
    seen_page_hashes: set[str] = set()

    while True:
        request_url = _build_url(
            base_url,
            resource,
            limit=limit,
            offset=current_offset,
            query=query,
        )
        response, requested_at, received_at, attempts = _get_with_retries(
            request_url,
            transport=active_transport,
            retry_policy=policy,
            circuit_breaker=breaker,
            rate_limiter=limiter,
            sleep=sleep,
            random_value=random_value,
            timeout_seconds=timeout_seconds,
            max_body_bytes=max_body_bytes,
            logger=log,
        )
        items = _parse_success(response.body, resource)
        body_sha256 = hashlib.sha256(response.body).hexdigest()
        if body_sha256 in seen_page_hashes:
            raise MunicipalTransparencyError(
                "A API municipal repetiu uma página durante a paginação; "
                "coleta interrompida para evitar loop infinito."
            )
        seen_page_hashes.add(body_sha256)
        yield MunicipalTransparencyPage(
            schema_name="municipal-transparency-api-response",
            schema_version="1.0.0",
            source_code=source_code,
            endpoint_code="dados-abertos-api",
            resource=resource,
            idempotency_key=hashlib.sha256(
                f"{request_url}:{body_sha256}".encode()
            ).hexdigest(),
            request_url=request_url,
            final_url=response.final_url,
            requested_at=requested_at,
            received_at=received_at,
            attempts=attempts,
            http_status=response.status,
            collection_status="empty" if not items else "success",
            body_sha256=body_sha256,
            body_size_bytes=len(response.body),
            media_type=_media_type(response.headers),
            response_headers=_safe_headers(response.headers),
            cursor={"offset": current_offset, "size": limit},
            raw_body=response.body,
            items=tuple(items),
        )
        if len(items) < limit:
            return
        current_offset += limit


def _validate_inputs(
    base_url: str,
    source_code: str,
    resource: str,
    limit: int,
    offset: int,
) -> None:
    validate_https_url(base_url, ALLOWED_HOSTS)
    if source_code not in SOURCE_CODES:
        raise ValueError(f"source_code não permitido: {source_code}.")
    if urlparse(base_url).hostname != SOURCE_HOSTS[source_code]:
        raise ValueError("base_url não corresponde ao source_code informado.")
    if not resource or re.fullmatch(RESOURCE_PATTERN, resource) is None:
        raise ValueError("resource deve ser um slug minúsculo com hífens.")
    if not 1 <= limit <= 500:
        raise ValueError("limit deve estar entre 1 e 500.")
    if offset < 0:
        raise ValueError("offset não pode ser negativo.")


def _build_url(
    base_url: str,
    resource: str,
    *,
    limit: int,
    offset: int,
    query: Mapping[str, str] | None,
) -> str:
    params: list[tuple[str, str]] = [
        ("resource", resource),
        ("limit", str(limit)),
        ("offset", str(offset)),
    ]
    if query:
        params.extend(sorted((str(key), str(value)) for key, value in query.items()))
    return f"{base_url.rstrip('/')}?{urlencode(params)}"


def _get_with_retries(
    request_url: str,
    *,
    transport: HttpTransport,
    retry_policy: RetryPolicy,
    circuit_breaker: CircuitBreaker,
    rate_limiter: PacedRateLimiter,
    sleep: Callable[[float], None],
    random_value: Callable[[], float],
    timeout_seconds: float,
    max_body_bytes: int,
    logger: logging.Logger,
):
    try:
        circuit_breaker.before_request()
    except CircuitOpenError:
        log_event(
            logger,
            logging.WARNING,
            "collector_circuit_open",
            source="municipal-transparency",
            endpoint="dados-abertos-api",
        )
        raise

    last_error: BaseException | None = None
    for attempt in range(1, retry_policy.max_attempts + 1):
        rate_limiter.acquire()
        requested_at = datetime.now(UTC).isoformat()
        try:
            response = transport.get(
                request_url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "BarreirasEmDados-Collector/0.1",
                },
                timeout_seconds=timeout_seconds,
                max_body_bytes=max_body_bytes,
            )
        except (OSError, TimeoutError, urllib.error.URLError) as error:
            last_error = error
            circuit_breaker.record_failure()
            if attempt == retry_policy.max_attempts:
                break
            sleep(retry_policy.delay(attempt, random_value()))
            continue

        received_at = datetime.now(UTC).isoformat()
        log_event(
            logger,
            logging.INFO,
            "collector_http_response",
            source="municipal-transparency",
            endpoint="dados-abertos-api",
            status=response.status,
            attempt=attempt,
            body_size_bytes=len(response.body),
        )
        if response.status == 200:
            circuit_breaker.record_success()
            return response, requested_at, received_at, attempt
        if response.status not in RETRYABLE_STATUSES:
            circuit_breaker.record_success()
            raise MunicipalTransparencyError(
                f"A API municipal respondeu HTTP {response.status}.",
            )
        last_error = MunicipalTransparencyError(
            f"A API municipal respondeu HTTP {response.status}."
        )
        circuit_breaker.record_failure()
        if attempt < retry_policy.max_attempts:
            sleep(retry_policy.delay(attempt, random_value()))

    raise MunicipalTransparencyAvailabilityError(
        "A API municipal ficou indisponível após as tentativas configuradas."
    ) from last_error


def _parse_success(body: bytes, expected_resource: str) -> list[dict]:
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MunicipalTransparencyContractError(
            "A API municipal não devolveu JSON UTF-8 válido."
        ) from error
    if not isinstance(payload, dict):
        raise MunicipalTransparencyContractError("A raiz da resposta deve ser objeto.")
    if "error" in payload:
        raise MunicipalTransparencyContractError(
            f"A API municipal devolveu erro em HTTP 200: {payload.get('error')!s}"
        )
    if payload.get("resource") != expected_resource:
        raise MunicipalTransparencyContractError(
            "O resource retornado diverge do resource solicitado."
        )
    count = payload.get("count")
    items = payload.get("data")
    if not isinstance(count, int) or count < 0 or not isinstance(items, list):
        raise MunicipalTransparencyContractError(
            "Resposta sem resource, count inteiro ou data em lista."
        )
    if count != len(items):
        raise MunicipalTransparencyContractError(
            "count deve representar a quantidade de linhas retornadas."
        )
    if not all(isinstance(item, dict) for item in items):
        raise MunicipalTransparencyContractError("Cada item de data deve ser objeto.")
    return items


def _media_type(headers: Mapping[str, str]) -> str:
    return next(
        (
            value.split(";", 1)[0].strip().lower()
            for key, value in headers.items()
            if key.lower() == "content-type"
        ),
        "application/json",
    )


def _safe_headers(headers: Mapping[str, str]) -> dict[str, str]:
    blocked = {"authorization", "cookie", "set-cookie"}
    return {
        str(key).lower(): str(value)
        for key, value in headers.items()
        if str(key).lower() not in blocked
    }
