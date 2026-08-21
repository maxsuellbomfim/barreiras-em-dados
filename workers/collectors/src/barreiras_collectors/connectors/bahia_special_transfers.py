"""Catálogo e arquivo oficial de Transferências Especiais da Bahia.

O conector preserva o ZIP integral e emite somente manifestos técnicos das
cinco views. A camada de aquisição não publica linhas, valores ou o campo
CPF/CNPJ presente na view de pagamentos.
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
ENDPOINT_CODE = "state-special-transfers"
DATASET_ID = "f2ecd7fa-24ce-4be2-80d5-08e2c11e3e1c"
DATASET_NAME = "transferencias-especiais"
RESOURCE_ID = "809f9b7d-c252-482d-9c92-f2169d48c29c"
ARCHIVE_NAME = "TransferenciasEspeciais.zip"
CATALOG_URL = (
    "https://dados.ba.gov.br/api/3/action/"
    "package_show?id=transferencias-especiais"
)
DOWNLOAD_URL = (
    f"https://dados.ba.gov.br/dataset/{DATASET_ID}/resource/{RESOURCE_ID}/"
    "download/transferenciasespeciais.zip"
)
OFFICIAL_HOSTS = frozenset({"dados.ba.gov.br"})
STATE_TLS_CA_BUNDLE = Path(
    os.getenv(
        "BAHIA_STATE_TLS_CA_BUNDLE",
        "config/certificates/sectigo-public-server-authentication-ov-r36-chain.pem",
    )
)
MAX_CATALOG_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_MEMBER_BYTES = 16 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 32 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
TIMEOUT_SECONDS = 120.0
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
SAFE_RESPONSE_HEADERS = frozenset(
    {"content-type", "content-length", "etag", "last-modified", "date"}
)

EXPECTED_MEMBER_COLUMNS: dict[str, tuple[str, ...]] = {
    "VW_PAINEL_TRANSFERENCIA_ESPECIAL_CENTRALIZACAO_DESCENTRALIZACAO.csv": (
        "num_codigo",
        "num_codigo_exec",
        "num_codigo_liqu",
        "nom_orgao_orcamento_exec",
    ),
    "VW_PAINEL_TRANSFERENCIA_ESPECIAL_DESPESA.csv": (
        "Ano Exercício",
        "Órgão",
        "sgl_orgao_orcamento",
        "Unidade Orçamentária",
        "nom_res_unidade_orcamentaria",
        "Ministério de Origem da Emenda",
        "Número da Emenda Parlamentar",
        "Ano da Emenda",
        "Deputado",
        "Ação do Programa de Governo",
        "COD_SUBFONTE_RECURSO",
        "num_codigo",
        "Valor Orçado Inicial",
        "Valor Orçado Atual",
        "Valor Empenhado Total",
        "Valor Liquidado Total",
        "Valor Pago",
    ),
    "VW_PAINEL_TRANSFERENCIA_ESPECIAL_INSTRUMENTO_CAPTACAO.csv": (
        "seq_inst_captacao_recurso",
        "valor_instrument_captacao",
        "dtc_assinatura",
    ),
    "VW_PAINEL_TRANSFERENCIA_ESPECIAL_LIQUIDACAO_ORCAMENTO.csv": (
        "val_liquidacao",
        "dtc_liquidacao",
        "dtc_cadastro",
        "dtc_ultima_atualizacao",
        "num_codigo_liqu",
    ),
    "VW_PAINEL_TRANSFERENCIA_ESPECIAL_PAGAMENTO.csv": (
        "num_pagto_nob",
        "Nº do Pagamento Formatado",
        "CNPJ_CPF_CREDOR_PAGAMENTO",
        "RazaoSocialCredorPagamento",
        "Data do Pagamento",
        "Valor Pagamento Nob",
        "Valor GCV",
        "Objeto",
        "Empenho",
        "ano_exercicio",
        "num_codigo_exec",
        "Pagamento_Efetivado",
        "URL Painel de Pagamentos",
    ),
}
PAYMENT_MEMBER_NAME = "VW_PAINEL_TRANSFERENCIA_ESPECIAL_PAGAMENTO.csv"
RESTRICTED_COLUMNS = frozenset({"CNPJ_CPF_CREDOR_PAGAMENTO"})
PAYMENT_RECORD_START = re.compile(r'(?m)^"?(?P<payment_id>\d{18,19})"?;')
PAYMENT_RECORD_TAIL = re.compile(
    r';"?(?P<status>Sim|Não|Em Processamento)"?;'
    r'"?https://www\.transparencia\.ba\.gov\.br/[^";\r\n]+"?\s*$',
    re.IGNORECASE,
)
EXECUTION_CODE = re.compile(
    r'\d{4}\.\d+\.\d+\.\d+\.\d+\.\d+\.\d+\.\d+'
)


class BahiaSpecialTransferArchiveError(RuntimeError):
    """A fonte não permite preservação segura neste retrato."""


@dataclass(frozen=True)
class BahiaSpecialTransferCatalogSnapshot:
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
class BahiaSpecialTransferArchiveSnapshot:
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
    resource_id: str
    resource_name: str
    resource_last_modified: str


def fetch_special_transfer_catalog(
    *,
    transport: HttpTransport | None = None,
    retry_policy: RetryPolicy | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    random_value: Callable[[], float] = random.random,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> BahiaSpecialTransferCatalogSnapshot:
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
        unavailable_message=(
            "O catálogo de transferências especiais ficou indisponível."
        ),
        transport=active_transport,
        policy=policy,
        breaker=breaker,
        random_value=random_value,
        now=now,
        sleep=sleep,
        logger=logger,
    )
    _validate_exact_url(response.final_url, expected_url=CATALOG_URL)
    resource = parse_special_transfer_catalog(response.body)
    body_sha256 = hashlib.sha256(response.body).hexdigest()
    return BahiaSpecialTransferCatalogSnapshot(
        schema_name="bahia-special-transfer-catalog",
        schema_version="1.0.0",
        artifact_kind="http_response",
        source_code=SOURCE_CODE,
        endpoint_code=ENDPOINT_CODE,
        idempotency_key=_digest(
            {"catalog_sha256": body_sha256, "resource_id": RESOURCE_ID}
        ),
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


def fetch_special_transfer_archive(
    *,
    catalog: BahiaSpecialTransferCatalogSnapshot,
    transport: HttpTransport | None = None,
    retry_policy: RetryPolicy | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    random_value: Callable[[], float] = random.random,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> BahiaSpecialTransferArchiveSnapshot:
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
        unavailable_message="O ZIP de transferências especiais ficou indisponível.",
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
        raise BahiaSpecialTransferArchiveError(
            "O tamanho do ZIP diverge do catálogo oficial."
        )
    try:
        content_length = int(headers.get("content-length", ""))
    except ValueError as error:
        raise BahiaSpecialTransferArchiveError(
            "O Content-Length do ZIP é inválido."
        ) from error
    if content_length != expected_size:
        raise BahiaSpecialTransferArchiveError(
            "O tamanho HTTP do ZIP diverge do catálogo oficial."
        )
    media_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type not in {"application/zip", "application/octet-stream"}:
        raise BahiaSpecialTransferArchiveError(
            "O tipo de conteúdo do ZIP não é permitido."
        )
    manifests = parse_special_transfer_archive(response.body)
    body_sha256 = hashlib.sha256(response.body).hexdigest()
    return BahiaSpecialTransferArchiveSnapshot(
        schema_name="bahia-special-transfer-archive",
        schema_version="1.0.0",
        artifact_kind="archive",
        source_code=SOURCE_CODE,
        endpoint_code=ENDPOINT_CODE,
        idempotency_key=_digest(
            {
                "archive_sha256": body_sha256,
                "catalog_sha256": catalog.body_sha256,
                "resource_last_modified": resource["last_modified"],
            }
        ),
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
        cursor={"offset": 0, "size": len(manifests)},
        raw_body=response.body,
        items=manifests,
        total_pages=1,
        total_items=len(manifests),
        catalog_sha256=catalog.body_sha256,
        resource_id=RESOURCE_ID,
        resource_name=ARCHIVE_NAME,
        resource_last_modified=str(resource["last_modified"]),
    )


def parse_special_transfer_archive(body: bytes) -> tuple[dict[str, object], ...]:
    """Valida estrutura e contagens sem materializar linhas no manifesto."""
    try:
        package = zipfile.ZipFile(io.BytesIO(body))
    except (zipfile.BadZipFile, OSError) as error:
        raise BahiaSpecialTransferArchiveError(
            "O arquivo oficial não é um ZIP válido."
        ) from error
    manifests: list[dict[str, object]] = []
    with package:
        members = package.infolist()
        names = {member.filename for member in members}
        if len(names) != len(members) or names != set(EXPECTED_MEMBER_COLUMNS):
            raise BahiaSpecialTransferArchiveError(
                "O ZIP não contém exatamente as cinco views contratadas."
            )
        total_uncompressed = sum(member.file_size for member in members)
        if not 1 <= total_uncompressed <= MAX_UNCOMPRESSED_BYTES:
            raise BahiaSpecialTransferArchiveError(
                "O tamanho descompactado do ZIP viola o limite."
            )
        for member in sorted(members, key=lambda item: item.filename):
            if (
                member.is_dir()
                or member.flag_bits & 0x1
                or not 1 <= member.file_size <= MAX_MEMBER_BYTES
                or member.compress_size < 1
                or member.file_size > member.compress_size * MAX_COMPRESSION_RATIO
                or member.compress_type
                not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
            ):
                raise BahiaSpecialTransferArchiveError(
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
                    raise BahiaSpecialTransferArchiveError(
                        f"O cabeçalho de {member.filename} diverge do contrato."
                    )
                row_count: int | None = 0
                row_count_status = "validated"
                validation_warnings: dict[str, object] = {}
                try:
                    for row in reader:
                        if not row or all(not value.strip() for value in row):
                            continue
                        if len(row) != len(header):
                            row_count = None
                            break
                        row_count += 1
                except csv.Error:
                    row_count = None
                if row_count is None and member.filename == PAYMENT_MEMBER_NAME:
                    recovered = _count_payment_records(decoded)
                    if recovered is not None:
                        row_count, missing_check_digit_rows = recovered
                        row_count_status = "validated_with_source_warnings"
                        validation_warnings = {
                            "record_boundary_recovery_used": True,
                            "missing_check_digit_rows": missing_check_digit_rows,
                        }
                if row_count is None:
                    raise BahiaSpecialTransferArchiveError(
                        f"Uma linha de {member.filename} tem estrutura inválida."
                    )
            except BahiaSpecialTransferArchiveError:
                raise
            except (UnicodeDecodeError, csv.Error, EOFError, RuntimeError) as error:
                raise BahiaSpecialTransferArchiveError(
                    f"O conteúdo de {member.filename} está inválido."
                ) from error
            restricted = [column for column in header if column in RESTRICTED_COLUMNS]
            manifests.append(
                {
                    "member_name": member.filename,
                    "columns": list(header),
                    "row_count": row_count,
                    "row_count_status": row_count_status,
                    "validation_warnings": validation_warnings,
                    "restricted_columns": restricted,
                    "public_row_projection": (
                        "forbidden" if restricted else "not_created"
                    ),
                    "territorial_scope": (
                        "object_text_only"
                        if member.filename == PAYMENT_MEMBER_NAME
                        else "not_available"
                    ),
                    "uncompressed_bytes": member.file_size,
                    "compressed_bytes": member.compress_size,
                    "content_sha256": hashlib.sha256(content).hexdigest(),
                }
            )
    return tuple(manifests)


def _count_payment_records(decoded: str) -> tuple[int, int] | None:
    """Recupera somente limites e contagem; não materializa campos pessoais."""
    first_line_end = decoded.find("\n")
    if first_line_end < 0:
        return None
    data = decoded[first_line_end + 1 :]
    starts = list(PAYMENT_RECORD_START.finditer(data))
    if not starts or data[: starts[0].start()].strip():
        return None
    missing_check_digit_rows = 0
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(data)
        record = data[match.start() : end].rstrip("\r\n")
        if (
            PAYMENT_RECORD_TAIL.search(record) is None
            or len(EXECUTION_CODE.findall(record)) != 1
        ):
            return None
        if len(match.group("payment_id")) == 18:
            missing_check_digit_rows += 1
    return len(starts), missing_check_digit_rows


def parse_special_transfer_catalog(body: bytes) -> dict[str, object]:
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BahiaSpecialTransferArchiveError(
            "O catálogo não devolveu JSON UTF-8 válido."
        ) from error
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise BahiaSpecialTransferArchiveError("O catálogo declarou falha de contrato.")
    result = payload.get("result")
    if (
        not isinstance(result, dict)
        or result.get("id") != DATASET_ID
        or result.get("name") != DATASET_NAME
        or not isinstance(result.get("resources"), list)
    ):
        raise BahiaSpecialTransferArchiveError(
            "O catálogo não corresponde ao conjunto oficial."
        )
    selected = [
        item
        for item in result["resources"]
        if isinstance(item, dict) and item.get("id") == RESOURCE_ID
    ]
    if len(selected) != 1:
        raise BahiaSpecialTransferArchiveError(
            "O recurso oficial não aparece uma única vez no catálogo."
        )
    resource = selected[0]
    size = resource.get("size")
    if (
        resource.get("name") != ARCHIVE_NAME
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
        raise BahiaSpecialTransferArchiveError(
            "Os metadados do recurso oficial estão incompletos."
        )
    _validate_exact_url(str(resource["url"]), expected_url=DOWNLOAD_URL)
    return {
        "dataset_id": DATASET_ID,
        "resource_id": RESOURCE_ID,
        "resource_name": ARCHIVE_NAME,
        "download_url": DOWNLOAD_URL,
        "byte_size": size,
        "last_modified": str(resource["last_modified"]),
        "dataset_modified": str(result["metadata_modified"]),
        "contains_restricted_identifier_column": True,
        "raw_access_scope": "private_workers_only",
    }


def _catalog_resource(
    catalog: BahiaSpecialTransferCatalogSnapshot,
) -> Mapping[str, object]:
    if (
        catalog.source_code != SOURCE_CODE
        or catalog.endpoint_code != ENDPOINT_CODE
        or catalog.schema_name != "bahia-special-transfer-catalog"
        or len(catalog.items) != 1
        or hashlib.sha256(catalog.raw_body).hexdigest() != catalog.body_sha256
    ):
        raise BahiaSpecialTransferArchiveError(
            "O catálogo preservado não corresponde ao contrato oficial."
        )
    resource = catalog.items[0]
    if (
        resource.get("resource_id") != RESOURCE_ID
        or resource.get("download_url") != DOWNLOAD_URL
    ):
        raise BahiaSpecialTransferArchiveError(
            "O catálogo preservado não referencia o recurso oficial."
        )
    return resource


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
            raise BahiaSpecialTransferArchiveError(
                "A resposta excedeu o tamanho oficial permitido."
            ) from error
        except RETRYABLE_TRANSPORT_EXCEPTIONS as error:
            breaker.record_failure()
            if attempt < policy.max_attempts:
                sleep(policy.delay(attempt, random_value()))
                continue
            raise BahiaSpecialTransferArchiveError(unavailable_message) from error
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
            raise BahiaSpecialTransferArchiveError(
                f"A fonte respondeu HTTP {response.status}."
            )
        breaker.record_failure()
        if attempt < policy.max_attempts:
            sleep(policy.delay(attempt, random_value()))
    raise BahiaSpecialTransferArchiveError(unavailable_message)


def _validate_exact_url(url: str, *, expected_url: str) -> None:
    try:
        validate_https_url(url, OFFICIAL_HOSTS)
    except ValueError as error:
        raise BahiaSpecialTransferArchiveError(
            "A fonte redirecionou para URL não oficial."
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
        raise BahiaSpecialTransferArchiveError(
            "A fonte redirecionou para URL não oficial."
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
