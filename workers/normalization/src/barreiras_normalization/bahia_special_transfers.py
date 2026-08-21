"""Normalização territorial segura das Transferências Especiais da Bahia.

O ZIP oficial possui um identificador de credor restrito e uma view de
pagamentos com aspas internas não escapadas no objeto. Este módulo restaura
somente campos financeiros e documentais necessários, descarta credor e
CPF/CNPJ antes de criar qualquer resultado e exige os vínculos oficiais entre
pagamento, centralização e despesa.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from barreiras_collectors.connectors.bahia_special_transfers import (
    EXECUTION_CODE,
    EXPECTED_MEMBER_COLUMNS,
    PAYMENT_MEMBER_NAME,
    PAYMENT_RECORD_START,
    parse_special_transfer_archive,
)

SPECIAL_TRANSFER_PARSER_VERSION = "bahia-special-transfer-payment/1.0.0"
CENTRALIZATION_MEMBER = (
    "VW_PAINEL_TRANSFERENCIA_ESPECIAL_CENTRALIZACAO_DESCENTRALIZACAO.csv"
)
EXPENSE_MEMBER = "VW_PAINEL_TRANSFERENCIA_ESPECIAL_DESPESA.csv"
TERRITORIAL_SCOPE = "payment_object_literal_barreiras"

_BARREIRAS_TOKEN = re.compile(
    r"(?<![A-Za-zÀ-ÿ])Barreiras(?:\s*/\s*BA)?(?![A-Za-zÀ-ÿ])",
    re.IGNORECASE,
)
_PAYMENT_ID = re.compile(r"\d{18,19}")
_YEAR = re.compile(r"\d{4}")
_BRL_AMOUNT = re.compile(r"-?\d{1,18},\d{2}")
_PAYMENT_STATUSES = frozenset({"Sim", "Não", "Em Processamento"})
_PAYMENT_HOST = "www.transparencia.ba.gov.br"
_DOCUMENT_NUMBER = re.compile(
    r"(?<!\d)(?:"
    r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}"
    r"|\d{3}\.?\d{3}\.?\d{3}-?\d{2}"
    r")(?!\d)"
)


class SpecialTransferNormalizationError(ValueError):
    """O recorte não satisfaz o contrato determinístico e seguro."""


@dataclass(frozen=True)
class SpecialTransferPaymentCandidate:
    fiscal_year: int
    amendment_number: str
    amendment_year: int
    author_name: str
    agency_name: str
    agency_code: str
    budget_unit_name: str
    budget_unit_code: str
    action_name: str
    expense_code: str
    execution_code: str
    liquidation_codes: tuple[str, ...]
    payment_id: str
    payment_number: str
    payment_date: date
    payment_amount: Decimal
    gcv_amount: Decimal | None
    payment_status: str
    object_text: str
    payment_url: str
    territorial_scope: str
    evidence_text: str
    evidence_sha256: str
    parser_version: str = SPECIAL_TRANSFER_PARSER_VERSION


def parse_special_transfer_payment_candidates(
    body: bytes,
) -> tuple[SpecialTransferPaymentCandidate, ...]:
    """Extrai pagamentos cujo objeto menciona Barreiras por chave oficial."""
    parse_special_transfer_archive(body)
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as package:
            centralizations = _regular_rows(package, CENTRALIZATION_MEMBER)
            expenses = _regular_rows(package, EXPENSE_MEMBER)
            payments = _payment_rows(package)
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile, KeyError) as error:
        raise SpecialTransferNormalizationError(
            "O ZIP oficial não pôde ser restaurado integralmente."
        ) from error

    expense_by_code = _unique_rows(expenses, "num_codigo", "despesa")
    centralization_by_execution: dict[str, list[dict[str, str]]] = {}
    for row in centralizations:
        execution_code = row["num_codigo_exec"].strip()
        if not execution_code:
            raise SpecialTransferNormalizationError(
                "A centralização omitiu a chave de execução."
            )
        centralization_by_execution.setdefault(execution_code, []).append(row)

    candidates: list[SpecialTransferPaymentCandidate] = []
    seen_payments: set[str] = set()
    for payment in payments:
        payment_id = payment["payment_id"]
        if payment_id in seen_payments:
            raise SpecialTransferNormalizationError(
                "A fonte repetiu um identificador de pagamento."
            )
        seen_payments.add(payment_id)
        if _BARREIRAS_TOKEN.search(payment["object_text"]) is None:
            continue

        relationships = centralization_by_execution.get(payment["execution_code"], [])
        expense_codes = {
            relationship["num_codigo"].strip()
            for relationship in relationships
            if relationship["num_codigo"].strip()
        }
        if len(expense_codes) != 1:
            raise SpecialTransferNormalizationError(
                "O pagamento territorial não possui vínculo oficial único."
            )
        expense_code = next(iter(expense_codes))
        expense = expense_by_code.get(expense_code)
        if expense is None:
            raise SpecialTransferNormalizationError(
                "O vínculo territorial não encontrou uma despesa oficial."
            )
        liquidation_codes = tuple(
            sorted(
                {
                    relationship["num_codigo_liqu"].strip()
                    for relationship in relationships
                    if relationship["num_codigo_liqu"].strip()
                }
            )
        )
        candidate = _candidate(
            payment,
            expense_code=expense_code,
            liquidation_codes=liquidation_codes,
            expense=expense,
        )
        candidates.append(candidate)
    return tuple(candidates)


def special_transfer_payload(
    candidate: SpecialTransferPaymentCandidate,
    *,
    source_url: str,
    source_artifact_sha256: str,
    source_collected_at: str,
) -> dict[str, object]:
    """Produz payload sem campos de credor ou identificadores pessoais."""
    payload = asdict(candidate)
    payload.update(
        {
            "schema_name": "bahia-special-transfer-payment-candidate",
            "schema_version": "1.0.0",
            "payment_date": candidate.payment_date.isoformat(),
            "payment_amount": format(candidate.payment_amount, "f"),
            "gcv_amount": (
                format(candidate.gcv_amount, "f")
                if candidate.gcv_amount is not None
                else None
            ),
            "source_url": source_url,
            "source_artifact_sha256": source_artifact_sha256,
            "source_collected_at": source_collected_at,
        }
    )
    return payload


def _regular_rows(
    package: zipfile.ZipFile,
    member_name: str,
) -> list[dict[str, str]]:
    decoded = package.read(member_name).decode("utf-8-sig", errors="strict")
    reader = csv.DictReader(
        io.StringIO(decoded, newline=""), delimiter=";", strict=True
    )
    if tuple(reader.fieldnames or ()) != EXPECTED_MEMBER_COLUMNS[member_name]:
        raise SpecialTransferNormalizationError(
            f"O cabeçalho de {member_name} diverge do contrato."
        )
    rows: list[dict[str, str]] = []
    try:
        for source_row in reader:
            if not source_row or all(
                not str(value or "").strip() for value in source_row.values()
            ):
                continue
            if None in source_row or any(
                value is None for value in source_row.values()
            ):
                raise SpecialTransferNormalizationError(
                    f"Uma linha de {member_name} possui largura inválida."
                )
            rows.append({key: str(value).strip() for key, value in source_row.items()})
    except csv.Error as error:
        raise SpecialTransferNormalizationError(
            f"O CSV de {member_name} está inválido."
        ) from error
    return rows


def _unique_rows(
    rows: list[dict[str, str]],
    key: str,
    label: str,
) -> dict[str, dict[str, str]]:
    unique: dict[str, dict[str, str]] = {}
    for row in rows:
        value = row[key].strip()
        if not value or value in unique:
            raise SpecialTransferNormalizationError(
                f"A fonte publicou uma chave de {label} vazia ou duplicada."
            )
        unique[value] = row
    return unique


def _payment_rows(package: zipfile.ZipFile) -> list[dict[str, str]]:
    decoded = package.read(PAYMENT_MEMBER_NAME).decode("utf-8-sig", errors="strict")
    first_line_end = decoded.find("\n")
    if first_line_end < 0:
        raise SpecialTransferNormalizationError("A view de pagamentos não tem dados.")
    header = next(csv.reader([decoded[:first_line_end]], delimiter=";"))
    if tuple(header) != EXPECTED_MEMBER_COLUMNS[PAYMENT_MEMBER_NAME]:
        raise SpecialTransferNormalizationError(
            "O cabeçalho da view de pagamentos diverge do contrato."
        )
    data = decoded[first_line_end + 1 :]
    starts = list(PAYMENT_RECORD_START.finditer(data))
    if not starts and data.strip():
        raise SpecialTransferNormalizationError(
            "A view de pagamentos não possui limites verificáveis."
        )
    if starts and data[: starts[0].start()].strip():
        raise SpecialTransferNormalizationError(
            "Há conteúdo sem vínculo antes do primeiro pagamento."
        )
    rows: list[dict[str, str]] = []
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(data)
        rows.append(_parse_payment_record(data[match.start() : end].strip()))
    return rows


def _parse_payment_record(record: str) -> dict[str, str]:
    parts = record.rsplit(";", 5)
    if len(parts) != 6:
        raise SpecialTransferNormalizationError(
            "Um pagamento não possui os campos finais esperados."
        )
    prefix_and_object, commitment, year, execution, status, payment_url = parts
    prefix, object_text = _consume_prefix(prefix_and_object, 7)
    prefix = [_unquote(value) for value in prefix]
    object_text = _mask_document_numbers(_unquote(object_text.strip()))
    commitment = _unquote(commitment)
    year = _unquote(year)
    execution = _unquote(execution)
    status = _unquote(status)
    payment_url = _unquote(payment_url)

    payment_id = prefix[0]
    if (
        _PAYMENT_ID.fullmatch(payment_id) is None
        or not prefix[1]
        or not object_text
        or not commitment
        or _YEAR.fullmatch(year) is None
        or EXECUTION_CODE.fullmatch(execution) is None
        or status not in _PAYMENT_STATUSES
        or not _official_payment_url(payment_url)
    ):
        raise SpecialTransferNormalizationError(
            "Um pagamento diverge do contrato estrutural oficial."
        )
    payment_date = _parse_date(prefix[4])
    payment_amount = _parse_amount(prefix[5])
    gcv_amount = _parse_optional_amount(prefix[6])
    return {
        "payment_id": payment_id,
        "payment_number": prefix[1],
        "payment_date": payment_date.isoformat(),
        "payment_amount": format(payment_amount, "f"),
        "gcv_amount": format(gcv_amount, "f") if gcv_amount is not None else "",
        "object_text": object_text,
        "commitment": commitment,
        "fiscal_year": year,
        "execution_code": execution,
        "payment_status": status,
        "payment_url": payment_url,
    }


def _consume_prefix(value: str, field_count: int) -> tuple[list[str], str]:
    fields: list[str] = []
    position = 0
    for _ in range(field_count):
        field, position = _consume_csv_field(value, position)
        fields.append(field)
    return fields, value[position:]


def _consume_csv_field(value: str, position: int) -> tuple[str, int]:
    if position >= len(value):
        raise SpecialTransferNormalizationError("Um pagamento foi truncado.")
    start = position
    if value[position] != '"':
        delimiter = value.find(";", position)
        if delimiter < 0:
            raise SpecialTransferNormalizationError("Um pagamento foi truncado.")
        return value[start:delimiter], delimiter + 1

    position += 1
    output: list[str] = []
    while position < len(value):
        character = value[position]
        if character == '"':
            if position + 1 < len(value) and value[position + 1] == '"':
                output.append('"')
                position += 2
                continue
            if position + 1 < len(value) and value[position + 1] == ";":
                return "".join(output), position + 2
        output.append(character)
        position += 1
    raise SpecialTransferNormalizationError("Um campo CSV foi truncado.")


def _unquote(value: str) -> str:
    cleaned = value.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] == '"':
        cleaned = cleaned[1:-1]
    return cleaned.replace('""', '"').strip()


def _mask_document_numbers(value: str) -> str:
    return _DOCUMENT_NUMBER.sub("[documento ocultado]", value)


def _candidate(
    payment: dict[str, str],
    *,
    expense_code: str,
    liquidation_codes: tuple[str, ...],
    expense: dict[str, str],
) -> SpecialTransferPaymentCandidate:
    fiscal_year = _parse_year(payment["fiscal_year"])
    amendment_year = _parse_year(expense["Ano da Emenda"])
    if fiscal_year != _parse_year(expense["Ano Exercício"]):
        raise SpecialTransferNormalizationError(
            "O exercício do pagamento diverge da despesa vinculada."
        )
    required_expense = (
        "Número da Emenda Parlamentar",
        "Deputado",
        "Órgão",
        "sgl_orgao_orcamento",
        "Unidade Orçamentária",
        "nom_res_unidade_orcamentaria",
        "Ação do Programa de Governo",
    )
    if any(not expense[field].strip() for field in required_expense):
        raise SpecialTransferNormalizationError(
            "A despesa vinculada omitiu campo documental obrigatório."
        )
    evidence = {
        "action_name": expense["Ação do Programa de Governo"].strip(),
        "amendment_number": expense["Número da Emenda Parlamentar"].strip(),
        "amendment_year": amendment_year,
        "author_name": expense["Deputado"].strip(),
        "expense_code": expense_code,
        "execution_code": payment["execution_code"],
        "object_text": payment["object_text"],
        "payment_amount": payment["payment_amount"],
        "payment_date": payment["payment_date"],
        "payment_id": payment["payment_id"],
        "payment_status": payment["payment_status"],
        "payment_url": payment["payment_url"],
        "territorial_scope": TERRITORIAL_SCOPE,
    }
    evidence_text = json.dumps(
        evidence,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return SpecialTransferPaymentCandidate(
        fiscal_year=fiscal_year,
        amendment_number=evidence["amendment_number"],
        amendment_year=amendment_year,
        author_name=evidence["author_name"],
        agency_name=expense["Órgão"].strip(),
        agency_code=expense["sgl_orgao_orcamento"].strip(),
        budget_unit_name=expense["Unidade Orçamentária"].strip(),
        budget_unit_code=expense["nom_res_unidade_orcamentaria"].strip(),
        action_name=evidence["action_name"],
        expense_code=evidence["expense_code"],
        execution_code=evidence["execution_code"],
        liquidation_codes=liquidation_codes,
        payment_id=evidence["payment_id"],
        payment_number=payment["payment_number"],
        payment_date=datetime.fromisoformat(payment["payment_date"]).date(),
        payment_amount=Decimal(payment["payment_amount"]),
        gcv_amount=(Decimal(payment["gcv_amount"]) if payment["gcv_amount"] else None),
        payment_status=evidence["payment_status"],
        object_text=evidence["object_text"],
        payment_url=evidence["payment_url"],
        territorial_scope=TERRITORIAL_SCOPE,
        evidence_text=evidence_text,
        evidence_sha256=hashlib.sha256(evidence_text.encode("utf-8")).hexdigest(),
    )


def _parse_year(value: str) -> int:
    if _YEAR.fullmatch(value.strip()) is None:
        raise SpecialTransferNormalizationError("Um exercício é inválido.")
    year = int(value)
    if not 2000 <= year <= 2200:
        raise SpecialTransferNormalizationError("Um exercício está fora do limite.")
    return year


def _parse_date(value: str) -> date:
    cleaned = value.strip()
    for date_format in ("%d/%m/%Y", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.strptime(cleaned, date_format).date()
        except ValueError:
            continue
    raise SpecialTransferNormalizationError("Uma data de pagamento é inválida.")


def _parse_amount(value: str) -> Decimal:
    cleaned = value.strip()
    if _BRL_AMOUNT.fullmatch(cleaned) is None:
        raise SpecialTransferNormalizationError("Um valor monetário é inválido.")
    try:
        return Decimal(cleaned.replace(",", "."))
    except InvalidOperation as error:
        raise SpecialTransferNormalizationError(
            "Um valor monetário não é decimal."
        ) from error


def _parse_optional_amount(value: str) -> Decimal | None:
    if not value.strip():
        return None
    return _parse_amount(value)


def _official_payment_url(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname == _PAYMENT_HOST
        and parsed.port in (None, 443)
        and not parsed.username
        and not parsed.password
        and not parsed.fragment
    )
