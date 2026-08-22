"""Execução federal de emendas regionalizadas oficialmente para Barreiras."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import random
import re
import time
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from ..http import (
    RETRYABLE_TRANSPORT_EXCEPTIONS,
    HttpResponse,
    HttpTransport,
    ResponseTooLargeError,
    UrllibTransport,
    validate_https_url,
)
from ..logging import log_event
from ..resilience import CircuitBreaker, RetryPolicy

SOURCE_CODE = "cgu-portal-transparencia"
ENDPOINT_CODE = "federal-amendments-open-data"
MUNICIPALITY_IBGE = "2903201"
DOWNLOAD_URL = (
    "https://portaldatransparencia.gov.br/"
    "download-de-dados/emendas-parlamentares/UNICO"
)
FINAL_ARCHIVE_PATH = (
    "/PortalDaTransparencia/saida/emendas-parlamentares/"
    "EmendasParlamentares.zip"
)
OFFICIAL_HOSTS = frozenset(
    {"portaldatransparencia.gov.br", "dadosabertos-download.cgu.gov.br"}
)
MAX_ARCHIVE_BYTES = 48 * 1024 * 1024
MAX_MEMBER_BYTES = 256 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
TIMEOUT_SECONDS = 180.0
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
SAFE_RESPONSE_HEADERS = frozenset(
    {"content-type", "content-length", "etag", "last-modified", "date"}
)
EXPECTED_MEMBERS = frozenset(
    {
        "EmendasParlamentares.csv",
        "EmendasParlamentares_Convenios.csv",
        "EmendasParlamentares_PorFavorecido.csv",
    }
)

MAIN_COLUMNS = (
    "Código da Emenda",
    "Ano da Emenda",
    "Tipo de Emenda",
    "Código do Autor da Emenda",
    "Nome do Autor da Emenda",
    "Número da emenda",
    "Localidade de aplicação do recurso",
    "Código Município IBGE",
    "Município",
    "Código UF IBGE",
    "UF",
    "Região",
    "Código Função",
    "Nome Função",
    "Código Subfunção",
    "Nome Subfunção",
    "Código Programa",
    "Nome Programa",
    "Código Ação",
    "Nome Ação",
    "Código Plano Orçamentário",
    "Nome Plano Orçamentário",
    "Valor Empenhado",
    "Valor Liquidado",
    "Valor Pago",
    "Valor Restos A Pagar Inscritos",
    "Valor Restos A Pagar Cancelados",
    "Valor Restos A Pagar Pagos",
)
MAIN_COLUMNS_WITH_SUPPORTER = (
    *MAIN_COLUMNS[:6],
    "Possui Apoiador/Solicitante? ",
    *MAIN_COLUMNS[6:],
)
CONVENIO_COLUMNS = (
    "Código da Emenda",
    "Código Função",
    "Nome Função",
    "Código Subfunção",
    "Nome Subfunção",
    "Localidade do gasto",
    "Tipo de Emenda",
    "Data Publicação Convênio",
    "Convenente",
    "Objeto Convênio",
    "Número Convênio",
    "Valor Convênio",
)
FAVORECIDO_COLUMNS = (
    "Código da Emenda",
    "Código do Autor da Emenda",
    "Nome do Autor da Emenda",
    "Número da emenda",
    "Tipo de Emenda",
    "Ano/Mês",
    "Código do Favorecido",
    "Favorecido",
    "Natureza Jurídica",
    "Tipo Favorecido",
    "UF Favorecido",
    "Município Favorecido",
    "Valor Recebido",
)
EXPECTED_COLUMNS = {
    "EmendasParlamentares.csv": (MAIN_COLUMNS, MAIN_COLUMNS_WITH_SUPPORTER),
    "EmendasParlamentares_Convenios.csv": (CONVENIO_COLUMNS,),
    "EmendasParlamentares_PorFavorecido.csv": (FAVORECIDO_COLUMNS,),
}
_DECIMAL = re.compile(r"^-?\d+(?:,\d{1,2})?$")


class CGUFederalAmendmentArchiveError(RuntimeError):
    """O arquivo da CGU não permite fechar o recorte com segurança."""


@dataclass(frozen=True)
class CGUFederalAmendmentSnapshot:
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
    first_fiscal_year: int
    last_fiscal_year: int
    source_last_modified: str
    source_etag: str


def fetch_cgu_federal_amendments(
    *,
    transport: HttpTransport | None = None,
    retry_policy: RetryPolicy | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    random_value: Callable[[], float] = random.random,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> CGUFederalAmendmentSnapshot:
    """Baixa o retrato nacional e recorta apenas o IBGE oficial de Barreiras."""
    active_transport = transport or UrllibTransport(OFFICIAL_HOSTS)
    policy = retry_policy or RetryPolicy(max_attempts=4)
    breaker = circuit_breaker or CircuitBreaker(failure_threshold=policy.max_attempts)
    log = logger or logging.getLogger(__name__)

    for attempt in range(1, policy.max_attempts + 1):
        breaker.before_request()
        requested_at = now().isoformat()
        try:
            response = active_transport.get(
                DOWNLOAD_URL,
                headers={
                    "Accept": "application/zip, application/octet-stream",
                    "User-Agent": "Barreiras360-Collector/0.1",
                },
                timeout_seconds=TIMEOUT_SECONDS,
                max_body_bytes=MAX_ARCHIVE_BYTES,
            )
        except ResponseTooLargeError as error:
            breaker.record_failure()
            raise CGUFederalAmendmentArchiveError(
                "O ZIP federal excede o limite operacional permitido."
            ) from error
        except RETRYABLE_TRANSPORT_EXCEPTIONS as error:
            breaker.record_failure()
            if attempt < policy.max_attempts:
                sleep(policy.delay(attempt, random_value()))
                continue
            raise CGUFederalAmendmentArchiveError(
                "O arquivo federal de emendas ficou indisponível."
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
                response,
                requested_at=requested_at,
                received_at=received_at,
                attempts=attempt,
            )
            breaker.record_success()
            return snapshot
        if response.status not in RETRYABLE_HTTP_STATUSES:
            raise CGUFederalAmendmentArchiveError(
                f"O arquivo federal respondeu HTTP {response.status}."
            )
        breaker.record_failure()
        if attempt < policy.max_attempts:
            sleep(policy.delay(attempt, random_value()))

    raise CGUFederalAmendmentArchiveError(
        "O arquivo federal de emendas ficou indisponível."
    )


def parse_cgu_federal_amendments_archive(
    body: bytes,
    *,
    municipality_ibge: str = MUNICIPALITY_IBGE,
) -> tuple[dict[str, object], ...]:
    """Valida o ZIP inteiro e normaliza o recorte territorial sem ``float``."""
    if not re.fullmatch(r"\d{7}", municipality_ibge):
        raise ValueError("Código IBGE municipal inválido.")
    try:
        package = zipfile.ZipFile(io.BytesIO(body))
    except (zipfile.BadZipFile, OSError) as error:
        raise CGUFederalAmendmentArchiveError(
            "O arquivo federal não é um ZIP válido."
        ) from error

    selected: list[dict[str, object]] = []
    identities: set[tuple[str, ...]] = set()
    with package:
        members = package.infolist()
        names = {member.filename for member in members}
        if len(names) != len(members) or names != EXPECTED_MEMBERS:
            raise CGUFederalAmendmentArchiveError(
                "O ZIP federal não contém exatamente os três CSVs contratados."
            )
        total_uncompressed = sum(member.file_size for member in members)
        if not 1 <= total_uncompressed <= MAX_UNCOMPRESSED_BYTES:
            raise CGUFederalAmendmentArchiveError(
                "O tamanho descompactado do ZIP federal viola o limite."
            )
        for member in members:
            _validate_member(member)
            try:
                with package.open(member) as stream:
                    reader = csv.reader(
                        io.TextIOWrapper(stream, encoding="cp1252", newline=""),
                        delimiter=";",
                        strict=True,
                    )
                    header = tuple(next(reader))
                    if header not in EXPECTED_COLUMNS[member.filename]:
                        raise CGUFederalAmendmentArchiveError(
                            f"O cabeçalho de {member.filename} diverge do contrato."
                        )
                    if member.filename != "EmendasParlamentares.csv":
                        continue
                    municipality_index = header.index("Código Município IBGE")
                    for source_row_number, row in enumerate(reader, start=2):
                        if not row or all(not value.strip() for value in row):
                            continue
                        if len(row) != len(header):
                            raise CGUFederalAmendmentArchiveError(
                                "Uma linha do arquivo federal diverge do cabeçalho."
                            )
                        if row[municipality_index].strip() != municipality_ibge:
                            continue
                        normalized = _normalize_row(
                            row,
                            header=header,
                            source_row_number=source_row_number,
                        )
                        identity = _natural_identity(normalized)
                        if identity in identities:
                            raise CGUFederalAmendmentArchiveError(
                                "A fonte publicou uma identidade territorial duplicada."
                            )
                        identities.add(identity)
                        selected.append(normalized)
            except (UnicodeDecodeError, csv.Error, StopIteration) as error:
                raise CGUFederalAmendmentArchiveError(
                    f"O CSV {member.filename} não pôde ser validado."
                ) from error
    return tuple(selected)


def _snapshot_from_response(
    response: HttpResponse,
    *,
    requested_at: str,
    received_at: str,
    attempts: int,
) -> CGUFederalAmendmentSnapshot:
    validate_https_url(response.final_url, OFFICIAL_HOSTS)
    parsed_final = urlparse(response.final_url)
    if (
        (parsed_final.hostname or "").lower().rstrip(".")
        != "dadosabertos-download.cgu.gov.br"
        or parsed_final.path != FINAL_ARCHIVE_PATH
        or parsed_final.query
        or parsed_final.fragment
    ):
        raise CGUFederalAmendmentArchiveError(
            "O redirecionamento do ZIP federal saiu do caminho oficial."
        )
    headers = _normalized_headers(response.headers)
    media_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type not in {
        "application/zip",
        "application/octet-stream",
        "application/x-zip-compressed",
    }:
        raise CGUFederalAmendmentArchiveError(
            "O tipo de conteúdo do ZIP federal não é permitido."
        )
    content_length = headers.get("content-length")
    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError as error:
            raise CGUFederalAmendmentArchiveError(
                "O Content-Length do ZIP federal é inválido."
            ) from error
        if declared_size != len(response.body):
            raise CGUFederalAmendmentArchiveError(
                "O tamanho HTTP do ZIP federal diverge dos bytes recebidos."
            )
    source_etag = headers.get("etag", "").strip()
    source_last_modified = headers.get("last-modified", "").strip()
    if not source_etag or not source_last_modified:
        raise CGUFederalAmendmentArchiveError(
            "O ZIP federal não publicou ETag e Last-Modified verificáveis."
        )
    items = parse_cgu_federal_amendments_archive(response.body)
    years = [int(item["fiscal_year"]) for item in items]
    if not years:
        raise CGUFederalAmendmentArchiveError(
            "O retrato federal validado não publicou linhas para Barreiras."
        )
    body_sha256 = hashlib.sha256(response.body).hexdigest()
    first_year = min(years)
    last_year = max(years)
    idempotency_key = hashlib.sha256(
        json.dumps(
            {
                "archive_sha256": body_sha256,
                "etag": source_etag,
                "municipality_ibge": MUNICIPALITY_IBGE,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return CGUFederalAmendmentSnapshot(
        schema_name="cgu-federal-amendment-execution",
        schema_version="1.0.0",
        artifact_kind="archive",
        source_code=SOURCE_CODE,
        endpoint_code=ENDPOINT_CODE,
        idempotency_key=idempotency_key,
        request_url=DOWNLOAD_URL,
        final_url=response.final_url,
        requested_at=requested_at,
        received_at=received_at,
        window_start=f"{first_year}-01-01",
        window_end=f"{last_year}-12-31",
        attempts=attempts,
        http_status=200,
        collection_status="success",
        body_sha256=body_sha256,
        body_size_bytes=len(response.body),
        media_type=media_type,
        response_headers=_safe_headers(response.headers),
        cursor={"offset": 0, "size": len(items)},
        raw_body=response.body,
        items=items,
        total_pages=1,
        total_items=len(items),
        first_fiscal_year=first_year,
        last_fiscal_year=last_year,
        source_last_modified=source_last_modified,
        source_etag=source_etag,
    )


def _validate_member(member: zipfile.ZipInfo) -> None:
    if (
        member.is_dir()
        or member.flag_bits & 0x1
        or member.file_size < 1
        or member.file_size > MAX_MEMBER_BYTES
        or member.compress_size < 1
        or member.file_size > member.compress_size * MAX_COMPRESSION_RATIO
        or member.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
    ):
        raise CGUFederalAmendmentArchiveError(
            f"O membro {member.filename} viola os limites de segurança."
        )


def _normalize_row(
    row: list[str],
    *,
    header: tuple[str, ...],
    source_row_number: int,
) -> dict[str, object]:
    source = dict(zip(header, row, strict=True))
    try:
        fiscal_year = int(source["Ano da Emenda"].strip())
    except ValueError as error:
        raise CGUFederalAmendmentArchiveError(
            "O ano de uma emenda federal é inválido."
        ) from error
    if not 2000 <= fiscal_year <= 2100:
        raise CGUFederalAmendmentArchiveError(
            "O ano de uma emenda federal está fora do intervalo aceito."
        )
    required_text = {
        "amendment_code": source["Código da Emenda"],
        "amendment_type": source["Tipo de Emenda"],
        "author_code": source["Código do Autor da Emenda"],
        "author_name": source["Nome do Autor da Emenda"],
        "amendment_number": source["Número da emenda"],
        "locality": source["Localidade de aplicação do recurso"],
        "municipality_ibge": source["Código Município IBGE"],
        "municipality_name": source["Município"],
        "state_ibge": source["Código UF IBGE"],
        "state_name": source["UF"],
        "region_name": source["Região"],
        "function_code": source["Código Função"],
        "function_name": source["Nome Função"],
        "subfunction_code": source["Código Subfunção"],
        "subfunction_name": source["Nome Subfunção"],
        "program_code": source["Código Programa"],
        "program_name": source["Nome Programa"],
        "action_code": source["Código Ação"],
        "action_name": source["Nome Ação"],
        "budget_plan_code": source["Código Plano Orçamentário"],
        "budget_plan_name": source["Nome Plano Orçamentário"],
    }
    normalized_text: dict[str, object] = {}
    for name, value in required_text.items():
        stripped = value.strip()
        if not stripped or len(stripped) > 4000:
            raise CGUFederalAmendmentArchiveError(
                f"O campo {name} de uma emenda federal é inválido."
            )
        normalized_text[name] = stripped
    amounts = {
        "committed_amount": source["Valor Empenhado"],
        "liquidated_amount": source["Valor Liquidado"],
        "paid_amount": source["Valor Pago"],
        "outstanding_registered_amount": source[
            "Valor Restos A Pagar Inscritos"
        ],
        "outstanding_cancelled_amount": source[
            "Valor Restos A Pagar Cancelados"
        ],
        "outstanding_paid_amount": source["Valor Restos A Pagar Pagos"],
    }
    return {
        **normalized_text,
        "fiscal_year": fiscal_year,
        **{name: _decimal(value, name=name) for name, value in amounts.items()},
        "source_row_number": source_row_number,
    }


def _decimal(value: str, *, name: str) -> str:
    stripped = value.strip()
    if not _DECIMAL.fullmatch(stripped):
        raise CGUFederalAmendmentArchiveError(
            f"O campo monetário {name} é inválido."
        )
    try:
        parsed = Decimal(stripped.replace(",", "."))
    except InvalidOperation as error:
        raise CGUFederalAmendmentArchiveError(
            f"O campo monetário {name} é inválido."
        ) from error
    return format(parsed, "f")


def _natural_identity(item: Mapping[str, object]) -> tuple[str, ...]:
    return tuple(
        str(item[name])
        for name in (
            "fiscal_year",
            "amendment_code",
            "municipality_ibge",
            "function_code",
            "subfunction_code",
            "program_code",
            "action_code",
            "budget_plan_code",
        )
    )


def _normalized_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in headers.items()}


def _safe_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in _normalized_headers(headers).items()
        if key in SAFE_RESPONSE_HEADERS
    }
