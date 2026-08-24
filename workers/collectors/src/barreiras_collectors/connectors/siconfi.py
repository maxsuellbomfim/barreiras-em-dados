"""Aquisição estrita da Declaração das Contas Anuais do SICONFI."""

from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlencode, urlparse

from ..http import (
    RETRYABLE_TRANSPORT_EXCEPTIONS,
    HttpResponse,
    HttpTransport,
    ResponseTooLargeError,
    UrllibTransport,
    validate_https_url,
)
from ..logging import log_event
from ..resilience import CircuitBreaker, PacedRateLimiter, RetryPolicy

SOURCE_CODE = "siconfi-barreiras"
ENDPOINT_CODE = "dca"
BARREIRAS_IBGE_CODE = 2903201
BASE_URL = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca"
OFFICIAL_HOSTS = frozenset({"apidatalake.tesouro.gov.br"})
OFFICIAL_PATHS = frozenset(
    {"/ords/siconfi/tt/dca", "/ords/cdwhprd/siconfi/tt/dca"}
)
SAFE_RESPONSE_HEADERS = frozenset(
    {"content-type", "content-length", "etag", "last-modified", "date"}
)
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
EXPECTED_PAGE_KEYS = frozenset(
    {"items", "hasMore", "limit", "offset", "count", "links"}
)
EXPECTED_ITEM_KEYS = frozenset(
    {
        "exercicio",
        "instituicao",
        "cod_ibge",
        "uf",
        "anexo",
        "rotulo",
        "coluna",
        "cod_conta",
        "conta",
        "valor",
        "populacao",
    }
)
MAX_PAGE_BYTES = 8 * 1024 * 1024
MAX_PAGES = 100
MAX_TOTAL_ITEMS = 100_000
TIMEOUT_SECONDS = 60.0


class SiconfiContractError(RuntimeError):
    """A resposta não permite afirmar cobertura DCA com segurança."""


@dataclass(frozen=True)
class ParsedSiconfiDcaPage:
    items: tuple[dict[str, object], ...]
    has_more: bool
    limit: int
    offset: int
    count: int


@dataclass(frozen=True)
class SiconfiDcaPage:
    schema_name: str
    schema_version: str
    artifact_kind: str
    source_code: str
    endpoint_code: str
    idempotency_key: str
    request_url: str
    final_url: str
    requested_at: str
    received_at: str
    window_start: str
    window_end: str
    attempts: int
    http_status: int
    collection_status: str
    body_sha256: str
    body_size_bytes: int
    media_type: str
    response_headers: dict[str, str]
    cursor: dict[str, int]
    raw_body: bytes
    items: tuple[dict[str, object], ...]
    total_pages: int
    total_items: int
    year: int
    offset: int
    limit: int
    has_more: bool


