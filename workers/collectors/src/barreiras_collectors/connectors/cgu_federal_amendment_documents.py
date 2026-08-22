"""Documentos anuais da execução federal de emendas em Barreiras."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import random
import re
import time
import unicodedata
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
ENDPOINT_CODE = "federal-amendment-documents-open-data"
MUNICIPALITY_IBGE = "2903201"
DOWNLOAD_URL_TEMPLATE = (
    "https://portaldatransparencia.gov.br/download-de-dados/"
    "emendas-parlamentares-documentos/{year}"
)
FINAL_ARCHIVE_PATH_TEMPLATE = (
    "/PortalDaTransparencia/saida/emendas-parlamentares-documentos/"
    "{year}_EmendasParlamentaresPorDocumento.zip"
)
OFFICIAL_HOSTS = frozenset(
    {"portaldatransparencia.gov.br", "dadosabertos-download.cgu.gov.br"}
)
MAX_ARCHIVE_BYTES = 48 * 1024 * 1024
MAX_MEMBER_BYTES = 768 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
TIMEOUT_SECONDS = 180.0
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
SAFE_RESPONSE_HEADERS = frozenset(
    {"content-type", "content-length", "etag", "last-modified", "date"}
)

DOCUMENT_COLUMNS = (
    "Código da Emenda",
    "Ano da Emenda",
    "Código do Autor da Emenda",
    "Nome do Autor da Emenda",
    "Número da emenda",
    "Valor Empenhado",
    "Valor Pago",
    "Tipo de Emenda",
    "Data Documento",
    "Código Documento",
    "Localidade de aplicação do recurso",
    "UF de aplicação do recurso",
    "Município de aplicação do recurso",
    "Código IBGE do município de aplicação do recurso",
    "Fase da despesa",
    "Código favorecido",
    "Favorecido",
    "Tipo Favorecido",
    "UF Favorecido",
    "Município Favorecido",
    "Código UG",
    "UG",
    "Código Unidade Orçamentária",
    "Unidade Orçamentária",
    "Código Órgão SIAFI",
    "Órgão",
    "Código Órgão Superior SIAFI",
    "Órgão Superior",
    "Código Grupo Despesa",
    "Grupo Despesa",
    "Código Elemento Despesa",
    "Elemento Despesa",
    "Código Modalidade Aplicação Despesa",
    "Modalidade Aplicação Despesa",
    "Código Plano Orçamentário",
    "Plano Orçamentário",
    "Código Função",
    "Função",
    "Código SubFunção",
    "SubFunção",
    "Código Programa",
    "Programa",
    "Código Ação",
    "Ação",
    "Linguagem Cidadã",
    "Código Subtítulo (Localizador)",
    "Subtítulo (Localizador)",
    "Possui convênio?",
)
DOCUMENT_COLUMNS_WITH_SUPPORTER = (
    *DOCUMENT_COLUMNS[:5],
    "Possui Apoiador/Solicitante?",
    *DOCUMENT_COLUMNS[5:],
)
DOCUMENT_COLUMN_VARIANTS = (
    DOCUMENT_COLUMNS,
    DOCUMENT_COLUMNS_WITH_SUPPORTER,
)
_DECIMAL = re.compile(r"^-?\d+(?:,\d{1,2})?$")
_DOCUMENT_DATE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_STAGES = {
    "empenho": "commitment",
    "liquidacao": "liquidation",
    "pagamento": "payment",
}


class CGUFederalAmendmentDocumentArchiveError(RuntimeError):
    """O arquivo anual não permite fechar o recorte com segurança."""


@dataclass(frozen=True)
class CGUFederalAmendmentDocumentSnapshot:
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
    archive_year: int
    source_last_modified: str
    source_etag: str


def fetch_cgu_federal_amendment_documents(
    archive_year: int,
    *,
    transport: HttpTransport | None = None,
    retry_policy: RetryPolicy | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    random_value: Callable[[], float] = random.random,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> CGUFederalAmendmentDocumentSnapshot:
    """Baixa um ano documental oficial e recorta o IBGE de Barreiras."""
    _validate_year(archive_year)
    request_url = DOWNLOAD_URL_TEMPLATE.format(year=archive_year)
    active_transport = transport or UrllibTransport(OFFICIAL_HOSTS)
    policy = retry_policy or RetryPolicy(max_attempts=4)
    breaker = circuit_breaker or CircuitBreaker(failure_threshold=policy.max_attempts)
    log = logger or logging.getLogger(__name__)

    for attempt in range(1, policy.max_attempts + 1):
        breaker.before_request()
        requested_at = now().isoformat()
        try:
            response = active_transport.get(
                request_url,
                headers={
                    "Accept": "application/zip, application/octet-stream",
                    "User-Agent": "Barreiras360-Collector/0.1",
                },
                timeout_seconds=TIMEOUT_SECONDS,
                max_body_bytes=MAX_ARCHIVE_BYTES,
            )
        except ResponseTooLargeError as error:
            breaker.record_failure()
            raise CGUFederalAmendmentDocumentArchiveError(
                "O ZIP anual de documentos excede o limite permitido."
            ) from error
        except RETRYABLE_TRANSPORT_EXCEPTIONS as error:
            breaker.record_failure()
            if attempt < policy.max_attempts:
                sleep(policy.delay(attempt, random_value()))
                continue
            raise CGUFederalAmendmentDocumentArchiveError(
                "O arquivo anual de documentos ficou indisponível."
            ) from error

        received_at = now().isoformat()
        log_event(
            log,
            logging.INFO,
            "collector_http_response",
            source=SOURCE_CODE,
            endpoint=ENDPOINT_CODE,
            archive_year=archive_year,
            status=response.status,
            attempt=attempt,
            body_size_bytes=len(response.body),
        )
        if response.status == 200:
            snapshot = _snapshot_from_response(
                response,
                archive_year=archive_year,
                request_url=request_url,
                requested_at=requested_at,
                received_at=received_at,
                attempts=attempt,
            )
            breaker.record_success()
            return snapshot
        if response.status not in RETRYABLE_HTTP_STATUSES:
            raise CGUFederalAmendmentDocumentArchiveError(
                f"O arquivo anual respondeu HTTP {response.status}."
            )
        breaker.record_failure()
        if attempt < policy.max_attempts:
            sleep(policy.delay(attempt, random_value()))

    raise CGUFederalAmendmentDocumentArchiveError(
        "O arquivo anual de documentos ficou indisponível."
    )


def parse_cgu_federal_amendment_documents_archive(
    body: bytes,
    *,
    archive_year: int,
    municipality_ibge: str = MUNICIPALITY_IBGE,
) -> tuple[dict[str, object], ...]:
    """Valida o CSV anual e preserva cada documento financeiro separadamente."""
    _validate_year(archive_year)
    if not re.fullmatch(r"\d{7}", municipality_ibge):
        raise ValueError("Código IBGE municipal inválido.")
    try:
        package = zipfile.ZipFile(io.BytesIO(body))
    except (zipfile.BadZipFile, OSError) as error:
        raise CGUFederalAmendmentDocumentArchiveError(
            "O arquivo anual não é um ZIP válido."
        ) from error

    expected_member = f"{archive_year}_EmendasParlamentares_PorDocumento.csv"
    selected: list[dict[str, object]] = []
    identities: set[tuple[str, ...]] = set()
    with package:
        members = package.infolist()
        if len(members) != 1 or members[0].filename != expected_member:
            raise CGUFederalAmendmentDocumentArchiveError(
                "O ZIP não corresponde ao ano solicitado."
            )
        member = members[0]
        _validate_member(member)
        try:
            with package.open(member) as stream:
                reader = csv.reader(
                    io.TextIOWrapper(stream, encoding="cp1252", newline=""),
                    delimiter=";",
                    strict=True,
                )
                header = tuple(next(reader))
                if header not in DOCUMENT_COLUMN_VARIANTS:
                    raise CGUFederalAmendmentDocumentArchiveError(
                        "O cabeçalho documental diverge do contrato."
                    )
                municipality_index = header.index(
                    "Código IBGE do município de aplicação do recurso"
                )
                for source_row_number, row in enumerate(reader, start=2):
                    if not row or all(not value.strip() for value in row):
                        continue
                    if len(row) != len(header):
                        raise CGUFederalAmendmentDocumentArchiveError(
                            "Uma linha documental diverge do cabeçalho."
                        )
                    if row[municipality_index].strip() != municipality_ibge:
                        continue
                    normalized = _normalize_row(
                        row,
                        header=header,
                        archive_year=archive_year,
                        source_row_number=source_row_number,
                    )
                    identity = _natural_identity(normalized)
                    if identity in identities:
                        # A CGU pode repetir literalmente uma linha sem valor
                        # adicional (observado em liquidações). Uma cópia
                        # idêntica não vira um segundo fato financeiro.
                        continue
                    identities.add(identity)
                    selected.append(normalized)
        except (UnicodeDecodeError, csv.Error, StopIteration) as error:
            raise CGUFederalAmendmentDocumentArchiveError(
                "O CSV documental não pôde ser validado."
            ) from error
    return tuple(selected)


def _snapshot_from_response(
    response: HttpResponse,
    *,
    archive_year: int,
    request_url: str,
    requested_at: str,
    received_at: str,
    attempts: int,
) -> CGUFederalAmendmentDocumentSnapshot:
    validate_https_url(response.final_url, OFFICIAL_HOSTS)
    parsed_final = urlparse(response.final_url)
    expected_path = FINAL_ARCHIVE_PATH_TEMPLATE.format(year=archive_year)
    if (
        (parsed_final.hostname or "").lower().rstrip(".")
        != "dadosabertos-download.cgu.gov.br"
        or parsed_final.path != expected_path
        or parsed_final.query
        or parsed_final.fragment
    ):
        raise CGUFederalAmendmentDocumentArchiveError(
            "O redirecionamento do ZIP anual saiu do caminho oficial."
        )
    headers = _normalized_headers(response.headers)
    media_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type not in {
        "application/zip",
        "application/octet-stream",
        "application/x-zip-compressed",
    }:
        raise CGUFederalAmendmentDocumentArchiveError(
            "O tipo de conteúdo do ZIP anual não é permitido."
        )
    declared_length = headers.get("content-length")
    if declared_length is not None:
        try:
            if int(declared_length) != len(response.body):
                raise ValueError
        except ValueError as error:
            raise CGUFederalAmendmentDocumentArchiveError(
                "O tamanho HTTP do ZIP anual diverge dos bytes recebidos."
            ) from error
    source_etag = headers.get("etag", "").strip()
    source_last_modified = headers.get("last-modified", "").strip()
    if not source_etag or not source_last_modified:
        raise CGUFederalAmendmentDocumentArchiveError(
            "O ZIP anual não publicou ETag e Last-Modified verificáveis."
        )
    items = parse_cgu_federal_amendment_documents_archive(
        response.body,
        archive_year=archive_year,
    )
    body_sha256 = hashlib.sha256(response.body).hexdigest()
    idempotency_key = hashlib.sha256(
        json.dumps(
            {
                "archive_sha256": body_sha256,
                "archive_year": archive_year,
                "etag": source_etag,
                "municipality_ibge": MUNICIPALITY_IBGE,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return CGUFederalAmendmentDocumentSnapshot(
        schema_name="cgu-federal-amendment-document",
        schema_version="1.0.0",
        artifact_kind="archive",
        source_code=SOURCE_CODE,
        endpoint_code=ENDPOINT_CODE,
        idempotency_key=idempotency_key,
        request_url=request_url,
        final_url=response.final_url,
        requested_at=requested_at,
        received_at=received_at,
        window_start=f"{archive_year}-01-01",
        window_end=f"{archive_year}-12-31",
        attempts=attempts,
        http_status=200,
        collection_status="success",
        body_sha256=body_sha256,
        body_size_bytes=len(response.body),
        media_type=media_type,
        response_headers=_safe_headers(response.headers),
        cursor={"year": archive_year, "size": len(items)},
        raw_body=response.body,
        items=items,
        total_pages=1,
        total_items=len(items),
        archive_year=archive_year,
        source_last_modified=source_last_modified,
        source_etag=source_etag,
    )


def _normalize_row(
    row: list[str],
    *,
    header: tuple[str, ...],
    archive_year: int,
    source_row_number: int,
) -> dict[str, object]:
    source = dict(zip(header, row, strict=True))
    try:
        amendment_year = int(source["Ano da Emenda"].strip())
    except ValueError as error:
        raise CGUFederalAmendmentDocumentArchiveError(
            "O ano da emenda em um documento é inválido."
        ) from error
    if not 2000 <= amendment_year <= archive_year:
        raise CGUFederalAmendmentDocumentArchiveError(
            "O ano da emenda está fora do intervalo documental."
        )
    date_match = _DOCUMENT_DATE.fullmatch(source["Data Documento"].strip())
    if date_match is None:
        raise CGUFederalAmendmentDocumentArchiveError(
            "A data de um documento federal é inválida."
        )
    day, month, year = (int(value) for value in date_match.groups())
    try:
        document_date = datetime(year, month, day).date()
    except ValueError as error:
        raise CGUFederalAmendmentDocumentArchiveError(
            "A data de um documento federal é inválida."
        ) from error
    if document_date.year != archive_year:
        raise CGUFederalAmendmentDocumentArchiveError(
            "A data do documento diverge do ano do arquivo."
        )
    stage_source = source["Fase da despesa"].strip()
    stage = _STAGES.get(_ascii_key(stage_source))
    if stage is None:
        raise CGUFederalAmendmentDocumentArchiveError(
            "A fase da despesa federal não é reconhecida."
        )

    field_columns = {
        "amendment_code": "Código da Emenda",
        "author_code": "Código do Autor da Emenda",
        "author_name": "Nome do Autor da Emenda",
        "amendment_number": "Número da emenda",
        "amendment_type": "Tipo de Emenda",
        "document_code": "Código Documento",
        "locality": "Localidade de aplicação do recurso",
        "state_code": "UF de aplicação do recurso",
        "municipality_name": "Município de aplicação do recurso",
        "municipality_ibge": "Código IBGE do município de aplicação do recurso",
        "beneficiary_code": "Código favorecido",
        "beneficiary_name": "Favorecido",
        "beneficiary_type": "Tipo Favorecido",
        "beneficiary_state": "UF Favorecido",
        "beneficiary_municipality": "Município Favorecido",
        "management_unit_code": "Código UG",
        "management_unit_name": "UG",
        "budget_unit_code": "Código Unidade Orçamentária",
        "budget_unit_name": "Unidade Orçamentária",
        "agency_code": "Código Órgão SIAFI",
        "agency_name": "Órgão",
        "superior_agency_code": "Código Órgão Superior SIAFI",
        "superior_agency_name": "Órgão Superior",
        "expense_group_code": "Código Grupo Despesa",
        "expense_group_name": "Grupo Despesa",
        "expense_element_code": "Código Elemento Despesa",
        "expense_element_name": "Elemento Despesa",
        "application_mode_code": "Código Modalidade Aplicação Despesa",
        "application_mode_name": "Modalidade Aplicação Despesa",
        "budget_plan_code": "Código Plano Orçamentário",
        "budget_plan_name": "Plano Orçamentário",
        "function_code": "Código Função",
        "function_name": "Função",
        "subfunction_code": "Código SubFunção",
        "subfunction_name": "SubFunção",
        "program_code": "Código Programa",
        "program_name": "Programa",
        "action_code": "Código Ação",
        "action_name": "Ação",
        "citizen_language": "Linguagem Cidadã",
        "localizer_code": "Código Subtítulo (Localizador)",
        "localizer_name": "Subtítulo (Localizador)",
        "has_agreement": "Possui convênio?",
    }
    text = {name: source[column].strip() for name, column in field_columns.items()}
    for required in (
        "amendment_code",
        "author_name",
        "document_code",
        "locality",
        "municipality_ibge",
        "beneficiary_name",
    ):
        if not text[required]:
            raise CGUFederalAmendmentDocumentArchiveError(
                f"O campo {required} de um documento federal está vazio."
            )
    if any(len(value) > 8000 for value in text.values()):
        raise CGUFederalAmendmentDocumentArchiveError(
            "Um campo textual do documento federal excede o limite."
        )
    normalized: dict[str, object] = {
        **text,
        "archive_year": archive_year,
        "amendment_year": amendment_year,
        "document_date": document_date.isoformat(),
        "expense_stage": stage,
        "expense_stage_source": stage_source,
        "committed_amount": _decimal(
            source["Valor Empenhado"], name="committed_amount"
        ),
        "paid_amount": _decimal(source["Valor Pago"], name="paid_amount"),
        "source_row_number": source_row_number,
    }
    fingerprint_payload = {
        key: value
        for key, value in normalized.items()
        if key != "source_row_number"
    }
    normalized["document_line_fingerprint"] = hashlib.sha256(
        json.dumps(
            fingerprint_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return normalized


def _natural_identity(item: Mapping[str, object]) -> tuple[str, ...]:
    return (str(item["document_line_fingerprint"]),)


def _decimal(value: str, *, name: str) -> str:
    stripped = value.strip()
    if not _DECIMAL.fullmatch(stripped):
        raise CGUFederalAmendmentDocumentArchiveError(
            f"O campo monetário {name} é inválido."
        )
    try:
        parsed = Decimal(stripped.replace(",", "."))
    except InvalidOperation as error:
        raise CGUFederalAmendmentDocumentArchiveError(
            f"O campo monetário {name} é inválido."
        ) from error
    return format(parsed, "f")


def _ascii_key(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value.strip().lower())
        if not unicodedata.combining(character)
    )


def _validate_year(year: int) -> None:
    if not 2000 <= year <= 2100:
        raise ValueError("Ano documental federal inválido.")


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
        raise CGUFederalAmendmentDocumentArchiveError(
            "O CSV anual viola os limites de segurança."
        )


def _normalized_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in headers.items()}


def _safe_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in _normalized_headers(headers).items()
        if key in SAFE_RESPONSE_HEADERS
    }
