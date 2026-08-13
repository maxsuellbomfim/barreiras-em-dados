"""Parser estrito das emendas ligadas a propostas históricas de Barreiras."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import random
import time
import unicodedata
import zipfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
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

EXPECTED_MEMBER = "siconv_emenda.csv"
MAX_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
SOURCE_CODE = "transferegov-downloads"
ENDPOINT_CODE = "emendas-historicas"
DOWNLOAD_HOSTS = frozenset({"api-publica.transferegov.gestao.gov.br"})
BLOB_HOSTS = frozenset({"trsfgovprodstrgaccpublic.blob.core.windows.net"})
ARCHIVE_NAME = "siconv_emenda.zip"
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_PROPOSAL_SCOPE = 10_000
TIMEOUT_SECONDS = 180.0
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
SAFE_RESPONSE_HEADERS = frozenset(
    {"content-type", "content-length", "etag", "last-modified", "date"}
)

CSV_COLUMNS = (
    "ID_PROPOSTA",
    "QUALIF_PROPONENTE",
    "COD_PROGRAMA_EMENDA",
    "NR_EMENDA",
    "NOME_PARLAMENTAR",
    "BENEFICIARIO_EMENDA",
    "IND_IMPOSITIVO",
    "TIPO_PARLAMENTAR",
    "VALOR_REPASSE_PROPOSTA_EMENDA",
    "VALOR_REPASSE_EMENDA",
)


class HistoricalAmendmentArchiveError(RuntimeError):
    """O ZIP não permite fechar o recorte de emendas com segurança."""


@dataclass(frozen=True)
class HistoricalAmendmentSnapshot:
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
    catalog_blob_url: str
    catalog_etag: str
    catalog_last_modified: str
    proposal_ids: tuple[str, ...]


def fetch_historical_amendments(
    *,
    catalog_entry: Mapping[str, object],
    proposal_ids: Iterable[str],
    transport: HttpTransport | None = None,
    retry_policy: RetryPolicy | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    random_value: Callable[[], float] = random.random,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> HistoricalAmendmentSnapshot:
    """Baixa o ZIP oficial e seleciona somente propostas já comprovadas."""
    scope = _proposal_scope(proposal_ids)
    metadata = _catalog_metadata(catalog_entry)
    active_transport = transport or UrllibTransport(DOWNLOAD_HOSTS)
    policy = retry_policy or RetryPolicy(max_attempts=4)
    breaker = circuit_breaker or CircuitBreaker(failure_threshold=policy.max_attempts)
    log = logger or logging.getLogger(__name__)

    for attempt in range(1, policy.max_attempts + 1):
        breaker.before_request()
        requested_at = now().isoformat()
        try:
            response = active_transport.get(
                str(metadata["download_url"]),
                headers={
                    "Accept": "application/octet-stream",
                    "User-Agent": "Barreiras360-Collector/0.1",
                },
                timeout_seconds=TIMEOUT_SECONDS,
                max_body_bytes=int(metadata["byte_size"]),
            )
        except ResponseTooLargeError as error:
            breaker.record_failure()
            raise HistoricalAmendmentArchiveError(
                "O tamanho do ZIP excede o declarado no catálogo."
            ) from error
        except RETRYABLE_TRANSPORT_EXCEPTIONS as error:
            breaker.record_failure()
            if attempt < policy.max_attempts:
                sleep(policy.delay(attempt, random_value()))
                continue
            raise HistoricalAmendmentArchiveError(
                "O arquivo de emendas do Transferegov ficou indisponível."
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
            snapshot = _snapshot_from_response(
                response=response,
                metadata=metadata,
                requested_at=requested_at,
                received_at=received_at,
                attempts=attempt,
                proposal_ids=scope,
            )
            breaker.record_success()
            return snapshot
        if response.status not in RETRYABLE_HTTP_STATUSES:
            raise HistoricalAmendmentArchiveError(
                f"O arquivo de emendas respondeu HTTP {response.status}."
            )
        breaker.record_failure()
        if attempt < policy.max_attempts:
            sleep(policy.delay(attempt, random_value()))

    raise HistoricalAmendmentArchiveError(
        "O arquivo de emendas do Transferegov ficou indisponível."
    )


def parse_historical_amendments_archive(
    body: bytes,
    *,
    proposal_ids: Iterable[str],
) -> tuple[dict[str, object], ...]:
    """Filtra por identidade de proposta sem publicar o identificador beneficiário."""
    scope = frozenset(_proposal_scope(proposal_ids))
    try:
        package = zipfile.ZipFile(io.BytesIO(body))
    except (zipfile.BadZipFile, OSError) as error:
        raise HistoricalAmendmentArchiveError(
            "O arquivo de emendas não é um ZIP válido."
        ) from error

    with package:
        members = package.infolist()
        if len(members) != 1 or members[0].filename != EXPECTED_MEMBER:
            raise HistoricalAmendmentArchiveError(
                "O arquivo de emendas deve conter um único CSV contratado."
            )
        member = members[0]
        if (
            member.is_dir()
            or member.flag_bits & 0x1
            or member.file_size < 1
            or member.file_size > MAX_UNCOMPRESSED_BYTES
            or member.compress_size < 1
            or member.file_size > member.compress_size * MAX_COMPRESSION_RATIO
            or member.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
        ):
            raise HistoricalAmendmentArchiveError(
                "O membro do ZIP viola os limites de segurança."
            )
        try:
            with package.open(member) as binary:
                text = io.TextIOWrapper(
                    binary,
                    encoding="utf-8-sig",
                    errors="strict",
                    newline="",
                )
                reader = csv.reader(text, delimiter=";", strict=True)
                if tuple(next(reader)) != CSV_COLUMNS:
                    raise HistoricalAmendmentArchiveError(
                        "O cabeçalho do CSV de emendas diverge do contrato."
                    )
                selected = _selected_rows(reader, proposal_ids=scope)
        except HistoricalAmendmentArchiveError:
            raise
        except (UnicodeDecodeError, csv.Error, EOFError, RuntimeError) as error:
            raise HistoricalAmendmentArchiveError(
                "O conteúdo do ZIP de emendas está truncado ou inválido."
            ) from error
    return tuple(selected)


def _selected_rows(
    reader: csv.reader,
    *,
    proposal_ids: frozenset[str],
) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for line_number, values in enumerate(reader, start=2):
        if not values or all(not value.strip() for value in values):
            continue
        if len(values) != len(CSV_COLUMNS):
            raise HistoricalAmendmentArchiveError(
                f"A linha {line_number} não possui {len(CSV_COLUMNS)} colunas."
            )
        row = dict(zip(CSV_COLUMNS, values, strict=True))
        proposal_id = row["ID_PROPOSTA"].strip()
        if proposal_id not in proposal_ids:
            continue
        _require_digits(proposal_id, "ID_PROPOSTA", line_number)
        program_code = _required_text(
            row["COD_PROGRAMA_EMENDA"], "COD_PROGRAMA_EMENDA", line_number
        )
        amendment_number = _required_text(
            row["NR_EMENDA"], "NR_EMENDA", line_number
        )
        author_name = _required_text(
            row["NOME_PARLAMENTAR"], "NOME_PARLAMENTAR", line_number
        )
        identity = (
            proposal_id,
            program_code,
            amendment_number,
            _fold(author_name),
        )
        if identity in seen:
            raise HistoricalAmendmentArchiveError(
                f"A emenda da linha {line_number} possui identidade duplicada."
            )
        seen.add(identity)

        beneficiary = row["BENEFICIARIO_EMENDA"].strip()
        _require_digits(beneficiary, "BENEFICIARIO_EMENDA", line_number)
        if len(beneficiary) == 11:
            raise HistoricalAmendmentArchiveError(
                "CPF de beneficiário não será normalizado neste recorte."
            )
        if len(beneficiary) != 14:
            raise HistoricalAmendmentArchiveError(
                f"BENEFICIARIO_EMENDA inválido na linha {line_number}."
            )

        selected.append(
            {
                "id_proposta": proposal_id,
                "qualificacao_proponente": row["QUALIF_PROPONENTE"].strip(),
                "codigo_programa_emenda": program_code,
                "numero_emenda": amendment_number,
                "autor_nome": author_name,
                "beneficiario_tipo": "cnpj",
                "beneficiario_ultimos_4": beneficiary[-4:],
                "impositiva": _boolean(
                    row["IND_IMPOSITIVO"], "IND_IMPOSITIVO", line_number
                ),
                "tipo_parlamentar": _required_text(
                    row["TIPO_PARLAMENTAR"], "TIPO_PARLAMENTAR", line_number
                ),
                "valor_repasse_proposta_emenda": _decimal(
                    row["VALOR_REPASSE_PROPOSTA_EMENDA"],
                    "VALOR_REPASSE_PROPOSTA_EMENDA",
                    line_number,
                ),
                "valor_repasse_emenda": _decimal(
                    row["VALOR_REPASSE_EMENDA"],
                    "VALOR_REPASSE_EMENDA",
                    line_number,
                ),
            }
        )
    return selected


def _snapshot_from_response(
    *, response, metadata: Mapping[str, object], requested_at: str,
    received_at: str, attempts: int, proposal_ids: tuple[str, ...]
) -> HistoricalAmendmentSnapshot:
    try:
        validate_https_url(response.final_url, DOWNLOAD_HOSTS)
    except ValueError as error:
        raise HistoricalAmendmentArchiveError(
            "O download foi redirecionado para host não oficial."
        ) from error
    headers = {str(key).lower(): str(value) for key, value in response.headers.items()}
    expected_size = int(metadata["byte_size"])
    try:
        content_length = int(headers.get("content-length", ""))
    except ValueError as error:
        raise HistoricalAmendmentArchiveError(
            "O tamanho HTTP do ZIP é inválido."
        ) from error
    if len(response.body) != expected_size or content_length != expected_size:
        raise HistoricalAmendmentArchiveError(
            "O tamanho do ZIP diverge do catálogo oficial."
        )
    if headers.get("etag", "").strip('"') != str(metadata["etag"]).strip('"'):
        raise HistoricalAmendmentArchiveError(
            "O ETag do ZIP diverge do catálogo oficial."
        )
    media_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type not in {"application/octet-stream", "application/zip"}:
        raise HistoricalAmendmentArchiveError(
            "O tipo de conteúdo do ZIP não é permitido."
        )
    items = parse_historical_amendments_archive(
        response.body, proposal_ids=proposal_ids
    )
    body_sha256 = hashlib.sha256(response.body).hexdigest()
    scope_sha256 = hashlib.sha256("\n".join(proposal_ids).encode()).hexdigest()
    idempotency_key = hashlib.sha256(
        json.dumps(
            {"body_sha256": body_sha256, "proposal_scope_sha256": scope_sha256},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return HistoricalAmendmentSnapshot(
        schema_name="transferegov-historical-amendments-archive",
        schema_version="1.0.0",
        artifact_kind="archive",
        source_code=SOURCE_CODE,
        endpoint_code=ENDPOINT_CODE,
        idempotency_key=idempotency_key,
        request_url=str(metadata["download_url"]),
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
        media_type=media_type,
        response_headers={
            key: value for key, value in headers.items() if key in SAFE_RESPONSE_HEADERS
        },
        cursor={"offset": 0, "size": len(items), "proposal_scope": len(proposal_ids)},
        raw_body=response.body,
        items=items,
        total_pages=1,
        total_items=len(items),
        catalog_blob_url=str(metadata["blob_url"]),
        catalog_etag=str(metadata["etag"]),
        catalog_last_modified=str(metadata["last_modified"]),
        proposal_ids=proposal_ids,
    )


def _catalog_metadata(entry: Mapping[str, object]) -> dict[str, object]:
    name = entry.get("name")
    download_url = entry.get("download_url")
    blob_url = entry.get("url")
    etag = entry.get("etag")
    last_modified = entry.get("last_modified")
    byte_size = entry.get("byte_size")
    if (
        name != ARCHIVE_NAME
        or not isinstance(download_url, str)
        or not isinstance(blob_url, str)
        or not isinstance(etag, str)
        or not etag.strip()
        or not isinstance(last_modified, str)
        or not last_modified.strip()
        or not isinstance(byte_size, int)
        or isinstance(byte_size, bool)
        or not 1 <= byte_size <= MAX_ARCHIVE_BYTES
    ):
        raise HistoricalAmendmentArchiveError(
            "Os metadados do ZIP no catálogo estão incompletos."
        )
    try:
        validate_https_url(download_url, DOWNLOAD_HOSTS)
        validate_https_url(blob_url, BLOB_HOSTS)
    except ValueError as error:
        raise HistoricalAmendmentArchiveError(
            "A rota de download ou o blob catalogado não é oficial."
        ) from error
    parsed = urlparse(download_url)
    if (
        unquote(parsed.path) != f"/downloads/dadosgov/{ARCHIVE_NAME}"
        or parsed.query
        or parsed.fragment
    ):
        raise HistoricalAmendmentArchiveError(
            "A rota de download do ZIP não é oficial."
        )
    blob_path = urlparse(blob_url)
    if (
        unquote(blob_path.path)
        != f"/trsfgov-prod-public-data/{ARCHIVE_NAME}"
        or blob_path.query
        or blob_path.fragment
    ):
        raise HistoricalAmendmentArchiveError(
            "O blob catalogado do ZIP não é oficial."
        )
    return {
        "download_url": download_url,
        "blob_url": blob_url,
        "etag": etag.strip(),
        "last_modified": last_modified.strip(),
        "byte_size": byte_size,
    }


def _proposal_scope(values: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(sorted(set(values)))
    if not normalized or len(normalized) > MAX_PROPOSAL_SCOPE:
        raise ValueError("O recorte de propostas deve ser não vazio e limitado.")
    if any(not value.isascii() or not value.isdigit() for value in normalized):
        raise ValueError("O recorte contém identidade de proposta inválida.")
    return normalized


def _required_text(value: str, field: str, line_number: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise HistoricalAmendmentArchiveError(
            f"{field} vazio na linha {line_number}."
        )
    return normalized


def _require_digits(value: str, field: str, line_number: int) -> None:
    if not value or not value.isascii() or not value.isdigit():
        raise HistoricalAmendmentArchiveError(
            f"{field} inválido na linha {line_number}."
        )


def _decimal(value: str, field: str, line_number: int) -> str:
    normalized = value.strip()
    if normalized.count(",") == 1 and "." not in normalized:
        normalized = normalized.replace(",", ".")
    try:
        parsed = Decimal(normalized)
    except InvalidOperation as error:
        raise HistoricalAmendmentArchiveError(
            f"{field} inválido na linha {line_number}."
        ) from error
    if not parsed.is_finite() or parsed < 0:
        raise HistoricalAmendmentArchiveError(
            f"{field} inválido na linha {line_number}."
        )
    return format(parsed, "f")


def _boolean(value: str, field: str, line_number: int) -> bool:
    normalized = _fold(value)
    if normalized in {"sim", "s", "yes", "1"}:
        return True
    if normalized in {"nao", "n", "no", "0"}:
        return False
    raise HistoricalAmendmentArchiveError(
        f"{field} inválido na linha {line_number}."
    )


def _fold(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value.strip().casefold())
        if not unicodedata.combining(character)
    )
