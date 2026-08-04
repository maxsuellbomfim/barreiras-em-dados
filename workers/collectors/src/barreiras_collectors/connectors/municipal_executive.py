"""Perfis do Executivo municipal publicados pela Prefeitura de Barreiras."""

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

from ..http import HttpTransport, UrllibTransport
from ..logging import log_event
from ..resilience import RetryPolicy
from .pncp import PncpPage

SOURCE_CODE = "prefeitura-barreiras"
ENDPOINT_CODE = "executive-pages-html"
ALLOWED_HOSTS = frozenset({"barreiras.ba.gov.br", "www.barreiras.ba.gov.br"})
RETRYABLE = frozenset({408, 425, 429, 500, 502, 503, 504})
TIMEOUT_SECONDS = 30.0
COLLECTOR_VERSION = "barreiras-executive-collector/1.0.0"
PARSER_VERSION = "barreiras-executive-pages/1.1.0"

PAGE_SPECS: tuple[tuple[str, str, str], ...] = (
    ("prefeito", "Prefeito", "https://barreiras.ba.gov.br/prefeito-e-vice/"),
    (
        "vice-prefeito",
        "Vice-prefeito",
        "https://barreiras.ba.gov.br/prefeito-e-vice/",
    ),
    (
        "secretario",
        "Secretaria Municipal de Administra\u00e7\u00e3o",
        "https://barreiras.ba.gov.br/secretaria-municipal-de-administracao",
    ),
    (
        "secretario",
        "Secretaria Municipal de Planejamento",
        "https://barreiras.ba.gov.br/secretaria-municipal-de-planejamento",
    ),
    (
        "secretario",
        "Secretaria Municipal de Sa\u00fade",
        "https://barreiras.ba.gov.br/secretaria-municipal-de-saude",
    ),
    (
        "secretario",
        "Secretaria Municipal da Fazenda",
        "https://barreiras.ba.gov.br/secretaria-municipal-da-fazenda",
    ),
    (
        "secretario",
        "Secretaria Municipal de Meio Ambiente e Sustentabilidade",
        "https://barreiras.ba.gov.br/secretaria-municipal-de-meio-ambiente-e-sustentabilidade",
    ),
    (
        "secretario",
        (
            "Secretaria Municipal de Infraestrutura, Obras, "
            "Servi\u00e7os P\u00fablicos e Transporte"
        ),
        "https://barreiras.ba.gov.br/secretaria-municipal-de-infraestrutura-obras-servicos-publicos-e-transporte",
    ),
    (
        "secretario",
        "Secretaria Municipal de Seguran\u00e7a Cidad\u00e3 e Tr\u00e2nsito",
        "https://barreiras.ba.gov.br/secretaria-municipal-de-seguranca-cidada-e-transito",
    ),
    (
        "secretario",
        "Secretaria Municipal de Educa\u00e7\u00e3o",
        "https://barreiras.ba.gov.br/secretaria-municipal-de-educacao",
    ),
    (
        "secretario",
        "Secretaria Municipal de Assist\u00eancia Social e Trabalho",
        "https://barreiras.ba.gov.br/secretaria-municipal-de-assistencia-social-e-trabalho",
    ),
    (
        "secretario",
        "Secretaria Municipal de Agricultura e Tecnologia",
        "https://barreiras.ba.gov.br/secretaria-municipal-de-agricultura-e-tecnologia",
    ),
    (
        "secretario",
        "Secretaria Municipal de Ind\u00fastria, Com\u00e9rcio e Servi\u00e7os",
        "https://barreiras.ba.gov.br/secretaria-municipal-de-industria-comercio-e-servicos",
    ),
    (
        "secretario",
        "Secretaria Municipal de Esporte, Juventude e Lazer",
        "https://barreiras.ba.gov.br/secretaria-municipal-de-esportes-juventude-e-lazer",
    ),
    (
        "secretario",
        "Secretaria Municipal de Cultura e Turismo",
        "https://barreiras.ba.gov.br/secretaria-municipal-de-cultura-e-turismo",
    ),
)

_TAG = re.compile(r"<[^>]+>", re.DOTALL)
_SPACE = re.compile(r"\s+")


