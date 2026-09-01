"""Parser fail-closed do demonstrativo analítico de despesa do SIGA/TCM-BA."""

from __future__ import annotations

import calendar
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal

from .financial_expense_pdf import (
    ExpensePdfReport,
    ExpensePdfRow,
    ExpensePdfUnitTotal,
)
from .revenue import RevenueNormalizationError, parse_brl_amount


class TcmBaExpenseContractError(RevenueNormalizationError):
    """O texto não comprova o contrato do demonstrativo SIGA esperado."""


_AMOUNT = r"-?(?:\d{1,3}(?:\.\d{3})*|\d+),\d{1,2}"
_AMOUNT_SEQUENCE = rf"(?P<amounts>{_AMOUNT}(?:\s+{_AMOUNT}){{11}})"
_ENTITY_COMPETENCE = re.compile(
    r"^Unidade:\s*(?P<entity>.+?)\s+Compet.ncia:\s*"
    r"(?P<month>\d{2})/(?P<year>\d{4})\s*$",
    re.IGNORECASE,
)
_PAGE = re.compile(
    r"^P.gina\s+(?P<number>\d+)\s+de\s+(?P<total>\d+)\b",
    re.IGNORECASE,
)
_BUDGET_UNIT = re.compile(
    r"^(?P<code>\d+\.\d{4})(?P<name>[^\d.].+)$"
)
_EXPENSE_START = re.compile(
    r"^(?P<code>\d\.\d\.\d{2}\.\d{2}\.\d{2})\s+"
    r"(?P<description>.+)$"
)
_SOURCE_AMOUNTS = re.compile(rf"^(?P<source>\d{{4}})\s*{_AMOUNT_SEQUENCE}$")
_UNIT_TOTAL = re.compile(
    rf"^Total\s+da\s+Unidade\s*:\s*{_AMOUNT_SEQUENCE}$",
    re.IGNORECASE,
)
_POWER_TOTAL = re.compile(
    rf"^Total\s+do\s+Poder\s*:\s*{_AMOUNT_SEQUENCE}$",
    re.IGNORECASE,
)

_AMOUNT_FIELDS = (
    "fixed_amount",
    "additions_amount",
    "reductions_amount",
    "updated_amount",
    "committed_period_amount",
    "committed_to_date_amount",
    "liquidated_period_amount",
    "liquidated_to_date_amount",
    "paid_period_amount",
    "paid_to_date_amount",
    "unpaid_committed_amount",
    "balance_amount",
)


def _amounts(value: str, *, field: str) -> tuple[Decimal, ...]:
    parsed = [_amount(item) for item in value.split()]
    if len(parsed) != 12:
        raise TcmBaExpenseContractError(f"{field} deve conter 12 valores")
    return tuple(parsed)


def _amount(value: str) -> Decimal:
    sign = Decimal("-1") if value.startswith("-") else Decimal("1")
    return sign * parse_brl_amount(value.removeprefix("-"))


def _summary_amount(text: str, label: str) -> Decimal:
    match = re.search(rf"(?im)^{label}\s*:\s*(?P<amount>{_AMOUNT})\s*$", text)
    if match is None:
        raise TcmBaExpenseContractError(
            "resumo obrigatório do demonstrativo não foi encontrado"
        )
    return _amount(match.group("amount"))


def _assert_amounts_equal(
    *,
    expected: tuple[Decimal, ...],
    observed: tuple[Decimal, ...],
    message: str,
) -> None:
    if observed != expected:
        differing = next(
            index
            for index, (left, right) in enumerate(zip(observed, expected, strict=True))
            if left != right
        )
        raise TcmBaExpenseContractError(
            f"{message}: {_AMOUNT_FIELDS[differing]}"
        )


def _values_from_item(item: ExpensePdfRow | ExpensePdfUnitTotal) -> tuple[Decimal, ...]:
    return tuple(getattr(item, field) for field in _AMOUNT_FIELDS)


def _sum_items(
    items: list[ExpensePdfRow] | list[ExpensePdfUnitTotal],
) -> tuple[Decimal, ...]:
    return tuple(
        sum((getattr(item, field) for item in items), start=Decimal("0"))
        for field in _AMOUNT_FIELDS
    )


