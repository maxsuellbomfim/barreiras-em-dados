"""Anexos oficiais da LOA da Bahia com emendas por municipio e autor.

O conector preserva o PDF integral e materializa somente um manifesto tecnico.
Valores, autores e municipios serao extraidos em document-processing, nunca
somados ou interpretados nesta fronteira de aquisicao.
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
from urllib.parse import unquote, urlparse

from ..http import (
    RETRYABLE_TRANSPORT_EXCEPTIONS,
    HttpTransport,
    ResponseTooLargeError,
    UrllibTransport,
    validate_https_url,
)
from ..logging import log_event
from ..resilience import CircuitBreaker, RetryPolicy

SOURCE_CODE = "bahia-seplan-budget"
ENDPOINT_CODE = "state-loa-amendment-annexes"
SOURCE_PAGE_URL = "https://www.ba.gov.br/seplan/orcamento/historico-de-loa"
OFFICIAL_HOSTS = frozenset({"www.ba.gov.br"})
MAX_PDF_BYTES = 96 * 1024 * 1024
TIMEOUT_SECONDS = 120.0
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
SAFE_RESPONSE_HEADERS = frozenset(
    {"content-type", "content-length", "etag", "last-modified", "date"}
)


@dataclass(frozen=True)
class StateLoaAnnexContract:
    fiscal_year: int
    annex_code: str
    title: str
    url: str
    budget_stage: str = "authorized"
    territorial_scope: str = "municipality_explicit"


YEARLY_ANNEXES: dict[int, StateLoaAnnexContract] = {
    2022: StateLoaAnnexContract(
        fiscal_year=2022,
        annex_code="III",
        title=(
            "LOA 2022 - Anexo III - Emendas Parlamentares Individuais "
            "por Municipio e Autor"
        ),
        url=(
            "https://www.ba.gov.br/seplan/sites/site-seplan/files/"
            "migracao_2024/arquivos/wp-content/uploads/"
            "LOA_2022_Anexo_III_Emendas_Parlamentares_Individuais_"
            "por_Municipio_Autor.pdf"
        ),
    ),
    2023: StateLoaAnnexContract(
        fiscal_year=2023,
        annex_code="III",
        title=(
            "LOA 2023 - Anexo III - Emendas Parlamentares Individuais "
            "por Municipio e Autor"
        ),
        url=(
            "https://www.ba.gov.br/seplan/sites/site-seplan/files/"
            "migracao_2024/arquivos/wp-content/uploads/"
            "LOA-2023-Anexo-III-Emendas-Parlamentares-Individuais-por-"
            "Municipio-e-Autor-Demonstrativo-Complementar.pdf"
        ),
    ),
    2024: StateLoaAnnexContract(
        fiscal_year=2024,
        annex_code="III",
        title=(
            "LOA 2024 - Anexo III - Emendas Parlamentares Individuais "
            "por Municipio e Autor"
        ),
        url=(
            "https://www.ba.gov.br/seplan/sites/site-seplan/files/"
            "migracao_2024/arquivos/wp-content/uploads/"
            "LOA-2024-Anexo-III-Emendas-Parlamentares-Individuais-por-"
            "Municipio-e-Autor-Demonstrativo-Complementar.pdf"
        ),
    ),
    2025: StateLoaAnnexContract(
        fiscal_year=2025,
        annex_code="III",
        title=(
            "LOA 2025 - Anexo III - Emendas Parlamentares Individuais "
            "por Municipio e Autor"
        ),
        url=(
            "https://www.ba.gov.br/seplan/sites/site-seplan/files/2025-02/"
            "LOA-2025-Anexo-III-Emendas-Parlamentares-Individuais-por-"
            "Municipio-e-Autor-Demonstrativo-Complementar.pdf"
        ),
    ),
    2026: StateLoaAnnexContract(
        fiscal_year=2026,
        annex_code="I",
        title=(
            "LOA 2026 - Anexo I - Emendas Parlamentares Individuais "
            "por Autor e Area Tematica"
        ),
        url=(
            "https://www.ba.gov.br/seplan/sites/site-seplan/files/2026-01/"
            "LOA-2026-Anexo-I-Emendas-Parlamentares-Individuais-por-Autor-"
            "e-Area-Tematica-Demonstrativo-Complementar.pdf"
        ),
    ),
}

BLOCKED_YEAR_REASONS = {
    2021: (
        "O link oficial rotulado como Anexo III da LOA 2021 aponta para o "
        "arquivo da LOA 2020; o periodo permanece bloqueado para evitar "
        "atribuir ao ano errado um documento oficial."
    )
}


class BahiaStateLoaAnnexError(RuntimeError):
    """O anexo da LOA nao pode ser preservado com seguranca."""


@dataclass(frozen=True)
class StateLoaAnnexSnapshot:
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
    fiscal_year: int
    annex_code: str


def fetch_state_loa_amendment_annex(
    fiscal_year: int,
    *,
    transport: HttpTransport | None = None,
    retry_policy: RetryPolicy | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    random_value: Callable[[], float] = random.random,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> StateLoaAnnexSnapshot:
    """Baixa um anexo anual exato, sem extrair linhas ou calcular valores."""
    if fiscal_year in BLOCKED_YEAR_REASONS:
        raise BahiaStateLoaAnnexError(
            f"O ano {fiscal_year} esta bloqueado: "
            f"{BLOCKED_YEAR_REASONS[fiscal_year]}"
        )
    contract = YEARLY_ANNEXES.get(fiscal_year)
    if contract is None:
        raise BahiaStateLoaAnnexError(
            f"O ano {fiscal_year} nao possui anexo suportado."
        )
    active_transport = transport or UrllibTransport(OFFICIAL_HOSTS)
    policy = retry_policy or RetryPolicy(max_attempts=4)
    breaker = circuit_breaker or CircuitBreaker(failure_threshold=policy.max_attempts)
    response, requested_at, received_at, attempts = _request(
        contract=contract,
        transport=active_transport,
        policy=policy,
        breaker=breaker,
        random_value=random_value,
        now=now,
        sleep=sleep,
        logger=logger,
    )
    _validate_exact_url(response.final_url, expected_url=contract.url)
    media_type = _validate_pdf_response(response.body, response.headers)
    manifest = build_state_loa_annex_manifest(response.body, contract=contract)
    body_sha256 = str(manifest["content_sha256"])
    idempotency_key = hashlib.sha256(
        json.dumps(
            {
                "fiscal_year": fiscal_year,
                "annex_code": contract.annex_code,
                "source_url": contract.url,
                "body_sha256": body_sha256,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return StateLoaAnnexSnapshot(
        schema_name="bahia-state-loa-amendment-annex",
        schema_version="1.0.0",
        artifact_kind="document",
        source_code=SOURCE_CODE,
        endpoint_code=ENDPOINT_CODE,
        idempotency_key=idempotency_key,
        request_url=contract.url,
        final_url=response.final_url,
        requested_at=requested_at,
        received_at=received_at,
        window_start=f"{fiscal_year}-01-01",
        window_end=f"{fiscal_year}-12-31",
        attempts=attempts,
        http_status=response.status,
        collection_status="success",
        body_sha256=body_sha256,
        body_size_bytes=len(response.body),
        media_type=media_type,
        response_headers=_safe_headers(response.headers),
        cursor={"offset": 0, "size": 1},
        raw_body=response.body,
        items=(manifest,),
        total_pages=1,
        total_items=1,
        fiscal_year=fiscal_year,
        annex_code=contract.annex_code,
    )


def build_state_loa_annex_manifest(
    body: bytes,
    *,
    contract: StateLoaAnnexContract,
) -> dict[str, object]:
    """Reconstroi o manifesto tecnico diretamente dos bytes preservados."""
    _validate_pdf_bytes(body)
    return {
        "fiscal_year": contract.fiscal_year,
        "annex_code": contract.annex_code,
        "document_title": contract.title,
        "source_page_url": SOURCE_PAGE_URL,
        "source_url": contract.url,
        "budget_stage": contract.budget_stage,
        "territorial_scope": contract.territorial_scope,
        "content_sha256": hashlib.sha256(body).hexdigest(),
        "byte_size": len(body),
    }


def _request(
    *,
    contract: StateLoaAnnexContract,
    transport: HttpTransport,
    policy: RetryPolicy,
    breaker: CircuitBreaker,
    random_value: Callable[[], float],
    now: Callable[[], datetime],
    sleep: Callable[[float], None],
    logger: logging.Logger | None,
):
    log = logger or logging.getLogger(__name__)
    for attempt in range(1, policy.max_attempts + 1):
        breaker.before_request()
        requested_at = now().isoformat()
        try:
            response = transport.get(
                contract.url,
                headers={
                    "Accept": "application/pdf, application/octet-stream",
                    "User-Agent": "Barreiras360-Collector/0.1",
                },
                timeout_seconds=TIMEOUT_SECONDS,
                max_body_bytes=MAX_PDF_BYTES,
            )
        except ResponseTooLargeError as error:
            breaker.record_failure()
            raise BahiaStateLoaAnnexError(
                "O PDF estadual excedeu o limite de tamanho permitido."
            ) from error
        except RETRYABLE_TRANSPORT_EXCEPTIONS as error:
            breaker.record_failure()
            if attempt < policy.max_attempts:
                sleep(policy.delay(attempt, random_value()))
                continue
            raise BahiaStateLoaAnnexError(
                f"O anexo da LOA {contract.fiscal_year} ficou indisponivel."
            ) from error
        received_at = now().isoformat()
        log_event(
            log,
            logging.INFO,
            "collector_http_response",
            source=SOURCE_CODE,
            endpoint=ENDPOINT_CODE,
            fiscal_year=contract.fiscal_year,
            status=response.status,
            attempt=attempt,
            body_size_bytes=len(response.body),
        )
        if response.status == 200:
            breaker.record_success()
            return response, requested_at, received_at, attempt
        if response.status not in RETRYABLE_HTTP_STATUSES:
            raise BahiaStateLoaAnnexError(
                f"A fonte da LOA respondeu HTTP {response.status}."
            )
        breaker.record_failure()
        if attempt < policy.max_attempts:
            sleep(policy.delay(attempt, random_value()))
    raise BahiaStateLoaAnnexError(
        f"O anexo da LOA {contract.fiscal_year} ficou indisponivel."
    )


def _validate_pdf_response(body: bytes, headers: Mapping[str, str]) -> str:
    normalized = {str(key).lower(): str(value) for key, value in headers.items()}
    media_type = normalized.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type not in {"application/pdf", "application/octet-stream"}:
        raise BahiaStateLoaAnnexError(
            "A fonte estadual nao devolveu um tipo de conteudo PDF permitido."
        )
    declared_length = normalized.get("content-length")
    if declared_length:
        try:
            parsed_length = int(declared_length)
        except ValueError as error:
            raise BahiaStateLoaAnnexError(
                "O Content-Length do PDF estadual e invalido."
            ) from error
        if parsed_length != len(body):
            raise BahiaStateLoaAnnexError(
                "O tamanho HTTP do PDF estadual diverge dos bytes recebidos."
            )
    _validate_pdf_bytes(body)
    return "application/pdf"


def _validate_pdf_bytes(body: bytes) -> None:
    if not body.startswith(b"%PDF-") or b"%%EOF" not in body[-2048:]:
        raise BahiaStateLoaAnnexError(
            "O documento estadual nao possui a estrutura minima de um PDF."
        )


def _validate_exact_url(url: str, *, expected_url: str) -> None:
    try:
        validate_https_url(url, OFFICIAL_HOSTS)
    except ValueError as error:
        raise BahiaStateLoaAnnexError(
            "A fonte da LOA redirecionou para URL nao oficial."
        ) from error
    parsed = urlparse(url)
    expected = urlparse(expected_url)
    if (
        unquote(parsed.path) != unquote(expected.path)
        or parsed.query != expected.query
        or parsed.fragment
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise BahiaStateLoaAnnexError(
            "A fonte da LOA redirecionou para URL nao oficial."
        )


def _safe_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        str(key).lower(): str(value)
        for key, value in headers.items()
        if str(key).lower() in SAFE_RESPONSE_HEADERS
    }
