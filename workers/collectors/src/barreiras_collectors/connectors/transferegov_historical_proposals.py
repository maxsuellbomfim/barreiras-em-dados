"""Parser estrito do arquivo histórico de propostas do Transferegov."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import random
import time
import zipfile
from collections.abc import Callable, Mapping
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

BARREIRAS_IBGE_CODE = "2903201"
EXPECTED_MEMBER = "siconv_proposta.csv"
MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
SOURCE_CODE = "transferegov-downloads"
ENDPOINT_CODE = "propostas-historicas"
DOWNLOAD_HOSTS = frozenset({"api-publica.transferegov.gestao.gov.br"})
DOWNLOAD_BASE_URL = (
    "https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/"
)
ARCHIVE_NAME = "siconv_proposta.zip"
MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
TIMEOUT_SECONDS = 300.0
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
SAFE_RESPONSE_HEADERS = frozenset(
    {"content-type", "content-length", "etag", "last-modified", "date"}
)

CSV_COLUMNS = (
    "ID_PROPOSTA",
    "UF_PROPONENTE",
    "MUNIC_PROPONENTE",
    "COD_MUNIC_IBGE",
    "COD_ORGAO_SUP",
    "DESC_ORGAO_SUP",
    "NATUREZA_JURIDICA",
    "NR_PROPOSTA",
    "DIA_PROP",
    "MES_PROP",
    "ANO_PROP",
    "DIA_PROPOSTA",
    "COD_ORGAO",
    "DESC_ORGAO",
    "MODALIDADE",
    "IDENTIF_PROPONENTE",
    "NM_PROPONENTE",
    "CEP_PROPONENTE",
    "ENDERECO_PROPONENTE",
    "BAIRRO_PROPONENTE",
    "NM_BANCO",
    "SITUACAO_CONTA",
    "SITUACAO_PROJETO_BASICO",
    "SIT_PROPOSTA",
    "DIA_INIC_VIGENCIA_PROPOSTA",
    "DIA_FIM_VIGENCIA_PROPOSTA",
    "OBJETO_PROPOSTA",
    "ITEM_INVESTIMENTO",
    "ENVIADA_MANDATARIA",
    "NOME_SUBTIPO_PROPOSTA",
    "DESCRICAO_SUBTIPO_PROPOSTA",
    "VL_GLOBAL_PROP",
    "VL_REPASSE_PROP",
    "VL_CONTRAPARTIDA_PROP",
    "CD_AGENCIA",
    "CD_CONTA",
)


class HistoricalProposalArchiveError(RuntimeError):
    """O ZIP existe, mas não permite fechar cobertura municipal confiável."""


@dataclass(frozen=True)
class HistoricalProposalSnapshot:
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
    year_from: int
    year_to: int


def fetch_historical_proposals(
    *,
    catalog_entry: Mapping[str, object],
    year_from: int,
    year_to: int,
    transport: HttpTransport | None = None,
    retry_policy: RetryPolicy | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    random_value: Callable[[], float] = random.random,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> HistoricalProposalSnapshot:
    """Baixa a rota proxy oficial e a vincula ao retrato do catálogo."""
    metadata = _catalog_metadata(catalog_entry)
    active_transport = transport or UrllibTransport(DOWNLOAD_HOSTS)
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
                metadata["download_url"],
                headers={
                    "Accept": "application/octet-stream",
                    "User-Agent": "Barreiras360-Collector/0.1",
                },
                timeout_seconds=TIMEOUT_SECONDS,
                max_body_bytes=metadata["byte_size"],
            )
        except ResponseTooLargeError as error:
            breaker.record_failure()
            raise HistoricalProposalArchiveError(
                "O tamanho do ZIP excede o declarado no catálogo."
            ) from error
        except RETRYABLE_TRANSPORT_EXCEPTIONS as error:
            breaker.record_failure()
            if attempt < policy.max_attempts:
                sleep(policy.delay(attempt, random_value()))
                continue
            raise HistoricalProposalArchiveError(
                "O arquivo histórico do Transferegov ficou indisponível."
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
                year_from=year_from,
                year_to=year_to,
            )
            breaker.record_success()
            return snapshot
        if response.status not in RETRYABLE_HTTP_STATUSES:
            raise HistoricalProposalArchiveError(
                f"O arquivo histórico respondeu HTTP {response.status}."
            )
        breaker.record_failure()
        if attempt < policy.max_attempts:
            sleep(policy.delay(attempt, random_value()))

    raise HistoricalProposalArchiveError(
        "O arquivo histórico do Transferegov ficou indisponível."
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
        raise HistoricalProposalArchiveError(
            "Os metadados do ZIP no catálogo estão incompletos."
        )
    try:
        validate_https_url(download_url, DOWNLOAD_HOSTS)
    except ValueError as error:
        raise HistoricalProposalArchiveError(
            "A rota de download do ZIP não é oficial."
        ) from error
    parsed = urlparse(download_url)
    if (
        unquote(parsed.path) != f"/downloads/dadosgov/{ARCHIVE_NAME}"
        or parsed.query
        or parsed.fragment
    ):
        raise HistoricalProposalArchiveError(
            "A rota de download do ZIP não é oficial."
        )
    return {
        "name": name,
        "download_url": download_url,
        "blob_url": blob_url,
        "etag": etag.strip(),
        "last_modified": last_modified.strip(),
        "byte_size": byte_size,
    }


def _snapshot_from_response(
    *,
    response,
    metadata: Mapping[str, object],
    requested_at: str,
    received_at: str,
    attempts: int,
    year_from: int,
    year_to: int,
) -> HistoricalProposalSnapshot:
    try:
        validate_https_url(response.final_url, DOWNLOAD_HOSTS)
    except ValueError as error:
        raise HistoricalProposalArchiveError(
            "O download foi redirecionado para host não oficial."
        ) from error
    headers = {str(key).lower(): str(value) for key, value in response.headers.items()}
    expected_size = int(metadata["byte_size"])
    try:
        content_length = int(headers.get("content-length", ""))
    except ValueError as error:
        raise HistoricalProposalArchiveError(
            "O tamanho HTTP do ZIP é inválido."
        ) from error
    if len(response.body) != expected_size or content_length != expected_size:
        raise HistoricalProposalArchiveError(
            "O tamanho do ZIP diverge do catálogo oficial."
        )
    if headers.get("etag", "").strip('"') != str(metadata["etag"]).strip('"'):
        raise HistoricalProposalArchiveError(
            "O ETag do ZIP diverge do catálogo oficial."
        )
    media_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type not in {"application/octet-stream", "application/zip"}:
        raise HistoricalProposalArchiveError(
            "O tipo de conteúdo do ZIP não é permitido."
        )
    items = parse_historical_proposals_archive(
        response.body,
        year_from=year_from,
        year_to=year_to,
    )
    body_sha256 = hashlib.sha256(response.body).hexdigest()
    idempotency_key = hashlib.sha256(
        json.dumps(
            {
                "body_sha256": body_sha256,
                "year_from": year_from,
                "year_to": year_to,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return HistoricalProposalSnapshot(
        schema_name="transferegov-historical-proposals-archive",
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
        cursor={
            "offset": 0,
            "size": len(items),
            "year_from": year_from,
            "year_to": year_to,
        },
        raw_body=response.body,
        items=items,
        total_pages=1,
        total_items=len(items),
        catalog_blob_url=str(metadata["blob_url"]),
        catalog_etag=str(metadata["etag"]),
        catalog_last_modified=str(metadata["last_modified"]),
        year_from=year_from,
        year_to=year_to,
    )


def parse_historical_proposals_archive(
    body: bytes,
    *,
    year_from: int,
    year_to: int,
) -> tuple[dict[str, object], ...]:
    """Seleciona propostas de Barreiras sem projetar dados bancários."""
    if year_from < 2008 or year_to < year_from:
        raise ValueError("O período histórico solicitado é inválido.")
    try:
        package = zipfile.ZipFile(io.BytesIO(body))
    except (zipfile.BadZipFile, OSError) as error:
        raise HistoricalProposalArchiveError(
            "O arquivo histórico não é um ZIP válido."
        ) from error

    with package:
        members = package.infolist()
        if len(members) != 1 or members[0].filename != EXPECTED_MEMBER:
            raise HistoricalProposalArchiveError(
                "O arquivo histórico deve conter um único CSV contratado."
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
            raise HistoricalProposalArchiveError(
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
                header = tuple(next(reader))
                if header != CSV_COLUMNS:
                    raise HistoricalProposalArchiveError(
                        "O cabeçalho do CSV histórico diverge do contrato."
                    )
                selected = _selected_rows(
                    reader,
                    year_from=year_from,
                    year_to=year_to,
                )
        except HistoricalProposalArchiveError:
            raise
        except (UnicodeDecodeError, csv.Error, EOFError, RuntimeError) as error:
            raise HistoricalProposalArchiveError(
                "O conteúdo do ZIP histórico está truncado ou inválido."
            ) from error
    return tuple(selected)


def _selected_rows(
    reader: csv.reader,
    *,
    year_from: int,
    year_to: int,
) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for line_number, values in enumerate(reader, start=2):
        if not values or all(not value.strip() for value in values):
            continue
        if len(values) != len(CSV_COLUMNS):
            raise HistoricalProposalArchiveError(
                f"A linha {line_number} não possui {len(CSV_COLUMNS)} colunas."
            )
        row = dict(zip(CSV_COLUMNS, values, strict=True))
        if row["COD_MUNIC_IBGE"].strip() != BARREIRAS_IBGE_CODE:
            continue
        year = _year(row["ANO_PROP"], line_number)
        if year < year_from or year > year_to:
            continue
        if row["MUNIC_PROPONENTE"].strip().casefold() != "barreiras":
            raise HistoricalProposalArchiveError(
                "O código IBGE de Barreiras diverge do município informado."
            )
        proposal_id = _digits(row["ID_PROPOSTA"], "ID_PROPOSTA", line_number)
        if proposal_id in seen_ids:
            raise HistoricalProposalArchiveError(
                f"A proposta {proposal_id} apareceu mais de uma vez no arquivo."
            )
        seen_ids.add(proposal_id)
        proponent = _digits(
            row["IDENTIF_PROPONENTE"],
            "IDENTIF_PROPONENTE",
            line_number,
        )
        if len(proponent) != 14:
            raise HistoricalProposalArchiveError(
                "A projeção municipal aceita somente CNPJ de proponente; CPF não "
                "será normalizado."
            )
        selected.append(
            {
                "id_proposta": proposal_id,
                "uf_proponente": row["UF_PROPONENTE"].strip(),
                "municipio_proponente": row["MUNIC_PROPONENTE"].strip(),
                "cod_municipio_ibge": BARREIRAS_IBGE_CODE,
                "cod_orgao_superior": row["COD_ORGAO_SUP"].strip(),
                "orgao_superior": row["DESC_ORGAO_SUP"].strip(),
                "natureza_juridica": row["NATUREZA_JURIDICA"].strip(),
                "numero_proposta": row["NR_PROPOSTA"].strip(),
                "ano_proposta": year,
                "data_proposta": row["DIA_PROPOSTA"].strip(),
                "cod_orgao": row["COD_ORGAO"].strip(),
                "orgao": row["DESC_ORGAO"].strip(),
                "modalidade": row["MODALIDADE"].strip(),
                "proponente_cnpj": proponent,
                "proponente": row["NM_PROPONENTE"].strip(),
                "situacao_projeto_basico": row[
                    "SITUACAO_PROJETO_BASICO"
                ].strip(),
                "situacao_proposta": row["SIT_PROPOSTA"].strip(),
                "inicio_vigencia": row["DIA_INIC_VIGENCIA_PROPOSTA"].strip(),
                "fim_vigencia": row["DIA_FIM_VIGENCIA_PROPOSTA"].strip(),
                "objeto": row["OBJETO_PROPOSTA"].strip(),
                "item_investimento": row["ITEM_INVESTIMENTO"].strip(),
                "enviada_mandataria": row["ENVIADA_MANDATARIA"].strip(),
                "subtipo": row["NOME_SUBTIPO_PROPOSTA"].strip(),
                "descricao_subtipo": row[
                    "DESCRICAO_SUBTIPO_PROPOSTA"
                ].strip(),
                "valor_global": _decimal(
                    row["VL_GLOBAL_PROP"], "VL_GLOBAL_PROP", line_number
                ),
                "valor_repasse": _decimal(
                    row["VL_REPASSE_PROP"], "VL_REPASSE_PROP", line_number
                ),
                "valor_contrapartida": _decimal(
                    row["VL_CONTRAPARTIDA_PROP"],
                    "VL_CONTRAPARTIDA_PROP",
                    line_number,
                ),
            }
        )
    return selected


def _year(value: str, line_number: int) -> int:
    digits = _digits(value, "ANO_PROP", line_number)
    year = int(digits)
    if not 2008 <= year <= 2100:
        raise HistoricalProposalArchiveError(
            f"ANO_PROP inválido na linha {line_number}."
        )
    return year


def _digits(value: str, field: str, line_number: int) -> str:
    normalized = value.strip()
    if not normalized or not normalized.isascii() or not normalized.isdigit():
        raise HistoricalProposalArchiveError(
            f"{field} inválido na linha {line_number}."
        )
    return normalized


def _decimal(value: str, field: str, line_number: int) -> str:
    normalized = value.strip()
    if normalized.count(",") == 1 and "." not in normalized:
        normalized = normalized.replace(",", ".")
    try:
        parsed = Decimal(normalized)
    except InvalidOperation as error:
        raise HistoricalProposalArchiveError(
            f"{field} inválido na linha {line_number}."
        ) from error
    if not parsed.is_finite() or parsed < 0:
        raise HistoricalProposalArchiveError(
            f"{field} inválido na linha {line_number}."
        )
    return format(parsed, "f")
