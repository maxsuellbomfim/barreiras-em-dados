"""Catálogo e arquivo oficial de emendas parlamentares estaduais da Bahia.

Esta etapa preserva o ZIP e valida a estrutura das cinco views publicadas pelo
FIPLAN. Ela não tenta atribuir registros a Barreiras, pois o arquivo atual não
publica uma coluna municipal explícita.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
import random
import re
import struct
import time
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
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

SOURCE_CODE = "bahia-open-data"
ENDPOINT_CODE = "state-parliamentary-amendments"
DATASET_ID = "1436b3e7-6594-4683-bfa5-b2e3a6c69e07"
DATASET_NAME = "emendas-parlamentares"
RESOURCE_ID = "2d284f2e-79cc-4e3c-a45b-6fc903a6e2d0"
ARCHIVE_NAME = "emendasparlamentares.zip"
RELATIONSHIP_RESOURCE_ID = "f463ff7d-569c-4b48-b1d3-c80f017779df"
RELATIONSHIP_RESOURCE_NAME = "Emendas Parlamentares - Relacionamento_Views.png"
CATALOG_URL = (
    "https://dados.ba.gov.br/api/3/action/"
    "package_show?id=emendas-parlamentares"
)
DOWNLOAD_URL = (
    f"https://dados.ba.gov.br/dataset/{DATASET_ID}/resource/{RESOURCE_ID}/"
    f"download/{ARCHIVE_NAME}"
)
RELATIONSHIP_DIAGRAM_URL = (
    f"https://dados.ba.gov.br/dataset/{DATASET_ID}/resource/"
    f"{RELATIONSHIP_RESOURCE_ID}/download/"
    "emendas-parlamentares-relacionamento_views.png"
)
OFFICIAL_HOSTS = frozenset({"dados.ba.gov.br"})
STATE_TLS_CA_BUNDLE = Path(
    os.getenv(
        "BAHIA_STATE_TLS_CA_BUNDLE",
        "config/certificates/sectigo-public-server-authentication-ov-r36-chain.pem",
    )
)
MAX_CATALOG_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_RELATIONSHIP_DIAGRAM_BYTES = 2 * 1024 * 1024
MAX_MEMBER_BYTES = 32 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
TIMEOUT_SECONDS = 120.0
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
SAFE_RESPONSE_HEADERS = frozenset(
    {"content-type", "content-length", "etag", "last-modified", "date"}
)

EXPECTED_MEMBER_COLUMNS: dict[str, tuple[str, ...]] = {
    "VW_PAINEL_EMENDAS_PARLAMENTARES_CENTRALIZACAO_DESCENTRALIZACAO.csv": (
        "num_codigo",
        "num_codigo_exec",
        "num_codigo_liqu",
        "nom_orgao_orcamento_exec",
    ),
    "VW_PAINEL_EMENDAS_PARLAMENTARES_DESPESAS.csv": (
        "Ano Exercício",
        "Órgão",
        "sgl_orgao_orcamento",
        "Unidade Orçamentária",
        "nom_res_unidade_orcamentaria",
        "Ação do Programa de Governo",
        "cod_subfonte_recurso",
        "Deputado",
        "Nome do Deputado",
        "num_codigo",
        "Valor Orçado Inicial.",
        "Valor Orçado Atual.",
        "Valor Empenhado.",
        "Valor Liquidado.",
        "Valor Pago.",
    ),
    "VW_PAINEL_EMENDAS_PARLAMENTARES_LIQUIDACAO_ORCAMENTO.csv": (
        "val_liquidacao",
        "dtc_liquidacao",
        "dtc_cadastro",
        "dtc_ultima_atualizacao",
        "num_codigo_liqu",
    ),
    "VW_PAINEL_EMENDAS_PARLAMENTARES_PAGAMENTOS.csv": (
        "num_pagto_nob",
        "Nº do Pagamento Formatado",
        "RazaoSocialCredorPagamento",
        "Data do Pagamento",
        "val_pagto_nob",
        "Pagamento_Efetivado",
        "val_GCV",
        "Objeto",
        "num_empenho",
        "num_codigo_exec",
    ),
    "VW_PROCESSO_SEI.csv": (
        "num_empenho_orcamento",
        "num_processo_sist_elet_info",
    ),
}

PAYMENT_MEMBER_NAME = "VW_PAINEL_EMENDAS_PARLAMENTARES_PAGAMENTOS.csv"
PAYMENT_RECORD_START = re.compile(
    r'(?m)^"\d{18,19}";"\d{5}\.\d{4}\.\d{2}\.\d{7}-\d?";'
)
PAYMENT_RECORD = re.compile(
    r'^"(?P<payment_id>\d{18,19})";'
    r'"(?P<formatted_id>\d{5}\.\d{4}\.\d{2}\.\d{7}-\d?)";'
    r'"(?P<creditor>[^"\r\n]*)";'
    r'"(?P<date>\d{2}/\d{2}/\d{4} 00:00:00)";'
    r'"(?P<amount>-?\d+(?:,\d+)?)";'
    r'"(?P<status>[^"\r\n]+)";'
    r'"(?P<gcv>-?\d*(?:,\d+)?)";'
    r'"(?P<object>[\s\S]*)";'
    r'"(?P<commitment_id>\d{18,19})";'
    r'"(?P<execution_code>'
    r'\d{4}\.\d\.\d{1,2}\.\d{4,5}\.\d+\.\d+\.\d+\.\d+'
    r')"$'
)


class BahiaStateAmendmentArchiveError(RuntimeError):
    """A fonte estadual não permite preservação segura neste retrato."""


@dataclass(frozen=True)
class BahiaStateAmendmentCatalogSnapshot:
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


@dataclass(frozen=True)
class BahiaStateAmendmentArchiveSnapshot:
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
    catalog_sha256: str
    resource_last_modified: str


@dataclass(frozen=True)
class BahiaStateAmendmentRelationshipSnapshot:
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
    catalog_sha256: str
    resource_last_modified: str


def fetch_state_amendment_catalog(
    *,
    transport: HttpTransport | None = None,
    retry_policy: RetryPolicy | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    random_value: Callable[[], float] = random.random,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> BahiaStateAmendmentCatalogSnapshot:
    """Obtém e valida o catálogo CKAN que referencia o ZIP diário."""
    active_transport = transport or UrllibTransport(
        OFFICIAL_HOSTS,
        additional_ca_bundle=STATE_TLS_CA_BUNDLE,
    )
    policy = retry_policy or RetryPolicy(max_attempts=4)
    breaker = circuit_breaker or CircuitBreaker(failure_threshold=policy.max_attempts)
    response, requested_at, received_at, attempts = _request(
        url=CATALOG_URL,
        accept="application/json",
        max_body_bytes=MAX_CATALOG_BYTES,
        unavailable_message="O catálogo estadual de emendas ficou indisponível.",
        transport=active_transport,
        policy=policy,
        breaker=breaker,
        random_value=random_value,
        now=now,
        sleep=sleep,
        logger=logger,
    )
    _validate_exact_url(response.final_url, expected_url=CATALOG_URL)
    resource = parse_state_amendment_catalog(response.body)
    body_sha256 = hashlib.sha256(response.body).hexdigest()
    idempotency_key = _digest(
        {"catalog_sha256": body_sha256, "resource_id": RESOURCE_ID}
    )
    return BahiaStateAmendmentCatalogSnapshot(
        schema_name="bahia-state-amendment-catalog",
        schema_version="1.0.0",
        artifact_kind="http_response",
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
        http_status=200,
        collection_status="success",
        body_sha256=body_sha256,
        body_size_bytes=len(response.body),
        media_type="application/json",
        response_headers=_safe_headers(response.headers),
        cursor={"offset": 0, "size": 1},
        raw_body=response.body,
        items=(resource,),
        total_pages=1,
        total_items=1,
    )


def fetch_state_amendment_archive(
    *,
    catalog: BahiaStateAmendmentCatalogSnapshot,
    transport: HttpTransport | None = None,
    retry_policy: RetryPolicy | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    random_value: Callable[[], float] = random.random,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> BahiaStateAmendmentArchiveSnapshot:
    """Baixa o ZIP exatamente descrito pelo catálogo já preservado."""
    resource = _catalog_resource(catalog)
    expected_size = int(resource["byte_size"])
    active_transport = transport or UrllibTransport(
        OFFICIAL_HOSTS,
        additional_ca_bundle=STATE_TLS_CA_BUNDLE,
    )
    policy = retry_policy or RetryPolicy(max_attempts=4)
    breaker = circuit_breaker or CircuitBreaker(failure_threshold=policy.max_attempts)
    response, requested_at, received_at, attempts = _request(
        url=DOWNLOAD_URL,
        accept="application/zip, application/octet-stream",
        max_body_bytes=expected_size,
        unavailable_message="O ZIP estadual de emendas ficou indisponível.",
        transport=active_transport,
        policy=policy,
        breaker=breaker,
        random_value=random_value,
        now=now,
        sleep=sleep,
        logger=logger,
    )
    _validate_exact_url(response.final_url, expected_url=DOWNLOAD_URL)
    headers = _normalized_headers(response.headers)
    if len(response.body) != expected_size:
        raise BahiaStateAmendmentArchiveError(
            "O tamanho do ZIP diverge do catálogo oficial."
        )
    try:
        content_length = int(headers.get("content-length", ""))
    except ValueError as error:
        raise BahiaStateAmendmentArchiveError(
            "O Content-Length do ZIP estadual é inválido."
        ) from error
    if content_length != expected_size:
        raise BahiaStateAmendmentArchiveError(
            "O tamanho HTTP do ZIP diverge do catálogo oficial."
        )
    media_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type not in {"application/zip", "application/octet-stream"}:
        raise BahiaStateAmendmentArchiveError(
            "O tipo de conteúdo do ZIP estadual não é permitido."
        )
    members = parse_state_amendment_archive(response.body)
    body_sha256 = hashlib.sha256(response.body).hexdigest()
    idempotency_key = _digest(
        {
            "archive_sha256": body_sha256,
            "catalog_sha256": catalog.body_sha256,
            "resource_last_modified": resource["last_modified"],
        }
    )
    return BahiaStateAmendmentArchiveSnapshot(
        schema_name="bahia-state-amendment-archive",
        schema_version="1.0.0",
        artifact_kind="archive",
        source_code=SOURCE_CODE,
        endpoint_code=ENDPOINT_CODE,
        idempotency_key=idempotency_key,
        request_url=DOWNLOAD_URL,
        final_url=response.final_url,
        requested_at=requested_at,
        received_at=received_at,
        window_start=str(resource["last_modified"]),
        window_end=received_at,
        attempts=attempts,
        http_status=200,
        collection_status="success",
        body_sha256=body_sha256,
        body_size_bytes=len(response.body),
        media_type=media_type,
        response_headers=_safe_headers(response.headers),
        cursor={"offset": 0, "size": len(members)},
        raw_body=response.body,
        items=members,
        total_pages=1,
        total_items=len(members),
        catalog_sha256=catalog.body_sha256,
        resource_last_modified=str(resource["last_modified"]),
    )


def fetch_state_amendment_relationship_diagram(
    *,
    catalog: BahiaStateAmendmentCatalogSnapshot,
    transport: HttpTransport | None = None,
    retry_policy: RetryPolicy | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    random_value: Callable[[], float] = random.random,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> BahiaStateAmendmentRelationshipSnapshot:
    """Preserva o mapa oficial das chaves sem inferir ligação territorial."""
    _catalog_resource(catalog)
    resource = parse_state_amendment_relationship_resource(catalog.raw_body)
    expected_size = int(resource["byte_size"])
    active_transport = transport or UrllibTransport(
        OFFICIAL_HOSTS,
        additional_ca_bundle=STATE_TLS_CA_BUNDLE,
    )
    policy = retry_policy or RetryPolicy(max_attempts=4)
    breaker = circuit_breaker or CircuitBreaker(failure_threshold=policy.max_attempts)
    response, requested_at, received_at, attempts = _request(
        url=RELATIONSHIP_DIAGRAM_URL,
        accept="image/png",
        max_body_bytes=expected_size,
        unavailable_message="O diagrama estadual de relacionamento ficou indisponível.",
        transport=active_transport,
        policy=policy,
        breaker=breaker,
        random_value=random_value,
        now=now,
        sleep=sleep,
        logger=logger,
    )
    _validate_exact_url(response.final_url, expected_url=RELATIONSHIP_DIAGRAM_URL)
    headers = _normalized_headers(response.headers)
    if len(response.body) != expected_size:
        raise BahiaStateAmendmentArchiveError(
            "O tamanho do diagrama diverge do catálogo oficial."
        )
    try:
        content_length = int(headers.get("content-length", ""))
    except ValueError as error:
        raise BahiaStateAmendmentArchiveError(
            "O Content-Length do diagrama estadual é inválido."
        ) from error
    if content_length != expected_size:
        raise BahiaStateAmendmentArchiveError(
            "O tamanho HTTP do diagrama diverge do catálogo oficial."
        )
    media_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != "image/png":
        raise BahiaStateAmendmentArchiveError(
            "O tipo de conteúdo do diagrama estadual não é permitido."
        )
    width, height = _png_dimensions(response.body)
    body_sha256 = hashlib.sha256(response.body).hexdigest()
    manifest = {
        **resource,
        "content_sha256": body_sha256,
        "width_pixels": width,
        "height_pixels": height,
        "relationship_scope": "execution_internal_codes_only",
        "territorial_key": "not_available",
    }
    validate_state_amendment_relationship_manifest(response.body, manifest)
    return BahiaStateAmendmentRelationshipSnapshot(
        schema_name="bahia-state-amendment-relationship-diagram",
        schema_version="1.0.0",
        artifact_kind="document",
        source_code=SOURCE_CODE,
        endpoint_code=ENDPOINT_CODE,
        idempotency_key=_digest(
            {
                "diagram_sha256": body_sha256,
                "catalog_sha256": catalog.body_sha256,
                "resource_last_modified": resource["last_modified"],
            }
        ),
        request_url=RELATIONSHIP_DIAGRAM_URL,
        final_url=response.final_url,
        requested_at=requested_at,
        received_at=received_at,
        window_start=str(resource["last_modified"]),
        window_end=received_at,
        attempts=attempts,
        http_status=200,
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
        catalog_sha256=catalog.body_sha256,
        resource_last_modified=str(resource["last_modified"]),
    )


def parse_state_amendment_archive(body: bytes) -> tuple[dict[str, object], ...]:
    """Valida membros e cabeçalhos; não calcula nem publica valores."""
    try:
        package = zipfile.ZipFile(io.BytesIO(body))
    except (zipfile.BadZipFile, OSError) as error:
        raise BahiaStateAmendmentArchiveError(
            "O arquivo estadual não é um ZIP válido."
        ) from error
    manifests: list[dict[str, object]] = []
    with package:
        members = package.infolist()
        names = {member.filename for member in members}
        if len(names) != len(members) or names != set(EXPECTED_MEMBER_COLUMNS):
            raise BahiaStateAmendmentArchiveError(
                "O ZIP estadual não contém exatamente as cinco views contratadas."
            )
        total_uncompressed = sum(member.file_size for member in members)
        if total_uncompressed < 1 or total_uncompressed > MAX_UNCOMPRESSED_BYTES:
            raise BahiaStateAmendmentArchiveError(
                "O tamanho descompactado do ZIP estadual viola o limite."
            )
        for member in sorted(members, key=lambda item: item.filename):
            if (
                member.is_dir()
                or member.flag_bits & 0x1
                or member.file_size < 1
                or member.file_size > MAX_MEMBER_BYTES
                or member.compress_size < 1
                or member.file_size > member.compress_size * MAX_COMPRESSION_RATIO
                or member.compress_type
                not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
            ):
                raise BahiaStateAmendmentArchiveError(
                    f"O membro {member.filename} viola os limites de segurança."
                )
            try:
                content = package.read(member)
                decoded = content.decode("utf-8-sig", errors="strict")
                reader = csv.reader(
                    io.StringIO(decoded, newline=""),
                    delimiter=";",
                    strict=True,
                )
                header = tuple(next(reader))
                if header != EXPECTED_MEMBER_COLUMNS[member.filename]:
                    raise BahiaStateAmendmentArchiveError(
                        f"O cabeçalho de {member.filename} diverge do contrato."
                    )
                row_count = 0
                row_count_status = "validated"
                validation_warnings: dict[str, object] = {}
                try:
                    for row in reader:
                        if not row or all(not value.strip() for value in row):
                            continue
                        if len(row) != len(header):
                            row_count = None
                            row_count_status = "source_csv_malformed"
                            break
                        row_count += 1
                except csv.Error:
                    # A view de pagamentos observada em 13/08/2026 contém
                    # aspas não escapadas. O artefato continua preservável,
                    # mas não declaramos uma contagem que não foi validada.
                    row_count = None
                    row_count_status = "source_csv_malformed"
                if (
                    row_count is None
                    and member.filename == PAYMENT_MEMBER_NAME
                ):
                    recovered = _count_payment_records(decoded)
                    if recovered is not None:
                        row_count, missing_check_digit_rows = recovered
                        row_count_status = "validated_with_source_warnings"
                        validation_warnings = {
                            "record_boundary_recovery_used": True,
                            "missing_check_digit_rows": missing_check_digit_rows,
                        }
            except BahiaStateAmendmentArchiveError:
                raise
            except (UnicodeDecodeError, csv.Error, EOFError, RuntimeError) as error:
                raise BahiaStateAmendmentArchiveError(
                    f"O conteúdo de {member.filename} está inválido."
                ) from error
            manifests.append(
                {
                    "member_name": member.filename,
                    "columns": list(header),
                    "row_count": row_count,
                    "row_count_status": row_count_status,
                    "validation_warnings": validation_warnings,
                    "physical_line_count": max(len(decoded.splitlines()) - 1, 0),
                    "uncompressed_bytes": member.file_size,
                    "compressed_bytes": member.compress_size,
                    "content_sha256": hashlib.sha256(content).hexdigest(),
                }
            )
    return tuple(manifests)


def _count_payment_records(decoded: str) -> tuple[int, int] | None:
    """Conta a view quebrada sem completar ou normalizar campos da fonte."""
    first_line_end = decoded.find("\n")
    if first_line_end < 0:
        return None
    data = decoded[first_line_end + 1 :]
    starts = [match.start() for match in PAYMENT_RECORD_START.finditer(data)]
    if not starts or data[: starts[0]].strip():
        return None

    missing_check_digit_rows = 0
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(data)
        record = data[start:end].rstrip("\r\n")
        match = PAYMENT_RECORD.fullmatch(record)
        if match is None:
            return None
        values = match.groupdict()
        if (
            len(values["payment_id"]) == 18
            or values["formatted_id"].endswith("-")
            or len(values["commitment_id"]) == 18
        ):
            missing_check_digit_rows += 1
    return len(starts), missing_check_digit_rows


def _request(
    *,
    url: str,
    accept: str,
    max_body_bytes: int,
    unavailable_message: str,
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
                url,
                headers={
                    "Accept": accept,
                    "User-Agent": "Barreiras360-Collector/0.1",
                },
                timeout_seconds=TIMEOUT_SECONDS,
                max_body_bytes=max_body_bytes,
            )
        except ResponseTooLargeError as error:
            breaker.record_failure()
            raise BahiaStateAmendmentArchiveError(
                "A resposta estadual excedeu o tamanho oficial permitido."
            ) from error
        except RETRYABLE_TRANSPORT_EXCEPTIONS as error:
            breaker.record_failure()
            if attempt < policy.max_attempts:
                sleep(policy.delay(attempt, random_value()))
                continue
            raise BahiaStateAmendmentArchiveError(unavailable_message) from error
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
            breaker.record_success()
            return response, requested_at, received_at, attempt
        if response.status not in RETRYABLE_HTTP_STATUSES:
            raise BahiaStateAmendmentArchiveError(
                f"A fonte estadual respondeu HTTP {response.status}."
            )
        breaker.record_failure()
        if attempt < policy.max_attempts:
            sleep(policy.delay(attempt, random_value()))
    raise BahiaStateAmendmentArchiveError(unavailable_message)


def parse_state_amendment_catalog(body: bytes) -> dict[str, object]:
    """Revalida o JSON CKAN preservado e extrai o único ZIP contratado."""
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BahiaStateAmendmentArchiveError(
            "O catálogo estadual não devolveu JSON UTF-8 válido."
        ) from error
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise BahiaStateAmendmentArchiveError(
            "O catálogo estadual declarou falha de contrato."
        )
    result = payload.get("result")
    if (
        not isinstance(result, dict)
        or result.get("id") != DATASET_ID
        or result.get("name") != DATASET_NAME
        or not isinstance(result.get("resources"), list)
    ):
        raise BahiaStateAmendmentArchiveError(
            "O catálogo estadual não corresponde ao conjunto oficial."
        )
    selected = [
        item
        for item in result["resources"]
        if isinstance(item, dict) and item.get("id") == RESOURCE_ID
    ]
    if len(selected) != 1:
        raise BahiaStateAmendmentArchiveError(
            "O recurso oficial do ZIP não aparece uma única vez no catálogo."
        )
    resource = selected[0]
    size = resource.get("size")
    if (
        resource.get("name") != "EmendasParlamentares.zip"
        or str(resource.get("format", "")).upper() != "ZIP"
        or resource.get("url") != DOWNLOAD_URL
        or not isinstance(size, int)
        or isinstance(size, bool)
        or not 1 <= size <= MAX_ARCHIVE_BYTES
        or not isinstance(resource.get("last_modified"), str)
        or not str(resource["last_modified"]).strip()
        or not isinstance(result.get("metadata_modified"), str)
        or not str(result["metadata_modified"]).strip()
    ):
        raise BahiaStateAmendmentArchiveError(
            "Os metadados do recurso oficial estão incompletos."
        )
    _validate_exact_url(str(resource["url"]), expected_url=DOWNLOAD_URL)
    return {
        "dataset_id": DATASET_ID,
        "resource_id": RESOURCE_ID,
        "resource_name": "EmendasParlamentares.zip",
        "download_url": DOWNLOAD_URL,
        "byte_size": size,
        "last_modified": str(resource["last_modified"]),
        "dataset_modified": str(result["metadata_modified"]),
    }


def parse_state_amendment_relationship_resource(
    body: bytes,
) -> dict[str, object]:
    """Extrai o recurso oficial que documenta as chaves entre as cinco views."""
    parse_state_amendment_catalog(body)
    payload = json.loads(body)
    result = payload["result"]
    selected = [
        item
        for item in result["resources"]
        if isinstance(item, dict)
        and item.get("id") == RELATIONSHIP_RESOURCE_ID
    ]
    if len(selected) != 1:
        raise BahiaStateAmendmentArchiveError(
            "O diagrama oficial não aparece uma única vez no catálogo."
        )
    resource = selected[0]
    size = resource.get("size")
    if (
        resource.get("name") != RELATIONSHIP_RESOURCE_NAME
        or str(resource.get("format", "")).upper() != "PNG"
        or resource.get("url") != RELATIONSHIP_DIAGRAM_URL
        or not isinstance(size, int)
        or isinstance(size, bool)
        or not 1 <= size <= MAX_RELATIONSHIP_DIAGRAM_BYTES
        or not isinstance(resource.get("last_modified"), str)
        or not str(resource["last_modified"]).strip()
    ):
        raise BahiaStateAmendmentArchiveError(
            "Os metadados do diagrama oficial estão incompletos."
        )
    _validate_exact_url(
        str(resource["url"]),
        expected_url=RELATIONSHIP_DIAGRAM_URL,
    )
    return {
        "dataset_id": DATASET_ID,
        "resource_id": RELATIONSHIP_RESOURCE_ID,
        "resource_name": RELATIONSHIP_RESOURCE_NAME,
        "download_url": RELATIONSHIP_DIAGRAM_URL,
        "byte_size": size,
        "last_modified": str(resource["last_modified"]),
        "dataset_modified": str(result["metadata_modified"]),
    }


def _png_dimensions(body: bytes) -> tuple[int, int]:
    if (
        len(body) < 24
        or body[:8] != b"\x89PNG\r\n\x1a\n"
        or body[12:16] != b"IHDR"
    ):
        raise BahiaStateAmendmentArchiveError(
            "O diagrama estadual não possui uma assinatura PNG válida."
        )
    width, height = struct.unpack(">II", body[16:24])
    if not 1 <= width <= 10_000 or not 1 <= height <= 10_000:
        raise BahiaStateAmendmentArchiveError(
            "As dimensões do diagrama estadual violam o limite."
        )
    return width, height


def validate_state_amendment_relationship_manifest(
    body: bytes,
    manifest: Mapping[str, object],
) -> None:
    """Revalida a evidência restaurada sem interpretar seu conteúdo visual."""
    width, height = _png_dimensions(body)
    if (
        manifest.get("dataset_id") != DATASET_ID
        or manifest.get("resource_id") != RELATIONSHIP_RESOURCE_ID
        or manifest.get("resource_name") != RELATIONSHIP_RESOURCE_NAME
        or manifest.get("download_url") != RELATIONSHIP_DIAGRAM_URL
        or manifest.get("content_sha256") != hashlib.sha256(body).hexdigest()
        or manifest.get("width_pixels") != width
        or manifest.get("height_pixels") != height
        or manifest.get("relationship_scope")
        != "execution_internal_codes_only"
        or manifest.get("territorial_key") != "not_available"
    ):
        raise BahiaStateAmendmentArchiveError(
            "O manifesto do diagrama estadual diverge da evidência preservada."
        )


def _catalog_resource(
    catalog: BahiaStateAmendmentCatalogSnapshot,
) -> Mapping[str, object]:
    if (
        catalog.source_code != SOURCE_CODE
        or catalog.endpoint_code != ENDPOINT_CODE
        or catalog.schema_name != "bahia-state-amendment-catalog"
        or len(catalog.items) != 1
        or hashlib.sha256(catalog.raw_body).hexdigest() != catalog.body_sha256
    ):
        raise BahiaStateAmendmentArchiveError(
            "O catálogo preservado não corresponde ao contrato estadual."
        )
    resource = catalog.items[0]
    if (
        resource.get("resource_id") != RESOURCE_ID
        or resource.get("download_url") != DOWNLOAD_URL
    ):
        raise BahiaStateAmendmentArchiveError(
            "O catálogo preservado não referencia o recurso oficial."
        )
    return resource


def _validate_exact_url(url: str, *, expected_url: str) -> None:
    try:
        validate_https_url(url, OFFICIAL_HOSTS)
    except ValueError as error:
        raise BahiaStateAmendmentArchiveError(
            "A fonte estadual redirecionou para URL não oficial."
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
        raise BahiaStateAmendmentArchiveError(
            "A fonte estadual redirecionou para URL não oficial."
        )


def _normalized_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in headers.items()}


def _safe_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in _normalized_headers(headers).items()
        if key in SAFE_RESPONSE_HEADERS
    }


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