class MunicipalExecutiveError(RuntimeError):
    """Falha expl\u00edcita ao consultar ou interpretar a Prefeitura."""


def _clean(value: str) -> str:
    value = html.unescape(value)
    value = _TAG.sub(" ", value)
    return _SPACE.sub(" ", value).strip()


def _name(value: str) -> str:
    return unicodedata.normalize("NFC", _clean(value))


def _image_url(fragment: str) -> str | None:
    match = re.search(
        r"<img[^>]+src=['\"](https://[^'\"]+)['\"]", fragment, re.I
    )
    return html.unescape(match.group(1)) if match else None


def _looks_like_name(value: str) -> bool:
    normalized = unicodedata.normalize("NFD", value)
    plain = re.sub(r"[^A-Za-zÀ-ÿ ]", " ", normalized)
    tokens = [token for token in _SPACE.sub(" ", plain).strip().split() if token]
    upper = value.upper()
    if len(tokens) < 2 or len(value) > 140:
        return False
    excluded = (
        "SECRETARIA",
        "SECRETÁRIO",
        "SUBSECRETÁRIO",
        "DIRETOR",
        "COORDENADOR",
        "CONTEÚDO",
        "RESPONSÁVEL",
    )
    if any(marker in upper for marker in excluded):
        return False
    return "@" not in value and re.search(r"\d{3,}", value) is None


def _first_name(content: str) -> str | None:
    paragraphs = re.findall(r"<p[^>]*>([\s\S]*?)</p>", content, re.I)
    for paragraph in paragraphs[:8]:
        marked = re.sub(r"<br\s*/?>", "\n", paragraph, flags=re.I)
        for line in marked.splitlines():
            candidate = _name(line)
            if " - " in candidate:
                candidate = candidate.split(" - ", 1)[0].strip()
            if _looks_like_name(candidate):
                return candidate
        for strong in re.findall(
            r"<strong[^>]*>([\s\S]*?)</strong>", paragraph, re.I
        ):
            candidate = _name(strong)
            if _looks_like_name(candidate):
                return candidate
    return None


def _profile(
    role: str,
    department: str | None,
    url: str,
    fragment: str,
    name: str,
    photo_url: str | None,
) -> dict:
    return {
        "profile_key": f"{role}:{url}:{name.casefold()}",
        "role": role,
        "department_name": department,
        "display_name": name,
        "profile_url": url,
        "photo_url": photo_url,
        "source_excerpt": _clean(fragment)[:1000],
    }


def parse_official_page(
    *, role: str, department: str, url: str, page_html: str
) -> tuple[dict, ...]:
    """Extrai perfis somente dos marcadores presentes no HTML oficial."""
    content_match = re.search(
        r'<div[^>]+class=["\']content["\'][^>]*>([\s\S]*?)(?:<div[^>]+class=["\']clear["\'])',
        page_html,
        re.I,
    )
    content = content_match.group(1) if content_match else page_html
    profiles: list[dict] = []

    if role in {"prefeito", "vice-prefeito"}:
        heading = re.search(
            rf"<h2[^>]*>\s*{re.escape(role)}\s*</h2>", content, re.I
        )
        if not heading:
            return ()
        # A página oficial reúne prefeito e vice no mesmo acordeão. O recorte
        # anterior começava antes do título atual e acabava incluindo a
        # biografia do outro cargo. Encerramos no próximo título de liderança
        # para que cada perfil carregue somente o texto correspondente.
        next_heading = re.search(
            r"<h2[^>]*>\s*(?:prefeito|vice-prefeito)\s*</h2>",
            content[heading.end() :],
            re.I,
        )
        end = (
            heading.end() + next_heading.start()
            if next_heading
            else len(content)
        )
        window = content[heading.start() : end]
        # No HTML oficial, a foto pode estar imediatamente antes do título
        # dentro do mesmo bloco visual. O texto continua limitado ao bloco do
        # cargo, mas a imagem deve ser procurada também nesse prefixo curto.
        photo_fragment = content[max(0, heading.start() - 2000) : heading.start()]
        title = re.search(
            r'<h2[^>]+class=["\'][^"\']*panel-title[^"\']*["\'][^>]*>'
            r'[\s\S]*?<strong>([^<]+)</strong>',
            window,
            re.I,
        )
        if title:
            profiles.append(
                _profile(
                    role,
                    None,
                    url,
                    window,
                    _name(title.group(1)),
                    _image_url(window) or _image_url(photo_fragment),
                )
            )
        return tuple(profiles)

    candidate = _first_name(content)
    if candidate:
        profiles.append(
            _profile(
                role,
                department,
                url,
                content[: min(len(content), 2200)],
                candidate,
                _image_url(content),
            )
        )
    return tuple(profiles)


