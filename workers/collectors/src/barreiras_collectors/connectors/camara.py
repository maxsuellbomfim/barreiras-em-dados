"""Coleta de representantes federais na API aberta da Câmara (ADR 0014).

Preserva a lista de deputados da Bahia e o detalhe de cada um como bruto
verificável. A API é pública e sem chave; o CPF que ela devolve é
preservado no bruto (fidelidade à fonte) e nunca sai na projeção pública.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime

from ..http import (
    RETRYABLE_TRANSPORT_EXCEPTIONS,
    HttpTransport,
    UrllibTransport,
)
from ..logging import log_event
from ..resilience import RetryPolicy
from .pncp import PncpPage

SOURCE_CODE = "camara-federal"
DEPUTIES_ENDPOINT_CODE = "deputados-api"
ALLOWED_HOSTS = frozenset({"dadosabertos.camara.leg.br"})
RETRYABLE = frozenset({408, 425, 429, 500, 502, 503, 504})
STATE_CODE = "BA"
PAGE_SIZE = 100
TIMEOUT_SECONDS = 45.0
BASE_URL = "https://dadosabertos.camara.leg.br/api/v2/deputados"


class CamaraError(RuntimeError):
    """Falha explícita ao consultar a Câmara dos Deputados."""


def deputies_page_url(pagina: int) -> str:
    return (
        f"{BASE_URL}?siglaUf={STATE_CODE}"
        f"&pagina={pagina}&itens={PAGE_SIZE}"
        "&ordem=ASC&ordenarPor=nome"
    )


def deputy_detail_url(deputy_id: int) -> str:
    return f"{BASE_URL}/{deputy_id}"


def fetch_json(
    url: str,
    *,
    schema_name: str,
    cursor: dict[str, int],
    transport: HttpTransport | None = None,
    retry_policy: RetryPolicy | None = None,
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> PncpPage | None:
    """Uma resposta da Câmara como página persistível; None se vazia."""
    active_transport = transport or UrllibTransport(ALLOWED_HOSTS)
    policy = retry_policy or RetryPolicy(max_attempts=4)
    log = logger or logging.getLogger(__name__)

    for attempt in range(1, policy.max_attempts + 1):
        requested_at = datetime.now(UTC).isoformat()
        try:
            response = active_transport.get(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "BarreirasEmDados-Collector/0.1",
                },
                timeout_seconds=TIMEOUT_SECONDS,
                max_body_bytes=8 * 1024 * 1024,
            )
        except RETRYABLE_TRANSPORT_EXCEPTIONS as error:
            log_event(
                log,
                logging.WARNING,
                "collector_transport_failure",
                source=SOURCE_CODE,
                endpoint=DEPUTIES_ENDPOINT_CODE,
                attempt=attempt,
                error_type=type(error).__name__,
            )
            if attempt < policy.max_attempts:
                sleep(policy.delay(attempt, 0.5))
                continue
            raise CamaraError(
                f"A Câmara ficou indisponível para {schema_name}."
            ) from error
        received_at = datetime.now(UTC).isoformat()
        log_event(
            log,
            logging.INFO,
            "collector_http_response",
            source=SOURCE_CODE,
            endpoint=DEPUTIES_ENDPOINT_CODE,
            status=response.status,
            attempt=attempt,
            body_size_bytes=len(response.body),
        )
        if response.status == 404:
            return None
        if response.status == 200:
            try:
                payload = json.loads(response.body)
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                raise CamaraError(
                    f"A Câmara não devolveu JSON válido em {schema_name}."
                ) from error
            if not isinstance(payload, dict):
                raise CamaraError(f"A raiz de {schema_name} deve ser objeto.")
            data = payload.get("dados")
            if data is None:
                raise CamaraError(
                    f"A resposta de {schema_name} não traz o campo dados."
                )
            items = data if isinstance(data, list) else [data]
            if not items:
                return None
            return PncpPage(
                schema_name=schema_name,
                schema_version="1.0.0",
                source_code=SOURCE_CODE,
                endpoint_code=DEPUTIES_ENDPOINT_CODE,
                idempotency_key=hashlib.sha256(
                    json.dumps(
                        {
                            "url": url,
                            "body_sha256": hashlib.sha256(response.body).hexdigest(),
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
                request_url=url,
                final_url=response.final_url,
                requested_at=requested_at,
                received_at=received_at,
                attempts=attempt,
                http_status=response.status,
                collection_status="success",
                body_sha256=hashlib.sha256(response.body).hexdigest(),
                body_size_bytes=len(response.body),
                media_type="application/json",
                response_headers={},
                cursor=cursor,
                raw_body=response.body,
                window_start=None,
                window_end=None,
                items=tuple(item for item in items if isinstance(item, dict)),
                total_paginas=1,
                total_registros=len(items),
            )
        if response.status not in RETRYABLE:
            raise CamaraError(
                f"A Câmara respondeu HTTP {response.status} em {schema_name}."
            )
        if attempt < policy.max_attempts:
            sleep(policy.delay(attempt, 0.5))

    raise CamaraError(f"A Câmara ficou indisponível para {schema_name}.")


def fetch_deputies_page(
    pagina: int,
    **kwargs,
) -> PncpPage | None:
    return fetch_json(
        deputies_page_url(pagina),
        schema_name="camara-deputados-page",
        cursor={
            "offset": (pagina - 1) * PAGE_SIZE,
            "size": PAGE_SIZE,
            "pagina": pagina,
        },
        **kwargs,
    )


def fetch_deputy_detail(
    deputy_id: int,
    **kwargs,
) -> PncpPage | None:
    return fetch_json(
        deputy_detail_url(deputy_id),
        schema_name="camara-deputado-detalhe",
        cursor={"offset": 0, "size": 1, "deputado": deputy_id},
        **kwargs,
    )
