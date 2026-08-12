"""Cliente restrito da API pública de Gestão de Parcerias do Transferegov.

Esta camada preserva os fatos da fonte sem somar ou converter estágios
financeiros. Proposta, distribuição de recurso e parceria continuam recursos
distintos até a normalização determinística.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode

from ..http import (
    RETRYABLE_TRANSPORT_EXCEPTIONS,
    HttpTransport,
    UrllibTransport,
)
from ..logging import log_event
from ..resilience import CircuitBreaker, RetryPolicy

SOURCE_CODE = "transferegov-parcerias"
BASE_URL = "https://api-publica.transferegov.gestao.gov.br/parcerias"
ALLOWED_HOSTS = frozenset({"api-publica.transferegov.gestao.gov.br"})
BARREIRAS_IBGE_CODE = 2903201
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500
TIMEOUT_SECONDS = 60.0
MAX_BODY_BYTES = 16 * 1024 * 1024
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


class TransferegovError(RuntimeError):
    """Falha explícita de contrato, territorialidade ou disponibilidade."""


@dataclass(frozen=True)
class TransferegovPage:
    schema_name: str
    schema_version: str
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
    items: tuple[dict, ...]
    total_pages: int
    total_items: int


def fetch_proposals_page(
    *,
    page: int,
    page_size: int = DEFAULT_PAGE_SIZE,
    transport: HttpTransport | None = None,
    retry_policy: RetryPolicy | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    random_value: Callable[[], float] = random.random,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> TransferegovPage:
    """Preserva uma página de propostas cujo município recebedor é Barreiras."""
    return _fetch_page(
        resource="proposta",
        endpoint_code="propostas-barreiras",
        schema_name="transferegov-parcerias-propostas-page",
        params={
            "cd_ibge_recebedor": BARREIRAS_IBGE_CODE,
            "pagina": _positive_int(page, "page"),
            "tamanho_da_pagina": _page_size(page_size),
        },
        expected_field="cd_ibge_recebedor",
        expected_value=BARREIRAS_IBGE_CODE,
        expected_description="fora de Barreiras",
        transport=transport,
        retry_policy=retry_policy,
        circuit_breaker=circuit_breaker,
        random_value=random_value,
        now=now,
        sleep=sleep,
        logger=logger,
    )


def fetch_resource_distributions_page(
    *,
    proposal_id: int,
    validated_proposal_ids: frozenset[int],
    page: int,
    page_size: int = DEFAULT_PAGE_SIZE,
    transport: HttpTransport | None = None,
    retry_policy: RetryPolicy | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    random_value: Callable[[], float] = random.random,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> TransferegovPage:
    """Preserva autoria/tipo/valor indicado sem tratá-lo como pagamento."""
    proposal = _validated_proposal_id(proposal_id, validated_proposal_ids)
    return _fetch_page(
        resource="distribuicao-recurso-proposta",
        endpoint_code="distribuicoes-proposta",
        schema_name="transferegov-parcerias-distribuicoes-page",
        params={
            "id_proposta": proposal,
            "pagina": _positive_int(page, "page"),
            "tamanho_da_pagina": _page_size(page_size),
        },
        expected_field="id_proposta",
        expected_value=proposal,
        expected_description=f"proposta {proposal}",
        transport=transport,
        retry_policy=retry_policy,
        circuit_breaker=circuit_breaker,
        random_value=random_value,
        now=now,
        sleep=sleep,
        logger=logger,
    )


def fetch_partnerships_page(
    *,
    proposal_id: int,
    validated_proposal_ids: frozenset[int],
    page: int,
    page_size: int = DEFAULT_PAGE_SIZE,
    transport: HttpTransport | None = None,
    retry_policy: RetryPolicy | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    random_value: Callable[[], float] = random.random,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> TransferegovPage:
    """Preserva as parcerias derivadas de uma proposta, ainda sem pagamentos."""
    proposal = _validated_proposal_id(proposal_id, validated_proposal_ids)
    return _fetch_page(
        resource="parceria",
        endpoint_code="parcerias-proposta",
        schema_name="transferegov-parcerias-parcerias-page",
        params={
            "id_proposta": proposal,
            "pagina": _positive_int(page, "page"),
            "tamanho_da_pagina": _page_size(page_size),
        },
        expected_field="id_proposta",
        expected_value=proposal,
        expected_description=f"proposta {proposal}",
        transport=transport,
        retry_policy=retry_policy,
        circuit_breaker=circuit_breaker,
        random_value=random_value,
        now=now,
        sleep=sleep,
        logger=logger,
    )


def _fetch_page(
    *,
    resource: str,
    endpoint_code: str,
    schema_name: str,
    params: Mapping[str, int],
    expected_field: str,
    expected_value: int,
    expected_description: str,
    transport: HttpTransport | None,
    retry_policy: RetryPolicy | None,
    circuit_breaker: CircuitBreaker | None,
    random_value: Callable[[], float],
    now: Callable[[], datetime],
    sleep: Callable[[float], None],
    logger: logging.Logger | None,
) -> TransferegovPage:
    url = f"{BASE_URL}/{resource}?{urlencode(params)}"
    active_transport = transport or UrllibTransport(ALLOWED_HOSTS)
    policy = retry_policy or RetryPolicy(max_attempts=4)
    breaker = circuit_breaker or CircuitBreaker(
        failure_threshold=policy.max_attempts
    )
    log = logger or logging.getLogger(__name__)

    for attempt in range(1, policy.max_attempts + 1):
        breaker.before_request()
        requested_at = now().isoformat()
        try:
            response = active_transport.get(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Barreiras360-Collector/0.1",
                },
                timeout_seconds=TIMEOUT_SECONDS,
                max_body_bytes=MAX_BODY_BYTES,
            )
        except RETRYABLE_TRANSPORT_EXCEPTIONS as error:
            breaker.record_failure()
            log_event(
                log,
                logging.WARNING,
                "collector_transport_failure",
                source=SOURCE_CODE,
                endpoint=endpoint_code,
                attempt=attempt,
                error_type=type(error).__name__,
            )
            if attempt < policy.max_attempts:
                sleep(policy.delay(attempt, random_value()))
                continue
            raise TransferegovError(
                f"O Transferegov ficou indisponível em {endpoint_code}."
            ) from error

        received_at = now().isoformat()
        log_event(
            log,
            logging.INFO,
            "collector_http_response",
            source=SOURCE_CODE,
            endpoint=endpoint_code,
            status=response.status,
            attempt=attempt,
            body_size_bytes=len(response.body),
        )
        if response.status == 200:
            try:
                parsed = _parse_page(
                    response=response,
                    url=url,
                    requested_at=requested_at,
                    received_at=received_at,
                    attempts=attempt,
                    endpoint_code=endpoint_code,
                    schema_name=schema_name,
                    expected_page=params["pagina"],
                    expected_page_size=params["tamanho_da_pagina"],
                    expected_field=expected_field,
                    expected_value=expected_value,
                    expected_description=expected_description,
                )
            except TransferegovError:
                breaker.record_failure()
                raise
            breaker.record_success()
            return parsed
        if response.status not in RETRYABLE_HTTP_STATUSES:
            raise TransferegovError(
                f"O Transferegov respondeu HTTP {response.status} em {endpoint_code}."
            )
        breaker.record_failure()
        if attempt < policy.max_attempts:
            retry_after = _retry_after_seconds(response.headers, now=now)
            sleep(
                max(
                    policy.delay(attempt, random_value()),
                    retry_after or 0.0,
                )
            )

    raise TransferegovError(
        f"O Transferegov ficou indisponível em {endpoint_code}."
    )


def _parse_page(
    *,
    response,
    url: str,
    requested_at: str,
    received_at: str,
    attempts: int,
    endpoint_code: str,
    schema_name: str,
    expected_page: int,
    expected_page_size: int,
    expected_field: str,
    expected_value: int,
    expected_description: str,
) -> TransferegovPage:
    try:
        payload = json.loads(response.body)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise TransferegovError(
            f"O endpoint {endpoint_code} não devolveu JSON válido."
        ) from error
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise TransferegovError(
            f"O envelope de {endpoint_code} não segue o contrato oficial."
        )

    items: list[dict] = []
    for index, item in enumerate(payload["data"]):
        if not isinstance(item, dict):
            raise TransferegovError(
                f"O item {index} de {endpoint_code} não é um objeto JSON."
            )
        if item.get(expected_field) != expected_value:
            raise TransferegovError(
                f"O item {index} de {endpoint_code} não referencia "
                f"{expected_description}."
            )
        items.append(item)

    page_number = _envelope_int(payload, "page_number", minimum=1)
    page_size = _envelope_int(payload, "page_size", minimum=0)
    total_pages = _envelope_int(payload, "total_pages", minimum=0)
    total_items = _envelope_int(payload, "total_items", minimum=0)
    if page_number != expected_page:
        raise TransferegovError(
            f"A paginação de {endpoint_code} declarou página {page_number}, "
            f"mas a página solicitada foi {expected_page}."
        )
    if total_pages == 0 and (total_items != 0 or items):
        raise TransferegovError(
            f"A paginação de {endpoint_code} declarou zero páginas com dados."
        )
    if total_pages > 0 and page_number > total_pages:
        raise TransferegovError(
            f"A paginação de {endpoint_code} excedeu o total de páginas."
        )
    if len(items) > page_size or len(items) > total_items:
        raise TransferegovError(
            f"A paginação de {endpoint_code} possui contagens incompatíveis."
        )
    if not items and total_items > 0 and page_number <= total_pages:
        raise TransferegovError(
            f"A paginação de {endpoint_code} omitiu itens declarados."
        )
    body_sha256 = hashlib.sha256(response.body).hexdigest()
    idempotency_key = hashlib.sha256(
        json.dumps(
            {"url": url, "body_sha256": body_sha256},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return TransferegovPage(
        schema_name=schema_name,
        schema_version="1.0.0",
        source_code=SOURCE_CODE,
        endpoint_code=endpoint_code,
        idempotency_key=idempotency_key,
        request_url=url,
        final_url=response.final_url,
        requested_at=requested_at,
        received_at=received_at,
        window_start=requested_at,
        window_end=received_at,
        attempts=attempts,
        http_status=response.status,
        collection_status="success" if items else "empty",
        body_sha256=body_sha256,
        body_size_bytes=len(response.body),
        media_type="application/json",
        response_headers=_safe_headers(response.headers),
        cursor={
            "page": page_number,
            "size": expected_page_size,
            "response_size": page_size,
            "offset": (page_number - 1) * expected_page_size,
        },
        raw_body=response.body,
        items=tuple(items),
        total_pages=total_pages,
        total_items=total_items,
    )


def _positive_int(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} deve ser inteiro positivo.")
    return value


def _validated_proposal_id(
    proposal_id: int,
    validated_proposal_ids: frozenset[int],
) -> int:
    proposal = _positive_int(proposal_id, "proposal_id")
    if proposal not in validated_proposal_ids:
        raise ValueError(
            f"proposal_id {proposal} não foi validada para Barreiras."
        )
    return proposal


def _page_size(value: int) -> int:
    size = _positive_int(value, "page_size")
    if size > MAX_PAGE_SIZE:
        raise ValueError(f"page_size não pode exceder {MAX_PAGE_SIZE}.")
    return size


def _envelope_int(payload: dict, field: str, *, minimum: int) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise TransferegovError(
            f"O envelope possui {field} inválido: {value!r}."
        )
    return value


def _safe_headers(headers: Mapping[str, str]) -> dict[str, str]:
    allowed = {"content-type", "etag", "last-modified", "retry-after"}
    return {
        str(key).lower(): str(value)
        for key, value in headers.items()
        if str(key).lower() in allowed
    }


def _retry_after_seconds(
    headers: Mapping[str, str],
    *,
    now: Callable[[], datetime],
) -> float | None:
    raw = next(
        (value for key, value in headers.items() if key.lower() == "retry-after"),
        None,
    )
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(raw)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=UTC)
            return max(0.0, (retry_at - now()).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None
