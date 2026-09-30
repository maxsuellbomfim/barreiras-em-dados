"""Aquisição estrita de demonstrativos do SICONFI (DCA e RGF-Anexo 02)."""

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
RGF_ENDPOINT_CODE = "rgf-anexo-02"
BARREIRAS_IBGE_CODE = 2903201
BASE_URL = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca"
RGF_BASE_URL = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rgf"
RGF_ANNEX = "RGF-Anexo 02"
OFFICIAL_HOSTS = frozenset({"apidatalake.tesouro.gov.br"})
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
RGF_EXTRA_ITEM_KEYS = frozenset({"periodo", "periodicidade", "co_poder", "esfera"})
MAX_PAGE_BYTES = 8 * 1024 * 1024
MAX_PAGES = 100
MAX_TOTAL_ITEMS = 100_000
TIMEOUT_SECONDS = 60.0


class SiconfiContractError(RuntimeError):
    """A resposta não permite afirmar cobertura do demonstrativo com segurança."""


@dataclass(frozen=True)
class SiconfiReport:
    """Contrato observado de um demonstrativo do SICONFI.

    A DCA é anual; o RGF-Anexo 02 (dívida consolidada) é quadrimestral, do
    Poder Executivo municipal, e traz quatro campos a mais em cada linha.
    """

    label: str
    endpoint_code: str
    base_url: str
    official_paths: frozenset[str]
    schema_name: str
    idempotency_prefix: str
    item_keys: frozenset[str]
    identity_fields: tuple[str, ...]
    periodic: bool

    def query(
        self, *, year: int, period: int | None, limit: int, offset: int
    ) -> dict[str, object]:
        if self.periodic:
            return {
                "an_exercicio": year,
                "in_periodicidade": "Q",
                "nr_periodo": period,
                "co_tipo_demonstrativo": "RGF",
                "no_anexo": RGF_ANNEX,
                "co_esfera": "M",
                "co_poder": "E",
                "id_ente": BARREIRAS_IBGE_CODE,
                "limit": limit,
                "offset": offset,
            }
        return {
            "an_exercicio": year,
            "id_ente": BARREIRAS_IBGE_CODE,
            "limit": limit,
            "offset": offset,
        }


_BASE_IDENTITY = (
    "exercicio",
    "cod_ibge",
    "anexo",
    "rotulo",
    "coluna",
    "cod_conta",
    "conta",
)
DCA_REPORT = SiconfiReport(
    label="DCA",
    endpoint_code=ENDPOINT_CODE,
    base_url=BASE_URL,
    official_paths=frozenset({"/ords/siconfi/tt/dca", "/ords/cdwhprd/siconfi/tt/dca"}),
    schema_name="siconfi-dca-page",
    idempotency_prefix="siconfi-dca",
    item_keys=EXPECTED_ITEM_KEYS,
    identity_fields=_BASE_IDENTITY,
    periodic=False,
)
RGF_ANNEX2_REPORT = SiconfiReport(
    label="RGF",
    endpoint_code=RGF_ENDPOINT_CODE,
    base_url=RGF_BASE_URL,
    official_paths=frozenset({"/ords/siconfi/tt/rgf", "/ords/cdwhprd/siconfi/tt/rgf"}),
    schema_name="siconfi-rgf-annex2-page",
    idempotency_prefix="siconfi-rgf-anexo-02",
    item_keys=EXPECTED_ITEM_KEYS | RGF_EXTRA_ITEM_KEYS,
    identity_fields=(*_BASE_IDENTITY, "periodicidade", "periodo", "co_poder"),
    periodic=True,
)


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
    # Quadrimestre do RGF; nulo na DCA, que é anual.
    period: int | None = None


# O mesmo instantâneo serve aos dois demonstrativos.
SiconfiPage = SiconfiDcaPage


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
    return _fetch_report(
        DCA_REPORT,
        year=year,
        period=None,
        page_size=page_size,
        transport=transport,
        rate_limiter=rate_limiter,
        retry_policy=retry_policy,
        circuit_breaker=circuit_breaker,
        random_value=random_value,
        now=now,
        sleep=sleep,
        logger=logger,
    )


