"""Totalizadores determinísticos da relação municipal de servidores.

O parser recebe texto já extraído do PDF oficial e devolve somente agregados.
Nomes, matrículas, cargos, lotações e descontos individuais não atravessam
esta fronteira. O total geral só é aceito quando fecha aritmeticamente e
coincide com a soma de todos os subtotais declarados no documento.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

PAYROLL_REPORT_PARSER_VERSION = "payroll-report-aggregate/1.0.0"


class PayrollReportContractError(ValueError):
    """O documento não atende ao leiaute agregado comprovado."""


@dataclass(frozen=True)
class PayrollReportAggregate:
    employee_count: int
    gross_amount: Decimal
    deduction_amount: Decimal
    net_amount: Decimal
    subtotal_count: int
    parser_version: str = PAYROLL_REPORT_PARSER_VERSION


@dataclass(frozen=True)
class _DeclaredTotal:
    employee_count: int
    gross_amount: Decimal
    deduction_amount: Decimal
    net_amount: Decimal


_AMOUNT = r"(?:\d{1,3}(?:\.\d{3})*|\d+),\d{2}"
_HEADER_FIELDS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bMat\.",
        r"\bNome\b",
        r"\bCargo\b",
        r"\bRegime/V\S*nculo\b",
        r"\bProvento\b",
        r"\bDesconto\b",
        r"\bL\S*quido\b",
    )
)
_TOTAL_ROW = re.compile(
    rf"^Total\s+de\s+Funcion\S*rios(?P<grand>\s+Geral)?\s*:\s*"
    rf"(?P<count>\d+)\s+"
    rf"(?P<gross>{_AMOUNT})\s+"
    rf"(?P<deduction>{_AMOUNT})\s+"
    rf"(?P<net>{_AMOUNT})\s*$",
    re.IGNORECASE,
)


def _amount(value: str) -> Decimal:
    try:
        return Decimal(value.replace(".", "").replace(",", ".")).quantize(
            Decimal("0.01")
        )
    except InvalidOperation as error:
        raise PayrollReportContractError(
            "total monetário inválido no documento"
        ) from error


def _declared_total(match: re.Match[str]) -> _DeclaredTotal:
    total = _DeclaredTotal(
        employee_count=int(match.group("count")),
        gross_amount=_amount(match.group("gross")),
        deduction_amount=_amount(match.group("deduction")),
        net_amount=_amount(match.group("net")),
    )
    if total.employee_count < 1:
        raise PayrollReportContractError(
            "total de vínculos deve ser positivo"
        )
    if total.gross_amount - total.deduction_amount != total.net_amount:
        raise PayrollReportContractError(
            "aritmética declarada de provento, desconto e líquido não fecha"
        )
    return total


def _has_validated_header(text: str) -> bool:
    return any(
        all(field.search(line) is not None for field in _HEADER_FIELDS)
        for line in text.splitlines()
    )


def parse_payroll_report_aggregate(text: str) -> PayrollReportAggregate:
    """Valida subtotais e retorna apenas o total geral reconciliado."""

    if not isinstance(text, str) or not text.strip():
        raise PayrollReportContractError("texto do relatório vazio")
    if not _has_validated_header(text):
        raise PayrollReportContractError(
            "cabeçalho da relação de servidores não reconhecido"
        )

    subtotals: list[_DeclaredTotal] = []
    grand_totals: list[_DeclaredTotal] = []
    for line in text.splitlines():
        match = _TOTAL_ROW.match(line.strip())
        if match is None:
            continue
        total = _declared_total(match)
        if match.group("grand"):
            grand_totals.append(total)
        else:
            subtotals.append(total)

    if not subtotals:
        raise PayrollReportContractError(
            "nenhum subtotal de lotação reconhecido"
        )
    if len(grand_totals) != 1:
        raise PayrollReportContractError(
            "documento deve conter exatamente um total geral"
        )

    grand = grand_totals[0]
    subtotal_sum = _DeclaredTotal(
        employee_count=sum(row.employee_count for row in subtotals),
        gross_amount=sum(
            (row.gross_amount for row in subtotals),
            start=Decimal("0.00"),
        ),
        deduction_amount=sum(
            (row.deduction_amount for row in subtotals),
            start=Decimal("0.00"),
        ),
        net_amount=sum(
            (row.net_amount for row in subtotals),
            start=Decimal("0.00"),
        ),
    )
    if subtotal_sum != grand:
        raise PayrollReportContractError(
            "soma dos subtotais diverge do total geral declarado"
        )

    return PayrollReportAggregate(
        employee_count=grand.employee_count,
        gross_amount=grand.gross_amount,
        deduction_amount=grand.deduction_amount,
        net_amount=grand.net_amount,
        subtotal_count=len(subtotals),
    )