def _validate_pages_and_period(text: str) -> tuple[date, date]:
    page_matches = [
        match
        for line in text.splitlines()
        if (match := _PAGE.match(" ".join(line.split()))) is not None
    ]
    if not page_matches:
        raise TcmBaExpenseContractError("sequência de páginas não encontrada")
    totals = {int(match.group("total")) for match in page_matches}
    if len(totals) != 1:
        raise TcmBaExpenseContractError("sequência de páginas possui totais distintos")
    total_pages = totals.pop()
    page_numbers = [int(match.group("number")) for match in page_matches]
    if page_numbers != list(range(1, total_pages + 1)):
        raise TcmBaExpenseContractError("sequência de páginas está incompleta")

    headers = [
        match
        for line in text.splitlines()
        if (match := _ENTITY_COMPETENCE.match(" ".join(line.split()))) is not None
    ]
    if len(headers) != total_pages:
        raise TcmBaExpenseContractError(
            "cada página deve identificar o ente municipal e a competência"
        )
    entities = {" ".join(match.group("entity").upper().split()) for match in headers}
    if entities != {"PREFEITURA MUNICIPAL DE BARREIRAS"}:
        raise TcmBaExpenseContractError("ente municipal não corresponde a Barreiras")
    periods = {
        (int(match.group("year")), int(match.group("month"))) for match in headers
    }
    if len(periods) != 1:
        raise TcmBaExpenseContractError("competência diverge entre as páginas")
    year, month = periods.pop()
    try:
        last_day = calendar.monthrange(year, month)[1]
    except calendar.IllegalMonthError as error:
        raise TcmBaExpenseContractError("competência mensal inválida") from error
    return date(year, month, 1), date(year, month, last_day)


def _validate_summary(text: str, total: tuple[Decimal, ...]) -> None:
    summary = {
        0: _summary_amount(text, r"Dota..o\s+Inicial"),
        1: _summary_amount(text, r"Altera..es\s+p/\s+Mais"),
        2: _summary_amount(text, r"Altera..es\s+p/\s+Menos"),
        3: _summary_amount(text, r"Dota..o\s+Atualizada"),
        10: _summary_amount(text, r"Despesa\s+a\s+Pagar"),
        11: _summary_amount(text, r"Saldo\s+da\s+Dota..o"),
    }
    for index, amount in summary.items():
        if total[index] != amount:
            raise TcmBaExpenseContractError(
                f"resumo diverge do Total do Poder: {_AMOUNT_FIELDS[index]}"
            )
    if total[3] != total[0] + total[1] - total[2]:
        raise TcmBaExpenseContractError("Total do Poder viola a dotação atualizada")
    if total[10] != total[5] - total[9]:
        raise TcmBaExpenseContractError("Total do Poder viola a despesa a pagar")
    if total[11] != total[3] - total[5]:
        raise TcmBaExpenseContractError("Total do Poder viola o saldo disponível")