def fetch_siconfi_rgf_annex2(
    *,
    year: int,
    period: int,
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
    """RGF-Anexo 02 (dívida consolidada) de um quadrimestre, como publicado."""
    if not 2015 <= year <= 2100:
        raise ValueError("O exercício do RGF deve estar entre 2015 e 2100.")
    if period not in (1, 2, 3):
        raise ValueError("O quadrimestre do RGF deve ser 1, 2 ou 3.")
    return _fetch_report(
        RGF_ANNEX2_REPORT,
        year=year,
        period=period,
        page_size=page_size,
        transport=transport,
        rate_limiter=rate_limiter,
        retry_policy=retry_policy,
        circuit_breaker=circuit_breaker,
        random_value=random_value,
        now=now,
        sleep=sleep,
        logger=logger,
    )


def _fetch_report(
    report: SiconfiReport,
    *,
    year: int,
    period: int | None,
    page_size: int,
    transport: HttpTransport | None,
    rate_limiter: PacedRateLimiter | None,
    retry_policy: RetryPolicy | None,
    circuit_breaker: CircuitBreaker | None,
    random_value: Callable[[], float],
    now: Callable[[], datetime],
    sleep: Callable[[float], None],
    logger: logging.Logger | None,
) -> tuple[SiconfiDcaPage, ...]:
    if not 1 <= page_size <= 5000:
        raise ValueError("page_size deve estar entre 1 e 5000.")

    active_transport = transport or UrllibTransport(OFFICIAL_HOSTS)
    limiter = rate_limiter or PacedRateLimiter(60)
    policy = retry_policy or RetryPolicy(max_attempts=4)
    breaker = circuit_breaker or CircuitBreaker(failure_threshold=policy.max_attempts)
    log = logger or logging.getLogger(__name__)
    pages: list[SiconfiDcaPage] = []
    identities: set[tuple[object, ...]] = set()
    offset = 0
    total_items = 0

    while True:
        if len(pages) >= MAX_PAGES:
            raise SiconfiContractError("A paginação excedeu o limite contratado.")
        page = _fetch_page(
            report,
            year=year,
            period=period,
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
            identity = _item_identity(item, report)
            if identity in identities:
                raise SiconfiContractError(
                    f"A fonte repetiu uma identidade {report.label} entre páginas."
                )
            identities.add(identity)
        pages.append(page)
        total_items += len(page.items)
        if total_items > MAX_TOTAL_ITEMS:
            raise SiconfiContractError(
                f"A {report.label} excedeu o volume máximo contratado."
            )
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
    return parse_siconfi_page(
        body,
        report=DCA_REPORT,
        expected_year=expected_year,
        expected_period=None,
        expected_offset=expected_offset,
        expected_limit=expected_limit,
    )


def parse_siconfi_rgf_page(
    body: bytes,
    *,
    expected_year: int,
    expected_period: int,
    expected_offset: int,
    expected_limit: int,
) -> ParsedSiconfiDcaPage:
    return parse_siconfi_page(
        body,
        report=RGF_ANNEX2_REPORT,
        expected_year=expected_year,
        expected_period=expected_period,
        expected_offset=expected_offset,
        expected_limit=expected_limit,
    )


def parse_siconfi_page(
    body: bytes,
    *,
    report: SiconfiReport,
    expected_year: int,
    expected_period: int | None,
    expected_offset: int,
    expected_limit: int,
) -> ParsedSiconfiDcaPage:
    label = report.label
    try:
        payload = json.loads(
            body.decode("utf-8"),
            parse_float=Decimal,
            parse_constant=lambda value: _raise_non_finite(value),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, InvalidOperation) as error:
        raise SiconfiContractError(f"A resposta {label} não é JSON válido.") from error
    if not isinstance(payload, dict) or frozenset(payload) != EXPECTED_PAGE_KEYS:
        raise SiconfiContractError(
            f"O envelope da {label} diverge do contrato oficial."
        )

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
        raise SiconfiContractError(f"A paginação da {label} é incoerente.")

    normalized: list[dict[str, object]] = []
    identities: set[tuple[object, ...]] = set()
    for index, raw_item in enumerate(items):
        item = _normalize_item(
            raw_item,
            report=report,
            expected_year=expected_year,
            expected_period=expected_period,
            index=index,
        )
        identity = _item_identity(item, report)
        if identity in identities:
            raise SiconfiContractError(
                f"A fonte publicou uma identidade {label} duplicada na página."
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
    report: SiconfiReport,
    *,
    year: int,
    period: int | None,
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
    label = report.label
    query = urlencode(
        report.query(year=year, period=period, limit=page_size, offset=offset)
    )
    request_url = f"{report.base_url}?{query}"
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
                f"A página {label} excedeu o limite de segurança."
            ) from error
        except RETRYABLE_TRANSPORT_EXCEPTIONS as error:
            circuit_breaker.record_failure()
            if attempt < retry_policy.max_attempts:
                sleep(retry_policy.delay(attempt, random_value()))
                continue
            raise SiconfiContractError(f"A API {label} ficou indisponível.") from error

        received_at = now().isoformat()
        log_event(
            logger,
            logging.INFO,
            "collector_http_response",
            source=SOURCE_CODE,
            endpoint=report.endpoint_code,
            status=response.status,
            attempt=attempt,
            body_size_bytes=len(response.body),
            year=year,
            period=period,
            offset=offset,
        )
        if response.status == 200:
            page = _snapshot_from_response(
                response,
                report=report,
                request_url=request_url,
                requested_at=requested_at,
                received_at=received_at,
                attempts=attempt,
                year=year,
                period=period,
                offset=offset,
                page_size=page_size,
            )
            circuit_breaker.record_success()
            return page
        if response.status not in RETRYABLE_HTTP_STATUSES:
            raise SiconfiContractError(
                f"A API {label} respondeu HTTP {response.status}."
            )
        circuit_breaker.record_failure()
        if attempt < retry_policy.max_attempts:
            sleep(retry_policy.delay(attempt, random_value()))
    raise SiconfiContractError(f"A API {label} ficou indisponível.")


def _snapshot_from_response(
    response: HttpResponse,
    *,
    report: SiconfiReport,
    request_url: str,
    requested_at: str,
    received_at: str,
    attempts: int,
    year: int,
    period: int | None,
    offset: int,
    page_size: int,
) -> SiconfiDcaPage:
    label = report.label
    _validate_final_url(
        response.final_url,
        report=report,
        year=year,
        period=period,
        offset=offset,
        page_size=page_size,
    )
    headers = {str(key).lower(): str(value) for key, value in response.headers.items()}
    media_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        raise SiconfiContractError(f"A API {label} não respondeu application/json.")
    content_length = headers.get("content-length")
    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError as error:
            raise SiconfiContractError(
                f"Content-Length inválido na {label}."
            ) from error
        if declared_size != len(response.body):
            raise SiconfiContractError(f"Content-Length diverge dos bytes da {label}.")
    parsed = parse_siconfi_page(
        response.body,
        report=report,
        expected_year=year,
        expected_period=period,
        expected_offset=offset,
        expected_limit=page_size,
    )
    body_sha256 = hashlib.sha256(response.body).hexdigest()
    # A chave da DCA não muda: artefatos já preservados continuam idempotentes.
    partition = f"{year}" if period is None else f"{year}:{period}"
    idempotency_key = hashlib.sha256(
        f"{report.idempotency_prefix}:{partition}:{offset}:{body_sha256}".encode()
    ).hexdigest()
    if period is None:
        window_start, window_end = f"{year:04d}-01-01", f"{year:04d}-12-31"
    else:
        # Quadrimestre cumulativo: o RGF acumula do início do ano ao fim do período.
        window_start = f"{year:04d}-01-01"
        window_end = f"{year:04d}-{('04-30', '08-31', '12-31')[period - 1]}"
    cursor: dict[str, int] = {
        "year": year,
        "offset": parsed.offset,
        "limit": parsed.limit,
        "count": parsed.count,
    }
    if period is not None:
        cursor["period"] = period
    return SiconfiDcaPage(
        schema_name=report.schema_name,
        schema_version="1.0.0",
        artifact_kind="http_response",
        source_code=SOURCE_CODE,
        endpoint_code=report.endpoint_code,
        idempotency_key=idempotency_key,
        request_url=request_url,
        final_url=response.final_url,
        requested_at=requested_at,
        received_at=received_at,
        window_start=window_start,
        window_end=window_end,
        attempts=attempts,
        http_status=response.status,
        collection_status="success" if parsed.items else "empty",
        body_sha256=body_sha256,
        body_size_bytes=len(response.body),
        media_type=media_type,
        response_headers={
            key: value for key, value in headers.items() if key in SAFE_RESPONSE_HEADERS
        },
        cursor=cursor,
        raw_body=response.body,
        items=parsed.items,
        total_pages=1,
        total_items=parsed.count,
        year=year,
        offset=parsed.offset,
        limit=parsed.limit,
        has_more=parsed.has_more,
        period=period,
    )


def _normalize_item(
    raw_item: object,
    *,
    report: SiconfiReport,
    expected_year: int,
    expected_period: int | None,
    index: int,
) -> dict[str, object]:
    label = report.label
    if not isinstance(raw_item, dict) or frozenset(raw_item) != report.item_keys:
        raise SiconfiContractError(
            f"A linha {label} {index} diverge do contrato oficial."
        )
    year = raw_item["exercicio"]
    ibge = raw_item["cod_ibge"]
    population = raw_item["populacao"]
    if not _is_int(year) or year != expected_year:
        raise SiconfiContractError(f"Exercício inválido na linha {label} {index}.")
    if not _is_int(ibge) or ibge != BARREIRAS_IBGE_CODE:
        raise SiconfiContractError(f"Código IBGE inválido na linha {label} {index}.")
    if not _is_int(population) or population < 0:
        raise SiconfiContractError(f"População inválida na linha {label} {index}.")

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
                f"{field} vazio ou inválido na linha {label} {index}."
            )
        texts[field] = value.strip()
    if texts["uf"] != "BA":
        raise SiconfiContractError(f"UF inválida na linha {label} {index}.")

    value = raw_item["valor"]
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise SiconfiContractError(f"Valor inválido na linha {label} {index}.")
    decimal_value = Decimal(value)
    if not decimal_value.is_finite():
        raise SiconfiContractError(f"Valor inválido na linha {label} {index}.")
    item: dict[str, object] = {
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
    if report.periodic:
        period = raw_item["periodo"]
        if not _is_int(period) or period != expected_period:
            raise SiconfiContractError(f"Período inválido na linha {label} {index}.")
        if (
            raw_item["periodicidade"] != "Q"
            or raw_item["co_poder"] != "E"
            or raw_item["esfera"] != "M"
            or texts["anexo"] != RGF_ANNEX
        ):
            raise SiconfiContractError(
                f"Demonstrativo fora do Anexo 02 do Executivo na linha {label} {index}."
            )
        item.update(
            {
                "periodo": period,
                "periodicidade": "Q",
                "co_poder": "E",
                "esfera": "M",
            }
        )
    return item


def _item_identity(
    item: Mapping[str, object], report: SiconfiReport = DCA_REPORT
) -> tuple[object, ...]:
    return tuple(item[field] for field in report.identity_fields)


def _validate_final_url(
    url: str,
    *,
    report: SiconfiReport,
    year: int,
    period: int | None,
    offset: int,
    page_size: int,
) -> None:
    label = report.label
    try:
        validate_https_url(url, OFFICIAL_HOSTS)
    except ValueError as error:
        raise SiconfiContractError(
            f"A resposta {label} saiu do host oficial."
        ) from error
    parsed = urlparse(url)
    query = parse_qs(parsed.query, strict_parsing=True)
    expected_query = {
        key: [str(value)]
        for key, value in report.query(
            year=year, period=period, limit=page_size, offset=offset
        ).items()
    }
    if (
        parsed.path not in report.official_paths
        or query != expected_query
        or parsed.fragment
    ):
        raise SiconfiContractError(f"A URL final da {label} diverge da requisição.")


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _raise_non_finite(value: str) -> None:
    raise InvalidOperation(value)
