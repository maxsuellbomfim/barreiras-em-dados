"""Coleta dos vereadores de Barreiras no portal da Câmara (ADR 0014).

A Câmara Municipal não publica os vereadores em API — o portal de
transparência tem recursos JSON, mas nenhum de composição da casa
(`docs/reviews/STAGE_6_REPRESENTATION_SOURCES.md`). A leitura é do HTML
servido, que é estável e não depende de JavaScript.

O coletor se identifica e não tenta contornar proteção alguma: os dados
são públicos por lei e a legitimidade da plataforma depende de coletá-los
às claras.
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import re
import time
import unicodedata
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

SOURCE_CODE = "camara-municipal-barreiras"
ENDPOINT_CODE = "vereadores-html"
ALLOWED_HOSTS = frozenset({"cmbarreiras.ba.gov.br"})
RETRYABLE = frozenset({408, 425, 429, 500, 502, 503, 504})
COUNCILLORS_URL = "https://cmbarreiras.ba.gov.br/vereadores"
TIMEOUT_SECONDS = 30.0
PARSER_VERSION = "cm-barreiras-vereadores/1.0.0"

# Cada vereador é uma linha .row-vereadores com foto e um bloco de campos
# rotulados em <strong>.
_BLOCK = re.compile(
    r"<div[^>]*class=['\"][^'\"]*row-vereadores[^'\"]*['\"][^>]*>(.*?)"
    r"(?=<div[^>]*class=['\"][^'\"]*row-vereadores|</div>\s*</div>\s*</div>)",
    re.IGNORECASE | re.DOTALL,
)
_PHOTO = re.compile(
    r"<img[^>]+src=['\"]([^'\"]+/wp-content/uploads/[^'\"]+)['\"]",
    re.IGNORECASE,
)
_TAGS = re.compile(r"<[^>]+>")


class CamaraMunicipalError(RuntimeError):
    """Falha explícita ao consultar o portal da Câmara Municipal."""


def _field(block: str, label: str) -> str | None:
    """Valor de um campo rotulado, tolerante à marcação do portal.

    Metade das fichas usa <strong> e metade <b>, com o dois-pontos ora
    dentro ora fora do rótulo — ler só uma variante omitia seis
    vereadores em silêncio.
    """
    pattern = re.compile(
        rf"<(?:strong|b)>\s*{label}\s*:?\s*</(?:strong|b)>\s*:?\s*(.*?)</p>",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(block)
    if match is None:
        return None
    text = html.unescape(_TAGS.sub(" ", match.group(1)))
    text = unicodedata.normalize("NFC", text)
    cleaned = re.sub(r"\s+", " ", text).strip(" :;,")
    return cleaned or None


def parse_councillors(page_html: str) -> tuple[dict, ...]:
    """Vereadores encontrados no HTML, em ordem de publicação.

    Bloco de ficha sem nome legível é falha explícita: publicar parte da
    Câmara como se fosse o todo seria pior do que não publicar.
    """
    found: list[dict] = []
    blocks = 0
    for index, block_match in enumerate(_BLOCK.finditer(page_html)):
        block = block_match.group(1)
        if "col-md-2" not in block and "col-md-10" not in block:
            continue
        blocks += 1
        name = _field(block, "NOME")
        if not name:
            raise CamaraMunicipalError(
                f"Ficha de vereador {index} sem nome legível: a marcação "
                "do portal mudou e a lista sairia incompleta."
            )
        photo = _PHOTO.search(block)
        found.append(
            {
                "nome": name,
                "partido": _field(block, "FILIAÇÃO PARTIDÁRIA"),
                "mandatos": _field(block, "NÚMERO DE MANDATOS"),
                "bandeira": _field(block, "PRINCIPAL BANDEIRA"),
                "biografia": _field(block, "BIOGRAFIA"),
                "foto_url": photo.group(1) if photo else None,
                "ordem": index,
            }
        )
    return tuple(found)


def fetch_councillors(
    *,
    transport: HttpTransport | None = None,
    retry_policy: RetryPolicy | None = None,
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> PncpPage | None:
    """Página de vereadores como bruto persistível; None se vier vazia."""
    active_transport = transport or UrllibTransport(ALLOWED_HOSTS)
    policy = retry_policy or RetryPolicy(max_attempts=4)
    log = logger or logging.getLogger(__name__)

    for attempt in range(1, policy.max_attempts + 1):
        requested_at = datetime.now(UTC).isoformat()
        try:
            response = active_transport.get(
                COUNCILLORS_URL,
                headers={
                    "Accept": "text/html",
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
                endpoint=ENDPOINT_CODE,
                attempt=attempt,
                error_type=type(error).__name__,
            )
            if attempt < policy.max_attempts:
                sleep(policy.delay(attempt, 0.5))
                continue
            raise CamaraMunicipalError(
                "O portal da Câmara Municipal ficou indisponível."
            ) from error
        received_at = datetime.now(UTC).isoformat()
        log_event(
            log,
            logging.INFO,
            "collector_http_response",
            source=SOURCE_CODE,
            endpoint=ENDPOINT_CODE,
            status=response.status,
            attempt=attempt,
            body_size_bytes=len(response.body),
        )
        if response.status == 200:
            try:
                page_html = response.body.decode("utf-8")
            except UnicodeDecodeError as error:
                raise CamaraMunicipalError(
                    "A página de vereadores não é UTF-8 válido."
                ) from error
            councillors = parse_councillors(page_html)
            if not councillors:
                # Layout mudou: estado explícito, nunca "zero vereadores".
                raise CamaraMunicipalError(
                    "Nenhum vereador reconhecido no HTML: o layout do "
                    "portal provavelmente mudou."
                )
            return PncpPage(
                schema_name="cm-barreiras-vereadores",
                schema_version="1.0.0",
                source_code=SOURCE_CODE,
                endpoint_code=ENDPOINT_CODE,
                idempotency_key=hashlib.sha256(
                    json.dumps(
                        {
                            "url": COUNCILLORS_URL,
                            "body_sha256": hashlib.sha256(response.body).hexdigest(),
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
                request_url=COUNCILLORS_URL,
                final_url=response.final_url,
                requested_at=requested_at,
                received_at=received_at,
                attempts=attempt,
                http_status=response.status,
                collection_status="success",
                body_sha256=hashlib.sha256(response.body).hexdigest(),
                body_size_bytes=len(response.body),
                media_type="text/html",
                response_headers={},
                cursor={"offset": 0, "size": len(councillors)},
                raw_body=response.body,
                window_start=None,
                window_end=None,
                items=councillors,
                total_paginas=1,
                total_registros=len(councillors),
            )
        if response.status not in RETRYABLE:
            raise CamaraMunicipalError(
                f"A Câmara Municipal respondeu HTTP {response.status}."
            )
        if attempt < policy.max_attempts:
            sleep(policy.delay(attempt, 0.5))

    raise CamaraMunicipalError("O portal da Câmara Municipal ficou indisponível.")