def fetch_executive_profiles(
    *,
    transport: HttpTransport | None = None,
    retry_policy: RetryPolicy | None = None,
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> PncpPage:
    active_transport = transport or UrllibTransport(ALLOWED_HOSTS)
    policy = retry_policy or RetryPolicy(max_attempts=4)
    log = logger or logging.getLogger(__name__)
    pages: list[dict] = []
    profiles: dict[str, dict] = {}

    for role, department, url in PAGE_SPECS:
        for attempt in range(1, policy.max_attempts + 1):
            response = active_transport.get(
                url,
                headers={
                    "Accept": "text/html",
                    "User-Agent": "BarreirasEmDados-Collector/0.1",
                },
                timeout_seconds=TIMEOUT_SECONDS,
                max_body_bytes=8 * 1024 * 1024,
            )
            log_event(
                log,
                logging.INFO,
                "collector_http_response",
                source=SOURCE_CODE,
                endpoint=ENDPOINT_CODE,
                status=response.status,
                attempt=attempt,
                url=url,
                body_size_bytes=len(response.body),
            )
            if response.status == 200:
                try:
                    page_html = response.body.decode("utf-8")
                except UnicodeDecodeError:
                    page_html = response.body.decode("latin-1")
                parsed = parse_official_page(
                    role=role,
                    department=department,
                    url=url,
                    page_html=page_html,
                )
                pages.append(
                    {
                        "url": url,
                        "role": role,
                        "department": department,
                        "body_sha256": hashlib.sha256(response.body).hexdigest(),
                        "html": page_html,
                    }
                )
                for item in parsed:
                    profiles[item["profile_key"]] = item
                break
            if response.status not in RETRYABLE:
                raise MunicipalExecutiveError(
                    f"A Prefeitura respondeu HTTP {response.status} para {url}."
                )
            if attempt < policy.max_attempts:
                sleep(policy.delay(attempt, 0.5))
        else:
            raise MunicipalExecutiveError(
                f"A p\u00e1gina oficial ficou indispon\u00edvel: {url}"
            )

    if not profiles:
        raise MunicipalExecutiveError(
            "Nenhum perfil reconhecido nas p\u00e1ginas oficiais do Executivo."
        )
    raw_body = json.dumps(
        {"pages": pages},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    body_sha256 = hashlib.sha256(raw_body).hexdigest()
    now = datetime.now(UTC).isoformat()
    return PncpPage(
        schema_name="barreiras-executive-profiles",
        schema_version="1.0.0",
        source_code=SOURCE_CODE,
        endpoint_code=ENDPOINT_CODE,
        idempotency_key=hashlib.sha256(
            f"{ENDPOINT_CODE}:{body_sha256}".encode()
        ).hexdigest(),
        request_url="https://barreiras.ba.gov.br/prefeito-e-vice/",
        final_url="https://barreiras.ba.gov.br/prefeito-e-vice/",
        requested_at=now,
        received_at=now,
        attempts=1,
        http_status=200,
        collection_status="success",
        body_sha256=body_sha256,
        body_size_bytes=len(raw_body),
        media_type="application/json",
        response_headers={},
        cursor={"offset": 0, "size": len(profiles)},
        raw_body=raw_body,
        window_start=None,
        window_end=None,
        items=tuple(
            sorted(
                profiles.values(),
                key=lambda item: (item["role"], item["display_name"]),
            )
        ),
        total_paginas=len(pages),
        total_registros=len(profiles),
    )
