"""Deputados estaduais da Bahia, do portal da Assembleia (ADR 0014).

A ALBA não publica dados abertos: a composição só existe em HTML
(`docs/reviews/STAGE_6_REPRESENTATION_SOURCES.md`). A listagem traz o
identificador oficial de cada parlamentar na Assembleia, que é o que
permite tratar cada pessoa como registro estável — nome nunca serve de
chave (ADR 0014).

O coletor se identifica e não contorna proteção alguma.
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
from urllib.parse import urljoin

from ..http import (
    RETRYABLE_TRANSPORT_EXCEPTIONS,
    HttpTransport,
    UrllibTransport,
)
from ..logging import log_event
from ..resilience import RetryPolicy
from .pncp import PncpPage

SOURCE_CODE = "alba"
ENDPOINT_CODE = "deputados-estaduais-html"
ALLOWED_HOSTS = frozenset({"www.al.ba.gov.br", "al.ba.gov.br"})
RETRYABLE = frozenset({408, 425, 429, 500, 502, 503, 504})
DEPUTIES_URL = "https://www.al.ba.gov.br/deputados/deputados-estaduais"
PROFILE_BASE = "https://www.al.ba.gov.br/deputados/deputado-estadual/"
TIMEOUT_SECONDS = 30.0
PARSER_VERSION = "alba-deputados/1.0.0"
PROFILE_ENDPOINT_CODE = "deputado-estadual-profile-html"
PROFILE_PARSER_VERSION = "alba-deputado-profile/1.1.0"
PROFILE_DELAY_SECONDS = 5.0
# A casa tem 63 cadeiras; um número muito menor indica página truncada.
MIN_EXPECTED = 40

_OPTION = re.compile(
    r"<option[^>]+value=['\"]/deputados/deputado-estadual/(\d+)['\"][^>]*>"
    r"\s*(?:<span[^>]*>)?\s*([^<]{2,120}?)\s*(?:</span>)?\s*</option>",
    re.IGNORECASE | re.DOTALL,
)

_OG_IMAGE = re.compile(
    r"<meta[^>]+property=['\"]og:image['\"][^>]+content=['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)
_IMAGE_SRC = re.compile(
    r"<img[^>]+src=['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)
_CV_FIELD = re.compile(
    r'<div[^>]+class=["\'][^"\']*linha-cv[^"\']*["\'][^>]*>'
    r"\s*<strong>\s*([^<]+?)\s*</strong>\s*<span[^>]*>(.*?)</span>",
    re.IGNORECASE | re.DOTALL,
)


class AlbaError(RuntimeError):
    """Falha explícita ao consultar o portal da Assembleia."""


def parse_deputies(page_html: str) -> tuple[dict, ...]:
    """Deputados da listagem, por identificador oficial da Assembleia."""
    seen: dict[str, dict] = {}
    for match in _OPTION.finditer(page_html):
        identifier = match.group(1)
        name = unicodedata.normalize("NFC", html.unescape(match.group(2)))
        name = re.sub(r"\s+", " ", name).strip()
        if not name or identifier in seen:
            continue
        seen[identifier] = {
            "id_alba": identifier,
            "nome": name,
            "perfil_url": f"{PROFILE_BASE}{identifier}",
        }
    return tuple(sorted(seen.values(), key=lambda item: item["nome"].casefold()))


def parse_profile(
    page_html: str,
    *,
    identifier: str,
    profile_url: str,
    display_name: str,
) -> dict:
    """Extrai apenas a foto oficial, sem inferir biografia ou vínculo municipal."""
    photo_url = None
    image_sources = [match.group(1) for match in _OG_IMAGE.finditer(page_html)] + [
        match.group(1) for match in _IMAGE_SRC.finditer(page_html)
    ]
    for image_source in image_sources:
        candidate = urljoin(profile_url, html.unescape(image_source).strip())
        if (
            candidate.startswith("https://www.al.ba.gov.br/")
            and "/fserver/" in candidate
        ):
            photo_url = candidate
            break
    fields: dict[str, str] = {}
    field_names = {
        "formação educacional": "formacao_educacional",
        "atividade profissional": "atividade_profissional",
        "mandato eletivo": "mandato_eletivo",
        "atividade parlamentar": "atividade_parlamentar",
    }
    for match in _CV_FIELD.finditer(page_html):
        label = re.sub(r"\s+", " ", html.unescape(match.group(1))).strip().casefold()
        field_name = field_names.get(label)
        if field_name is None:
            continue
        value = re.sub(r"<[^>]+>", " ", match.group(2))
        value = re.sub(r"\s+", " ", html.unescape(value)).strip()
        if value:
            fields[field_name] = value
    return {
        "id_alba": identifier,
        "nome": display_name,
        "perfil_url": profile_url,
        "foto_url": photo_url,
        **fields,
    }


def fetch_profile(
    deputy: dict,
    *,
    transport: HttpTransport | None = None,
    retry_policy: RetryPolicy | None = None,
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> PncpPage:
    """Preserva uma página individual da ALBA como artefato independente."""
    identifier = deputy.get("id_alba")
    profile_url = deputy.get("perfil_url")
    display_name = deputy.get("nome")
    if (
        not isinstance(identifier, str)
        or not identifier.isdigit()
        or not isinstance(profile_url, str)
        or not profile_url.startswith(PROFILE_BASE)
        or not isinstance(display_name, str)
    ):
        raise AlbaError("Registro estadual inválido para consulta de perfil.")

    active_transport = transport or UrllibTransport(ALLOWED_HOSTS)
    policy = retry_policy or RetryPolicy(max_attempts=4)
    log = logger or logging.getLogger(__name__)
    for attempt in range(1, policy.max_attempts + 1):
        requested_at = datetime.now(UTC).isoformat()
        try:
            response = active_transport.get(
                profile_url,
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
                endpoint=PROFILE_ENDPOINT_CODE,
                attempt=attempt,
                error_type=type(error).__name__,
            )
            if attempt < policy.max_attempts:
                sleep(policy.delay(attempt, 0.5))
                continue
            raise AlbaError(
                f"A ALBA ficou indisponível no perfil {identifier}."
            ) from error
        received_at = datetime.now(UTC).isoformat()
        log_event(
            log,
            logging.INFO,
            "collector_http_response",
            source=SOURCE_CODE,
            endpoint=PROFILE_ENDPOINT_CODE,
            identifier=identifier,
            status=response.status,
            attempt=attempt,
            body_size_bytes=len(response.body),
        )
        if response.status == 200:
            try:
                page_html = response.body.decode("utf-8")
            except UnicodeDecodeError:
                page_html = response.body.decode("latin-1")
            payload = parse_profile(
                page_html,
                identifier=identifier,
                profile_url=profile_url,
                display_name=display_name,
            )
            body_sha256 = hashlib.sha256(response.body).hexdigest()
            return PncpPage(
                schema_name="alba-deputado-estadual-profile",
                schema_version="1.0.0",
                source_code=SOURCE_CODE,
                endpoint_code=PROFILE_ENDPOINT_CODE,
                idempotency_key=hashlib.sha256(
                    json.dumps(
                        {"url": profile_url, "body_sha256": body_sha256},
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
                request_url=profile_url,
                final_url=response.final_url,
                requested_at=requested_at,
                received_at=received_at,
                attempts=attempt,
                http_status=response.status,
                collection_status="success",
                body_sha256=body_sha256,
                body_size_bytes=len(response.body),
                media_type="text/html",
                response_headers={},
                cursor={"offset": 0, "size": 1},
                raw_body=response.body,
                window_start=None,
                window_end=None,
                items=(payload,),
                total_paginas=1,
                total_registros=1,
            )
        if response.status not in RETRYABLE:
            raise AlbaError(f"A ALBA respondeu HTTP {response.status} no perfil.")
        if attempt < policy.max_attempts:
            sleep(policy.delay(attempt, 0.5))
    raise AlbaError(f"A ALBA ficou indisponível no perfil {identifier}.")


def fetch_deputies(
    *,
    transport: HttpTransport | None = None,
    retry_policy: RetryPolicy | None = None,
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> PncpPage | None:
    """Listagem de deputados estaduais pronta para persistir."""
    active_transport = transport or UrllibTransport(ALLOWED_HOSTS)
    policy = retry_policy or RetryPolicy(max_attempts=4)
    log = logger or logging.getLogger(__name__)

    for attempt in range(1, policy.max_attempts + 1):
        requested_at = datetime.now(UTC).isoformat()
        try:
            response = active_transport.get(
                DEPUTIES_URL,
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
            raise AlbaError("O portal da Assembleia ficou indisponível.") from error
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
            except UnicodeDecodeError:
                page_html = response.body.decode("latin-1")
            deputies = parse_deputies(page_html)
            if len(deputies) < MIN_EXPECTED:
                # Casa incompleta é falha: publicar parte da Assembleia
                # como se fosse o todo seria pior do que não publicar.
                raise AlbaError(
                    f"Apenas {len(deputies)} deputados reconhecidos "
                    f"(esperado ao menos {MIN_EXPECTED}): o layout do "
                    "portal provavelmente mudou."
                )
            return PncpPage(
                schema_name="alba-deputados-estaduais",
                schema_version="1.0.0",
                source_code=SOURCE_CODE,
                endpoint_code=ENDPOINT_CODE,
                idempotency_key=hashlib.sha256(
                    json.dumps(
                        {
                            "url": DEPUTIES_URL,
                            "body_sha256": hashlib.sha256(response.body).hexdigest(),
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
                request_url=DEPUTIES_URL,
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
                cursor={"offset": 0, "size": len(deputies)},
                raw_body=response.body,
                window_start=None,
                window_end=None,
                items=deputies,
                total_paginas=1,
                total_registros=len(deputies),
            )
        if response.status not in RETRYABLE:
            raise AlbaError(f"A Assembleia respondeu HTTP {response.status}.")
        if attempt < policy.max_attempts:
            sleep(policy.delay(attempt, 0.5))

    raise AlbaError("O portal da Assembleia ficou indisponível.")
