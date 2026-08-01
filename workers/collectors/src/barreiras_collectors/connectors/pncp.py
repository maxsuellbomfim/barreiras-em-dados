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
