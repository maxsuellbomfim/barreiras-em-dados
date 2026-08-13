"""Normalizacao dos agregados estaduais de execucao de emendas da Bahia.

O arquivo do FIPLAN nao publica municipio nem numero individual da emenda.
Consequentemente, estes registros descrevem somente execucao estadual agregada
por ano, estrutura orcamentaria, acao e autor. Nenhum valor deste modulo pode
ser rotulado como pago a Barreiras sem uma reconciliacao territorial posterior.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from barreiras_collectors.connectors.bahia_state_amendments import (
    EXPECTED_MEMBER_COLUMNS,
    parse_state_amendment_archive,
)

STATE_EXECUTION_PARSER_VERSION = "bahia-state-execution-aggregate/1.0.0"
EXPENSE_MEMBER_NAME = "VW_PAINEL_EMENDAS_PARLAMENTARES_DESPESAS.csv"
TERRITORIAL_SCOPE = "not_available_in_execution_archive"

_EXECUTION_CODE = re.compile(
    r"^(?P<year>\d{4})\.\d+\.\d+\.\d+\.\d+\."
    r"(?P<action>\d+)\.(?P<author>\d+)\.\d+$"
)
_BRL_AMOUNT = re.compile(r"^-?\d{1,18},\d{2}$")


class StateExecutionParseError(ValueError):
    """O agregado do FIPLAN nao satisfaz o contrato deterministico."""


@dataclass(frozen=True)
class StateExecutionAggregate:
    fiscal_year: int
    agency_name: str
    agency_code: str
    budget_unit_name: str
    budget_unit_code: str
    action_name: str
    action_code: str
    author_name: str
    author_external_code: str
    execution_code: str
    initial_budget_amount: Decimal
    current_budget_amount: Decimal
    committed_amount: Decimal
    liquidated_amount: Decimal
    paid_amount: Decimal
    territorial_scope: str
    evidence_text: str
    evidence_sha256: str
    parser_version: str = STATE_EXECUTION_PARSER_VERSION


def parse_state_execution_archive(
    body: bytes,
) -> tuple[StateExecutionAggregate, ...]:
    """Extrai a view de despesas sem atribuir seus valores a um municipio."""
    parse_state_amendment_archive(body)
    try:
        package = zipfile.ZipFile(io.BytesIO(body))
        with package:
            decoded = package.read(EXPENSE_MEMBER_NAME).decode(
                "utf-8-sig", errors="strict"
            )
    except (KeyError, OSError, UnicodeDecodeError, zipfile.BadZipFile) as error:
        raise StateExecutionParseError(
            "O ZIP estadual nao contem a view de despesas integra."
        ) from error

    reader = csv.DictReader(
        io.StringIO(decoded, newline=""),
        delimiter=";",
        strict=True,
    )
    expected_columns = EXPECTED_MEMBER_COLUMNS[EXPENSE_MEMBER_NAME]
    if tuple(reader.fieldnames or ()) != expected_columns:
        raise StateExecutionParseError(
            "O cabecalho da execucao estadual diverge do contrato."
        )

    aggregates: list[StateExecutionAggregate] = []
    execution_codes: set[str] = set()
    try:
        for source_row in reader:
            if not source_row or all(
                not str(value or "").strip() for value in source_row.values()
            ):
                continue
            if None in source_row or any(
                value is None for value in source_row.values()
            ):
                raise StateExecutionParseError(
                    "Uma linha da execucao estadual possui largura invalida."
                )
            aggregate = _parse_row(source_row, expected_columns)
            if aggregate.execution_code in execution_codes:
                raise StateExecutionParseError(
                    "O arquivo estadual repetiu uma chave de execucao."
                )
            execution_codes.add(aggregate.execution_code)
            aggregates.append(aggregate)
    except csv.Error as error:
        raise StateExecutionParseError(
            "A view de despesas estadual possui CSV invalido."
        ) from error
    return tuple(aggregates)


def _parse_row(
    row: dict[str | None, str | None],
    columns: tuple[str, ...],
) -> StateExecutionAggregate:
    values = {column: str(row[column] or "").strip() for column in columns}
    execution_code = values["num_codigo"]
    code = _EXECUTION_CODE.fullmatch(execution_code)
    if code is None:
        raise StateExecutionParseError("O codigo da execucao estadual e invalido.")
    fiscal_year = _parse_year(values["Ano Exercício"])
    author_code = values["cod_subfonte_recurso"]
    if (
        str(fiscal_year) != code.group("year")
        or author_code != code.group("author")
    ):
        raise StateExecutionParseError(
            "O codigo da execucao diverge do ano ou do autor publicado."
        )
    required_text = (
        "Órgão",
        "sgl_orgao_orcamento",
        "Unidade Orçamentária",
        "nom_res_unidade_orcamentaria",
        "Ação do Programa de Governo",
        "Nome do Deputado",
    )
    if any(not values[field] for field in required_text):
        raise StateExecutionParseError(
            "Uma linha da execucao estadual omitiu campo obrigatorio."
        )
    evidence_text = ";".join(values[column] for column in columns)
    return StateExecutionAggregate(
        fiscal_year=fiscal_year,
        agency_name=values["Órgão"],
        agency_code=values["sgl_orgao_orcamento"],
        budget_unit_name=values["Unidade Orçamentária"],
        budget_unit_code=values["nom_res_unidade_orcamentaria"],
        action_name=values["Ação do Programa de Governo"],
        action_code=code.group("action"),
        author_name=values["Nome do Deputado"],
        author_external_code=author_code,
        execution_code=execution_code,
        initial_budget_amount=_parse_amount(values["Valor Orçado Inicial."]),
        current_budget_amount=_parse_amount(values["Valor Orçado Atual."]),
        committed_amount=_parse_amount(values["Valor Empenhado."]),
        liquidated_amount=_parse_amount(values["Valor Liquidado."]),
        paid_amount=_parse_amount(values["Valor Pago."]),
        territorial_scope=TERRITORIAL_SCOPE,
        evidence_text=evidence_text,
        evidence_sha256=hashlib.sha256(evidence_text.encode("utf-8")).hexdigest(),
    )


def _parse_year(value: str) -> int:
    if not re.fullmatch(r"\d{4}", value):
        raise StateExecutionParseError("O exercicio estadual e invalido.")
    year = int(value)
    if year < 2000 or year > 2200:
        raise StateExecutionParseError("O exercicio estadual esta fora do limite.")
    return year


def _parse_amount(value: str) -> Decimal:
    if not _BRL_AMOUNT.fullmatch(value):
        raise StateExecutionParseError("Um valor estadual possui formato invalido.")
    try:
        return Decimal(value.replace(",", "."))
    except InvalidOperation as error:
        raise StateExecutionParseError("Um valor estadual nao e decimal.") from error