def parse_tcm_ba_expense_pdf_text(text: str) -> ExpensePdfReport:
    """Extrai linhas e totais somente quando o documento SIGA fecha integralmente."""

    if not isinstance(text, str) or not text.strip():
        raise TcmBaExpenseContractError("texto do demonstrativo vazio")
    period_start, period_end = _validate_pages_and_period(text)

    rows: list[ExpensePdfRow] = []
    unit_totals: list[ExpensePdfUnitTotal] = []
    rows_by_unit: dict[tuple[str, str], list[ExpensePdfRow]] = defaultdict(list)
    current_unit: tuple[str, str] | None = None
    pending_code: str | None = None
    pending_description: list[str] = []
    total: tuple[Decimal, ...] | None = None

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = " ".join(line.split())
        if not stripped:
            continue

        source_match = _SOURCE_AMOUNTS.match(stripped)
        if pending_code is not None and source_match is not None:
            if current_unit is None:
                raise TcmBaExpenseContractError(
                    f"linha de despesa sem unidade na linha {line_number}"
                )
            values = _amounts(
                source_match.group("amounts"), field=f"linha {line_number}"
            )
            row = ExpensePdfRow(
                budget_unit_code=current_unit[0],
                budget_unit_name=current_unit[1],
                expense_code=pending_code,
                description=" ".join(pending_description),
                source_code=source_match.group("source"),
                **dict(zip(_AMOUNT_FIELDS, values, strict=True)),
            )
            rows.append(row)
            rows_by_unit[current_unit].append(row)
            pending_code = None
            pending_description = []
            continue

        expense_match = _EXPENSE_START.match(stripped)
        if expense_match is not None:
            if pending_code is not None:
                raise TcmBaExpenseContractError(
                    f"linha {pending_code} não possui fonte e 12 valores "
                    f"antes da linha textual {line_number}"
                )
            if current_unit is None:
                raise TcmBaExpenseContractError(
                    f"linha de despesa sem unidade na linha {line_number}"
                )
            pending_code = expense_match.group("code")
            pending_description = [expense_match.group("description").strip()]
            continue

        unit_match = _BUDGET_UNIT.match(stripped)
        if unit_match is not None:
            if pending_code is not None:
                raise TcmBaExpenseContractError(
                    f"linha {pending_code} não possui fonte e 12 valores"
                )
            current_unit = (
                unit_match.group("code"),
                unit_match.group("name").strip(),
            )
            continue

        unit_total_match = _UNIT_TOTAL.match(stripped)
        if unit_total_match is not None:
            if pending_code is not None or current_unit is None:
                raise TcmBaExpenseContractError("subtotal da unidade sem contexto")
            values = _amounts(
                unit_total_match.group("amounts"),
                field=f"subtotal da unidade na linha {line_number}",
            )
            unit_totals.append(
                ExpensePdfUnitTotal(
                    budget_unit_code=current_unit[0],
                    budget_unit_name=current_unit[1],
                    **dict(zip(_AMOUNT_FIELDS, values, strict=True)),
                )
            )
            continue

        power_total_match = _POWER_TOTAL.match(stripped)
        if power_total_match is not None:
            if pending_code is not None or total is not None:
                raise TcmBaExpenseContractError(
                    "Total do Poder duplicado ou incompleto"
                )
            total = _amounts(power_total_match.group("amounts"), field="Total do Poder")
            continue

        if pending_code is not None:
            pending_description.append(stripped)
            if len(pending_description) > 6:
                raise TcmBaExpenseContractError(
                    f"descrição da linha {pending_code} excede o limite seguro"
                )

    if pending_code is not None:
        raise TcmBaExpenseContractError(
            f"linha {pending_code} não possui fonte e 12 valores"
        )
    if not rows:
        raise TcmBaExpenseContractError("nenhuma linha analítica reconhecida")
    if total is None:
        raise TcmBaExpenseContractError("Total do Poder não encontrado")

    totals_by_unit: dict[tuple[str, str], ExpensePdfUnitTotal] = {}
    for unit_total in unit_totals:
        key = (unit_total.budget_unit_code, unit_total.budget_unit_name)
        if key in totals_by_unit:
            raise TcmBaExpenseContractError("subtotal da unidade está duplicado")
        totals_by_unit[key] = unit_total
    if set(totals_by_unit) != set(rows_by_unit):
        raise TcmBaExpenseContractError(
            "subtotais não cobrem exatamente as unidades com linhas"
        )
    for key, unit_rows in rows_by_unit.items():
        _assert_amounts_equal(
            expected=_values_from_item(totals_by_unit[key]),
            observed=_sum_items(unit_rows),
            message=f"subtotal da unidade diverge das linhas: {key[0]}",
        )
    _assert_amounts_equal(
        expected=total,
        observed=_sum_items(unit_totals),
        message="total do poder diverge dos subtotais",
    )
    _validate_summary(text, total)

    return ExpensePdfReport(
        period_start=period_start,
        period_end=period_end,
        fiscal_year=period_end.year,
        **dict(
            zip(
                (f"total_{field}" for field in _AMOUNT_FIELDS),
                total,
                strict=True,
            )
        ),
        rows=tuple(rows),
        unit_totals=tuple(unit_totals),
    )