def fetch_siconfi_dca(
    *,
    year: int,
    page_size: int = 5000,
    transport: HttpTransport | None = None,
    rate_limiter: PacedRateLimiter | None = None,
    retry_policy: RetryPolicy | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    random_value: Callable[[], float] = random.random,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> tuple[SiconfiDcaPage, ...]:
    """Coleta todas as páginas anuais sem seguir links internos da resposta."""
    if not 2013 <= year <= 2100:
        raise ValueError("O exercício DCA deve estar entre 2013 e 2100.")
    if not 1 <= page_size <= 5000:
        raise ValueError("page_size deve estar entre 1 e 5000.")

    active_transport = transport or UrllibTransport(OFFICIAL_HOSTS)
    limiter = rate_limiter or PacedRateLimiter(60)
    policy = retry_policy or RetryPolicy(max_attempts=4)
    breaker = circuit_breaker or CircuitBreaker(
        failure_threshold=policy.max_attempts
    )
    log = logger or logging.getLogger(__name__)
    pages: list[SiconfiDcaPage] = []
    identities: set[tuple[object, ...]] = set()
    offset = 0
    total_items = 0

    while True:
        if len(pages) >= MAX_PAGES:
            raise SiconfiContractError("A paginação excedeu o limite contratado.")
        page = _fetch_page(
            year=year,
            offset=offset,
            page_size=page_size,
            transport=active_transport,
            rate_limiter=limiter,
            retry_policy=policy,
            circuit_breaker=breaker,
            random_value=random_value,
            now=now,
            sleep=sleep,
            logger=log,
        )
        for item in page.items:
            identity = _item_identity(item)
            if identity in identities:
                raise SiconfiContractError(
                    "A fonte repetiu uma identidade DCA entre páginas."
                )
            identities.add(identity)
        pages.append(page)
        total_items += len(page.items)
        if total_items > MAX_TOTAL_ITEMS:
            raise SiconfiContractError("A DCA excedeu o volume máximo contratado.")
        if not page.has_more:
            return tuple(pages)
        offset += len(page.items)


def parse_siconfi_dca_page(
    body: bytes,
    *,
    expected_year: int,
    expected_offset: int,
    expected_limit: int,
) -> ParsedSiconfiDcaPage:
    """Valida envelope e linhas, mantendo valores monetários como texto decimal."""
    try:
        payload = json.loads(
            body.decode("utf-8"),
            parse_float=Decimal,
            parse_constant=lambda value: (_raise_non_finite(value)),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, InvalidOperation) as error:
        raise SiconfiContractError("A resposta DCA não é JSON válido.") from error
    if not isinstance(payload, dict) or frozenset(payload) != EXPECTED_PAGE_KEYS:
        raise SiconfiContractError("O envelope da DCA diverge do contrato oficial.")

    items = payload["items"]
    has_more = payload["hasMore"]
    limit = payload["limit"]
    offset = payload["offset"]
    count = payload["count"]
    links = payload["links"]
    if (
        not isinstance(items, list)
        or not isinstance(has_more, bool)
        or not _is_int(limit)
        or not _is_int(offset)
        or not _is_int(count)
        or not isinstance(links, list)
        or limit != expected_limit
        or offset != expected_offset
        or count != len(items)
        or count < 0
        or count > limit
        or (has_more and count == 0)
    ):
        raise SiconfiContractError("A paginação da DCA é incoerente.")

    normalized: list[dict[str, object]] = []
    identities: set[tuple[object, ...]] = set()
    for index, raw_item in enumerate(items):
        item = _normalize_item(raw_item, expected_year=expected_year, index=index)
        identity = _item_identity(item)
        if identity in identities:
            raise SiconfiContractError(
                "A fonte publicou uma identidade DCA duplicada na página."
            )
        identities.add(identity)
        normalized.append(item)
    return ParsedSiconfiDcaPage(
        items=tuple(normalized),
        has_more=has_more,
        limit=limit,
        offset=offset,
        count=count,
    )


def _fetch_page(
    *,
    year: int,
    offset: int,
    page_size: int,
    transport: HttpTransport,
    rate_limiter: PacedRateLimiter,
    retry_policy: RetryPolicy,
    circuit_breaker: CircuitBreaker,
    random_value: Callable[[], float],
    now: Callable[[], datetime],
    sleep: Callable[[float], None],
    logger: logging.Logger,
) -> SiconfiDcaPage:
    query = urlencode(
        {
            "an_exercicio": year,
            "id_ente": BARREIRAS_IBGE_CODE,
            "limit": page_size,
            "offset": offset,
        }
    )
    request_url = f"{BASE_URL}?{query}"
    for attempt in range(1, retry_policy.max_attempts + 1):
        circuit_breaker.before_request()
        rate_limiter.acquire()
        requested_at = now().isoformat()
        try:
            response = transport.get(
                request_url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Barreiras360-Collector/0.1",
                },
                timeout_seconds=TIMEOUT_SECONDS,
                max_body_bytes=MAX_PAGE_BYTES,
            )
        except ResponseTooLargeError as error:
            circuit_breaker.record_failure()
            raise SiconfiContractError(
                "A página DCA excedeu o limite de segurança."
            ) from error
        except RETRYABLE_TRANSPORT_EXCEPTIONS as error:
            circuit_breaker.record_failure()
            if attempt < retry_policy.max_attempts:
                sleep(retry_policy.delay(attempt, random_value()))
                continue
            raise SiconfiContractError("A API DCA ficou indisponível.") from error

        received_at = now().isoformat()
        log_event(
            logger,
            logging.INFO,
            "collector_http_response",
            source=SOURCE_CODE,
            endpoint=ENDPOINT_CODE,
            status=response.status,
            attempt=attempt,
            body_size_bytes=len(response.body),
            year=year,
            offset=offset,
        )
        if response.status == 200:
            page = _snapshot_from_response(
                response,
                request_url=request_url,
                requested_at=requested_at,
                received_at=received_at,
                attempts=attempt,
                year=year,
                offset=offset,
                page_size=page_size,
            )
            circuit_breaker.record_success()
            return page
        if response.status not in RETRYABLE_HTTP_STATUSES:
            raise SiconfiContractError(
                f"A API DCA respondeu HTTP {response.status}."
            )
        circuit_breaker.record_failure()
        if attempt < retry_policy.max_attempts:
            sleep(retry_policy.delay(attempt, random_value()))
    raise SiconfiContractError("A API DCA ficou indisponível.")


