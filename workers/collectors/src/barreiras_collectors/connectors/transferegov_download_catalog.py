"""Catálogo oficial dos arquivos históricos do Transferegov.

O conector preserva o XML integral e seleciona somente os conjuntos necessários
ao rastro municipal. Ele não baixa nem interpreta os ZIPs nesta etapa.
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

from defusedxml import ElementTree as ET

from ..http import (
    RETRYABLE_TRANSPORT_EXCEPTIONS,
    HttpTransport,
    UrllibTransport,
    validate_https_url,
)
from ..logging import log_event
from ..resilience import CircuitBreaker, RetryPolicy

SOURCE_CODE = "transferegov-downloads"
ENDPOINT_CODE = "dados-abertos-catalogo"
CATALOG_URL = (
    "https://api-publica.transferegov.gestao.gov.br/"
    "downloads/dadosgov/?restype=container&comp=list"
)
CATALOG_HOSTS = frozenset({"api-publica.transferegov.gestao.gov.br"})
BLOB_HOST = "trsfgovprodstrgaccpublic.blob.core.windows.net"
BLOB_CONTAINER = "trsfgov-prod-public-data"
REQUIRED_HISTORICAL_FILES = frozenset(
    {
        "siconv_convenio.zip",
        "siconv_desembolso.zip",
        "siconv_emenda.zip",
        "siconv_empenho.zip",
        "siconv_pagamento.zip",
        "siconv_proponentes.zip",
        "siconv_proposta.zip",
        "siconv_termo_aditivo.zip",
    }
)
TIMEOUT_SECONDS = 60.0
MAX_BODY_BYTES = 8 * 1024 * 1024
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
SAFE_RESPONSE_HEADERS = frozenset(
    {"content-type", "etag", "last-modified", "content-length", "date"}
)


class TransferegovDownloadCatalogError(RuntimeError):
    """Falha explícita de disponibilidade ou contrato do catálogo."""


@dataclass(frozen=True)
class TransferegovDownloadCatalogSnapshot:
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
    items: tuple[dict[str, object], ...]
    total_pages: int
    total_items: int


def fetch_download_catalog(
    *,
    transport: HttpTransport | None = None,
    retry_policy: RetryPolicy | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    random_value: Callable[[], float] = random.random,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> TransferegovDownloadCatalogSnapshot:
    """Obtém uma enumeração completa e validada dos downloads oficiais."""
    active_transport = transport or UrllibTransport(CATALOG_HOSTS)
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
                CATALOG_URL,
                headers={
                    "Accept": "application/xml",
                    "User-Agent": "Barreiras360-Collector/0.1",
                },
                timeout_seconds=TIMEOUT_SECONDS,
                max_body_bytes=MAX_BODY_BYTES,
            )
        except RETRYABLE_TRANSPORT_EXCEPTIONS as error:
            breaker.record_failure()
            if attempt < policy.max_attempts:
                sleep(policy.delay(attempt, random_value()))
                continue
            raise TransferegovDownloadCatalogError(
                "O catálogo de downloads do Transferegov ficou indisponível."
            ) from error

        received_at = now().isoformat()
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
                snapshot = _parse_catalog(
                    response=response,
                    requested_at=requested_at,
                    received_at=received_at,
                    attempts=attempt,
                )
            except TransferegovDownloadCatalogError:
                breaker.record_failure()
                raise
            breaker.record_success()
            return snapshot
        if response.status not in RETRYABLE_HTTP_STATUSES:
            raise TransferegovDownloadCatalogError(
                "O catálogo de downloads respondeu "
                f"HTTP {response.status}."
            )
        breaker.record_failure()
        if attempt < policy.max_attempts:
            sleep(policy.delay(attempt, random_value()))

    raise TransferegovDownloadCatalogError(
        "O catálogo de downloads do Transferegov ficou indisponível."
    )


def parse_catalog_items(body: bytes) -> tuple[dict[str, object], ...]:
    """Valida o XML preservado e devolve apenas os arquivos contratados."""
    upper_prefix = body[:4096].upper()
    if b"<!DOCTYPE" in upper_prefix or b"<!ENTITY" in upper_prefix:
        raise TransferegovDownloadCatalogError(
            "O XML do catálogo contém declaração não permitida."
        )
    try:
        root = ET.fromstring(body)
    except ET.ParseError as error:
        raise TransferegovDownloadCatalogError(
            "O catálogo de downloads não devolveu XML válido."
        ) from error
    if root.tag != "EnumerationResults":
        raise TransferegovDownloadCatalogError(
            "O envelope do catálogo não segue o contrato oficial."
        )
    _validate_container(root.attrib.get("ContainerName", ""))
    next_marker = (root.findtext("NextMarker") or "").strip()
    if next_marker:
        raise TransferegovDownloadCatalogError(
            "A paginação do catálogo ainda possui continuação."
        )

    selected: dict[str, dict[str, object]] = {}
    for blob in root.findall("./Blobs/Blob"):
        name = (blob.findtext("Name") or "").strip()
        if name not in REQUIRED_HISTORICAL_FILES:
            continue
        if name in selected:
            raise TransferegovDownloadCatalogError(
                f"O arquivo {name} apareceu mais de uma vez no catálogo."
            )
        url = (blob.findtext("Url") or "").strip()
        _validate_blob_url(name, url)
        properties = blob.find("Properties")
        if properties is None:
            raise TransferegovDownloadCatalogError(
                f"O arquivo {name} não possui metadados oficiais."
            )
        byte_size = _positive_catalog_int(
            properties.findtext("Content-Length"),
            field="Content-Length",
            name=name,
        )
        modified = (properties.findtext("Last-Modified") or "").strip()
        etag = (properties.findtext("Etag") or "").strip()
        blob_type = (properties.findtext("BlobType") or "").strip()
        if not modified or not etag or blob_type != "BlockBlob":
            raise TransferegovDownloadCatalogError(
                f"Os metadados oficiais de {name} estão incompletos."
            )
        selected[name] = {
            "name": name,
            "url": url,
            "byte_size": byte_size,
            "last_modified": modified,
            "etag": etag,
            "content_md5": (properties.findtext("Content-MD5") or "").strip()
            or None,
            "content_type": (
                properties.findtext("Content-Type") or ""
            ).strip(),
        }

    missing = sorted(REQUIRED_HISTORICAL_FILES - selected.keys())
    if missing:
        raise TransferegovDownloadCatalogError(
            "O catálogo oficial não listou arquivos obrigatórios: "
            + ", ".join(missing)
        )
    return tuple(selected[name] for name in sorted(selected))


def _parse_catalog(
    *, response, requested_at: str, received_at: str, attempts: int
) -> TransferegovDownloadCatalogSnapshot:
    items = parse_catalog_items(response.body)
    body_sha256 = hashlib.sha256(response.body).hexdigest()
    idempotency_key = hashlib.sha256(
        json.dumps(
            {"url": CATALOG_URL, "body_sha256": body_sha256},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return TransferegovDownloadCatalogSnapshot(
        schema_name="transferegov-download-catalog",
        schema_version="1.0.0",
        source_code=SOURCE_CODE,
        endpoint_code=ENDPOINT_CODE,
        idempotency_key=idempotency_key,
        request_url=CATALOG_URL,
        final_url=response.final_url,
        requested_at=requested_at,
        received_at=received_at,
        window_start=requested_at,
        window_end=received_at,
        attempts=attempts,
        http_status=response.status,
        collection_status="success",
        body_sha256=body_sha256,
        body_size_bytes=len(response.body),
        media_type="application/xml",
        response_headers=_safe_headers(response.headers),
        cursor={
            "offset": 0,
            "size": len(items),
            "selected_files": len(items),
        },
        raw_body=response.body,
        items=items,
        total_pages=1,
        total_items=len(items),
    )


def _validate_container(url: str) -> None:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != BLOB_HOST
        or parsed.path.rstrip("/") != f"/{BLOB_CONTAINER}"
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise TransferegovDownloadCatalogError(
            "O catálogo declarou contêiner fora da URL oficial."
        )


def _validate_blob_url(name: str, url: str) -> None:
    try:
        validate_https_url(url, frozenset({BLOB_HOST}))
    except ValueError as error:
        raise TransferegovDownloadCatalogError(
            f"O arquivo {name} não aponta para a URL oficial."
        ) from error
    parsed = urlparse(url)
    if (
        unquote(parsed.path) != f"/{BLOB_CONTAINER}/{name}"
        or parsed.query
        or parsed.fragment
    ):
        raise TransferegovDownloadCatalogError(
            f"O arquivo {name} não aponta para a URL oficial."
        )


def _positive_catalog_int(value: str | None, *, field: str, name: str) -> int:
    try:
        parsed = int((value or "").strip())
    except ValueError as error:
        raise TransferegovDownloadCatalogError(
            f"O campo {field} de {name} não é inteiro."
        ) from error
    if parsed < 1:
        raise TransferegovDownloadCatalogError(
            f"O campo {field} de {name} deve ser positivo."
        )
    return parsed


def _safe_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        key.lower(): value
        for key, value in headers.items()
        if key.lower() in SAFE_RESPONSE_HEADERS
    }
