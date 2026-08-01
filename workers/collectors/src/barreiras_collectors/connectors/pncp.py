"""Coleta do cadastro do PNCP para Barreiras (Etapa 2, fatia 1).

Preserva como bruto as respostas JSON do órgão e das unidades — inclusive as
inconsistências da fonte (duplicatas, unidades de outro município), que são
evidência, não defeito a corrigir na coleta.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from ..http import HttpTransport, UrllibTransport
from ..logging import log_event
from ..resilience import RetryPolicy

SOURCE_CODE = "pncp"
ENDPOINT_CODE = "registry-api"
BARREIRAS_CNPJ = "13654405000195"
ALLOWED_HOSTS = frozenset({"pncp.gov.br"})
RETRYABLE = frozenset({408, 425, 429, 500, 502, 503, 504})

REGISTRY_RESOURCES: tuple[tuple[str, str], ...] = (
    (
        "orgao",
        f"https://pncp.gov.br/api/pncp/v1/orgaos/{BARREIRAS_CNPJ}",
    ),
    (
        "unidades",
        f"https://pncp.gov.br/api/pncp/v1/orgaos/{BARREIRAS_CNPJ}/unidades",
    ),
)


class PncpError(RuntimeError):
    """Falha explícita ao consultar o PNCP."""


CONTRATACOES_ENDPOINT_CODE = "consulta-contratacoes"
# Modalidades da Lei 14.133/2021 aceitas pela API de consulta.
CONTRATACAO_MODALIDADES: tuple[int, ...] = tuple(range(1, 14))
CONTRATACOES_PAGE_SIZE = 50


@dataclass(frozen=True)
class PncpPage:
    """Página de consulta com a mesma anatomia persistível do QD."""

    schema_name: str
    schema_version: str
    source_code: str
    endpoint_code: str
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
    response_headers: dict[str, str]
    cursor: dict[str, int]
    raw_body: bytes
    window_start: str | None
    window_end: str | None
    items: tuple[dict, ...]
    total_paginas: int
    total_registros: int


def fetch_contratacoes_page(
    *,
    since: str,
    until: str,
    modalidade: int,
    pagina: int,
    transport: HttpTransport | None = None,
    retry_policy: RetryPolicy | None = None,
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> PncpPage | None:
    """Uma página de contratações publicadas; None quando não há conteúdo."""
    url = (
        "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
        f"?dataInicial={since}&dataFinal={until}"
        f"&cnpj={BARREIRAS_CNPJ}"
        f"&codigoModalidadeContratacao={modalidade}"
        f"&pagina={pagina}&tamanhoPagina={CONTRATACOES_PAGE_SIZE}"
    )
    active_transport = transport or UrllibTransport(ALLOWED_HOSTS)
    policy = retry_policy or RetryPolicy(max_attempts=4)
    log = logger or logging.getLogger(__name__)

    for attempt in range(1, policy.max_attempts + 1):
        requested_at = datetime.now(UTC).isoformat()
        response = active_transport.get(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "BarreirasEmDados-Collector/0.1",
            },
            timeout_seconds=35.0,
            max_body_bytes=8 * 1024 * 1024,
        )
        received_at = datetime.now(UTC).isoformat()
        log_event(
            log,
            logging.INFO,
            "collector_http_response",
            source=SOURCE_CODE,
            endpoint=CONTRATACOES_ENDPOINT_CODE,
            status=response.status,
            attempt=attempt,
            body_size_bytes=len(response.body),
        )
        if response.status == 204:
            return None
        if response.status == 200:
            try:
                payload = json.loads(response.body)
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                raise PncpError(
                    "A consulta de contratações não devolveu JSON válido."
                ) from error
            if not isinstance(payload, dict):
                raise PncpError("A raiz da consulta deve ser objeto JSON.")
            # Gate da Etapa 2: HTTP 200 com raiz de erro é falha, não dado.
            if payload.get("error") or payload.get("status") in (400, 500):
                raise PncpError(
                    "O PNCP devolveu erro dentro de HTTP 200: "
                    f"{str(payload)[:200]}"
                )
            data = payload.get("data") or []
            if not isinstance(data, list):
                raise PncpError("O campo data deve ser uma lista.")
            total_registros = payload.get("totalRegistros") or 0
            total_paginas = payload.get("totalPaginas") or 0
            if not data:
                return None
            return PncpPage(
                schema_name="pncp-contratacoes-page",
                schema_version="1.0.0",
                source_code=SOURCE_CODE,
                endpoint_code=CONTRATACOES_ENDPOINT_CODE,
                idempotency_key=hashlib.sha256(
                    json.dumps(
                        {
                            "url": url,
                            "body_sha256": hashlib.sha256(
                                response.body
                            ).hexdigest(),
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
                cursor={
                    "offset": (pagina - 1) * CONTRATACOES_PAGE_SIZE,
                    "size": CONTRATACOES_PAGE_SIZE,
                    "modalidade": modalidade,
                    "pagina": pagina,
                },
                raw_body=response.body,
                window_start=since,
                window_end=until,
                items=tuple(
                    item for item in data if isinstance(item, dict)
                ),
                total_paginas=int(total_paginas),
                total_registros=int(total_registros),
            )
        if response.status not in RETRYABLE:
            raise PncpError(
                f"O PNCP respondeu HTTP {response.status} nas contratações."
            )
        if attempt < policy.max_attempts:
            sleep(policy.delay(attempt, 0.5))

    raise PncpError("O PNCP ficou indisponível para contratações.")


@dataclass(frozen=True)
class RegistrySnapshot:
    resource: str
    url: str
    final_url: str
    fetched_at: str
    http_status: int
    body: bytes
    body_sha256: str
    media_type: str


def fetch_registry_snapshot(
    resource: str,
    url: str,
    *,
    transport: HttpTransport | None = None,
    retry_policy: RetryPolicy | None = None,
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> RegistrySnapshot:
    """Busca um recurso do cadastro e valida que o corpo é JSON."""
    active_transport = transport or UrllibTransport(ALLOWED_HOSTS)
    policy = retry_policy or RetryPolicy(max_attempts=4)
    log = logger or logging.getLogger(__name__)

    last_status: int | None = None
    for attempt in range(1, policy.max_attempts + 1):
        response = active_transport.get(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "BarreirasEmDados-Collector/0.1",
            },
            timeout_seconds=35.0,
            max_body_bytes=8 * 1024 * 1024,
        )
        log_event(
            log,
            logging.INFO,
            "collector_http_response",
            source=SOURCE_CODE,
            endpoint=resource,
            status=response.status,
            attempt=attempt,
            body_size_bytes=len(response.body),
        )
        if response.status == 200:
            try:
                json.loads(response.body)
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                raise PncpError(
                    f"O recurso {resource} não devolveu JSON válido."
                ) from error
            return RegistrySnapshot(
                resource=resource,
                url=url,
                final_url=response.final_url,
                fetched_at=datetime.now(UTC).isoformat(),
                http_status=response.status,
                body=response.body,
                body_sha256=hashlib.sha256(response.body).hexdigest(),
                media_type="application/json",
            )
        last_status = response.status
        if response.status not in RETRYABLE:
            raise PncpError(
                f"O PNCP respondeu HTTP {response.status} em {resource}."
            )
        if attempt < policy.max_attempts:
            sleep(policy.delay(attempt, 0.5))

    raise PncpError(
        f"O PNCP ficou indisponível para {resource} "
        f"(último HTTP {last_status})."
    )