def _snapshot_from_response(
    response: HttpResponse,
    *,
    request_url: str,
    requested_at: str,
    received_at: str,
    attempts: int,
    year: int,
    offset: int,
    page_size: int,
) -> SiconfiDcaPage:
    _validate_final_url(
        response.final_url,
        year=year,
        offset=offset,
        page_size=page_size,
    )
    headers = {str(key).lower(): str(value) for key, value in response.headers.items()}
    media_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        raise SiconfiContractError("A API DCA não respondeu application/json.")
    content_length = headers.get("content-length")
    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError as error:
            raise SiconfiContractError("Content-Length inválido na DCA.") from error
        if declared_size != len(response.body):
            raise SiconfiContractError("Content-Length diverge dos bytes da DCA.")
    parsed = parse_siconfi_dca_page(
        response.body,
        expected_year=year,
        expected_offset=offset,
        expected_limit=page_size,
    )
    body_sha256 = hashlib.sha256(response.body).hexdigest()
    idempotency_key = hashlib.sha256(
        f"siconfi-dca:{year}:{offset}:{body_sha256}".encode()
    ).hexdigest()
    return SiconfiDcaPage(
        schema_name="siconfi-dca-page",
        schema_version="1.0.0",
        artifact_kind="http_response",
        source_code=SOURCE_CODE,
        endpoint_code=ENDPOINT_CODE,
        idempotency_key=idempotency_key,
        request_url=request_url,
        final_url=response.final_url,
        requested_at=requested_at,
        received_at=received_at,
        window_start=f"{year:04d}-01-01",
        window_end=f"{year:04d}-12-31",
        attempts=attempts,
        http_status=response.status,
        collection_status="success" if parsed.items else "empty",
        body_sha256=body_sha256,
        body_size_bytes=len(response.body),
        media_type=media_type,
        response_headers={
            key: value for key, value in headers.items() if key in SAFE_RESPONSE_HEADERS
        },
        cursor={
            "year": year,
            "offset": parsed.offset,
            "limit": parsed.limit,
            "count": parsed.count,
        },
        raw_body=response.body,
        items=parsed.items,
        total_pages=1,
        total_items=parsed.count,
        year=year,
        offset=parsed.offset,
        limit=parsed.limit,
        has_more=parsed.has_more,
    )


def _normalize_item(
    raw_item: object,
    *,
    expected_year: int,
    index: int,
) -> dict[str, object]:
    if not isinstance(raw_item, dict) or frozenset(raw_item) != EXPECTED_ITEM_KEYS:
        raise SiconfiContractError(
            f"A linha DCA {index} diverge do contrato oficial."
        )
    year = raw_item["exercicio"]
    ibge = raw_item["cod_ibge"]
    population = raw_item["populacao"]
    if not _is_int(year) or year != expected_year:
        raise SiconfiContractError(f"Exercício inválido na linha DCA {index}.")
    if not _is_int(ibge) or ibge != BARREIRAS_IBGE_CODE:
        raise SiconfiContractError(f"Código IBGE inválido na linha DCA {index}.")
    if not _is_int(population) or population < 0:
        raise SiconfiContractError(f"População inválida na linha DCA {index}.")

    text_fields = (
        "instituicao",
        "uf",
        "anexo",
        "rotulo",
        "coluna",
        "cod_conta",
        "conta",
    )
    texts: dict[str, str] = {}
    for field in text_fields:
        value = raw_item[field]
        if not isinstance(value, str) or not value.strip():
            raise SiconfiContractError(
                f"{field} vazio ou inválido na linha DCA {index}."
            )
        texts[field] = value.strip()
    if texts["uf"] != "BA":
        raise SiconfiContractError(f"UF inválida na linha DCA {index}.")

    value = raw_item["valor"]
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise SiconfiContractError(f"Valor inválido na linha DCA {index}.")
    decimal_value = Decimal(value)
    if not decimal_value.is_finite():
        raise SiconfiContractError(f"Valor inválido na linha DCA {index}.")
    return {
        "exercicio": year,
        "instituicao": texts["instituicao"],
        "cod_ibge": ibge,
        "uf": texts["uf"],
        "anexo": texts["anexo"],
        "rotulo": texts["rotulo"],
        "coluna": texts["coluna"],
        "cod_conta": texts["cod_conta"],
        "conta": texts["conta"],
        "valor": format(decimal_value, "f"),
        "populacao": population,
    }


def _item_identity(item: Mapping[str, object]) -> tuple[object, ...]:
    return tuple(
        item[field]
        for field in (
            "exercicio",
            "cod_ibge",
            "anexo",
            "rotulo",
            "coluna",
            "cod_conta",
            "conta",
        )
    )


def _validate_final_url(
    url: str,
    *,
    year: int,
    offset: int,
    page_size: int,
) -> None:
    try:
        validate_https_url(url, OFFICIAL_HOSTS)
    except ValueError as error:
        raise SiconfiContractError("A resposta DCA saiu do host oficial.") from error
    parsed = urlparse(url)
    query = parse_qs(parsed.query, strict_parsing=True)
    expected_query = {
        "an_exercicio": [str(year)],
        "id_ente": [str(BARREIRAS_IBGE_CODE)],
        "limit": [str(page_size)],
        "offset": [str(offset)],
    }
    if parsed.path not in OFFICIAL_PATHS or query != expected_query or parsed.fragment:
        raise SiconfiContractError("A URL final da DCA diverge da requisição.")


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _raise_non_finite(value: str) -> None:
    raise InvalidOperation(value)
