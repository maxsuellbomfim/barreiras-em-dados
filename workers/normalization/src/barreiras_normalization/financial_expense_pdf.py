"""Parser determinístico do Demonstrativo de Despesa Analítica municipal.

O relatório é um retrato da execução orçamentária no intervalo informado no
PDF. Cada linha contém o código de natureza da despesa, fonte e os valores de
fixação, empenho, liquidação, pagamento e saldo. Nenhuma soma é inferida aqui;
o parser apenas converte o texto preservado em valores decimais tipados.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .revenue import RevenueNormalizationError, parse_brl_amount


class ExpensePdfContractError(RevenueNormalizationError):
    """O texto não corresponde ao contrato observado do relatório."""


@dataclass(frozen=True)
class ExpensePdfRow:
    budget_unit_code: str
    budget_unit_name: str
    expense_code: str
    description: str
    source_code: str
    fixed_amount: Decimal
    additions_amount: Decimal
    reductions_amount: Decimal
    updated_amount: Decimal
    committed_period_amount: Decimal
    committed_to_date_amount: Decimal
    liquidated_period_amount: Decimal
    liquidated_to_date_amount: Decimal
    paid_period_amount: Decimal
    paid_to_date_amount: Decimal
    unpaid_committed_amount: Decimal
    balance_amount: Decimal


@dataclass(frozen=True)
class ExpensePdfUnitTotal:
    budget_unit_code: str
    budget_unit_name: str
    fixed_amount: Decimal
    additions_amount: Decimal
    reductions_amount: Decimal
    updated_amount: Decimal
    committed_period_amount: Decimal
    committed_to_date_amount: Decimal
    liquidated_period_amount: Decimal
    liquidated_to_date_amount: Decimal
    paid_period_amount: Decimal
    paid_to_date_amount: Decimal
    unpaid_committed_amount: Decimal
    balance_amount: Decimal


@dataclass(frozen=True)
class ExpensePdfReport:
    period_start: date
    period_end: date
    fiscal_year: int
    total_fixed_amount: Decimal
    total_additions_amount: Decimal
    total_reductions_amount: Decimal
    total_updated_amount: Decimal
    total_committed_period_amount: Decimal
    total_committed_to_date_amount: Decimal
    total_liquidated_period_amount: Decimal
    total_liquidated_to_date_amount: Decimal
    total_paid_period_amount: Decimal
    total_paid_to_date_amount: Decimal
    total_unpaid_committed_amount: Decimal
    total_balance_amount: Decimal
    rows: tuple[ExpensePdfRow, ...]
    unit_totals: tuple[ExpensePdfUnitTotal, ...]


_DATE_RANGE = re.compile(
    r"Data:\s*De\s*(?P<start>\d{2}/\d{2}/\d{4})\s*at(?:e|é|Ã©)\s*"
    r"(?P<end>\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)
_CODE = r"\d+(?:\.\d+){6,8}\.?"
_AMOUNT = r"-?(?:\d{1,3}(?:\.\d{3})*|\d+),\d{1,2}"
# Em relatórios antigos, as colunas "Fonte" e "Fonte TC" podem ser
# extraídas sem espaço (por exemplo, 1500 + 1001 vira 15001001). Preservamos
# o token literal para não colapsar combinações contábeis distintas.
_SOURCE_CODE = r"\d{4}(?:\d{4})?"
_BUDGET_UNIT = re.compile(
    r"^(?P<code>\d{6,8})\s+-\s+(?P<name>\S.+?)\s*$"
)
_ROW = re.compile(
    rf"^(?P<code>{_CODE})\s+(?P<description>.+?)(?<!\d)\s*"
    rf"(?P<source>{_SOURCE_CODE})\s+"
    rf"(?P<amounts>{_AMOUNT}(?:\s+{_AMOUNT}){{11}})\s*$"
)
_TOTAL = re.compile(
    rf"^Total\s*:\s*(?P<amounts>{_AMOUNT}(?:\s+{_AMOUNT}){{11}})\s*$",
    re.IGNORECASE,
)
_UNIT_TOTAL = re.compile(
    rf"^(?P<amounts>{_AMOUNT}(?:\s+{_AMOUNT}){{11}})"
    r"Total\s+da\s+Unidade\s*:\s*$",
    re.IGNORECASE,
)


def _parse_date(value: str) -> date:
    day, month, year = (int(part) for part in value.split("/"))
    try:
        return date(year, month, day)
    except ValueError as error:
        raise ExpensePdfContractError(f"data inválida no relatório: {value}") from error


def _amounts(value: str, *, field: str) -> tuple[Decimal, ...]:
    def parse_amount(item: str) -> Decimal:
        if item.startswith("-"):
            return -parse_brl_amount(item[1:])
        return parse_brl_amount(item)

    values = tuple(parse_amount(item) for item in value.split())
    if len(values) != 12:
        raise ExpensePdfContractError(f"{field} deve conter 12 valores")
    return values


def parse_expense_pdf_text(text: str) -> ExpensePdfReport:
    """Converte um demonstrativo preservado em valores tipados, sem floats."""

    if not isinstance(text, str) or not text.strip():
        raise ExpensePdfContractError("texto do relatório vazio")
    period = _DATE_RANGE.search(text)
    if period is None:
        raise ExpensePdfContractError("período do relatório não encontrado")
    period_start = _parse_date(period.group("start"))
    period_end = _parse_date(period.group("end"))
    if period_start > period_end:
        raise ExpensePdfContractError("início do período posterior ao fim")

    rows: list[ExpensePdfRow] = []
    unit_totals: list[ExpensePdfUnitTotal] = []
    total: tuple[Decimal, ...] | None = None
    budget_unit: tuple[str, str] | None = None
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = " ".join(line.split())
        budget_unit_match = _BUDGET_UNIT.match(stripped)
        if budget_unit_match is not None:
            budget_unit = (
                budget_unit_match.group("code"),
                budget_unit_match.group("name").strip(),
            )
            continue
        unit_total_match = _UNIT_TOTAL.match(stripped)
        if unit_total_match is not None:
            if budget_unit is None:
                raise ExpensePdfContractError(
                    f"subtotal sem unidade orçamentária: {line_number}"
                )
            values = _amounts(
                unit_total_match.group("amounts"),
                field=f"subtotal da unidade na linha {line_number}",
            )
            unit_totals.append(
                ExpensePdfUnitTotal(
                    budget_unit_code=budget_unit[0],
                    budget_unit_name=budget_unit[1],
                    fixed_amount=values[0],
                    additions_amount=values[1],
                    reductions_amount=values[2],
                    updated_amount=values[3],
                    committed_period_amount=values[4],
                    committed_to_date_amount=values[5],
                    liquidated_period_amount=values[6],
                    liquidated_to_date_amount=values[7],
                    paid_period_amount=values[8],
                    paid_to_date_amount=values[9],
                    unpaid_committed_amount=values[10],
                    balance_amount=values[11],
                )
            )
            continue
        total_match = _TOTAL.match(stripped)
        if total_match:
            total = _amounts(total_match.group("amounts"), field="total")
            continue
        match = _ROW.match(stripped)
        if match is None:
            continue
        if budget_unit is None:
            raise ExpensePdfContractError(
                f"linha de despesa sem unidade orçamentária: {line_number}"
            )
        values = _amounts(match.group("amounts"), field=f"linha {line_number}")
        rows.append(
            ExpensePdfRow(
                budget_unit_code=budget_unit[0],
                budget_unit_name=budget_unit[1],
                expense_code=match.group("code").rstrip("."),
                description=match.group("description").strip(),
                source_code=match.group("source"),
                fixed_amount=values[0],
                additions_amount=values[1],
                reductions_amount=values[2],
                updated_amount=values[3],
                committed_period_amount=values[4],
                committed_to_date_amount=values[5],
                liquidated_period_amount=values[6],
                liquidated_to_date_amount=values[7],
                paid_period_amount=values[8],
                paid_to_date_amount=values[9],
                unpaid_committed_amount=values[10],
                balance_amount=values[11],
            )
        )

    if not rows:
        raise ExpensePdfContractError("nenhuma linha de despesa reconhecida")
    if total is None:
        raise ExpensePdfContractError("total declarado da despesa não encontrado")
    return ExpensePdfReport(
        period_start=period_start,
        period_end=period_end,
        fiscal_year=period_end.year,
        total_fixed_amount=total[0],
        total_additions_amount=total[1],
        total_reductions_amount=total[2],
        total_updated_amount=total[3],
        total_committed_period_amount=total[4],
        total_committed_to_date_amount=total[5],
        total_liquidated_period_amount=total[6],
        total_liquidated_to_date_amount=total[7],
        total_paid_period_amount=total[8],
        total_paid_to_date_amount=total[9],
        total_unpaid_committed_amount=total[10],
        total_balance_amount=total[11],
        rows=tuple(rows),
        unit_totals=tuple(unit_totals),
    )
