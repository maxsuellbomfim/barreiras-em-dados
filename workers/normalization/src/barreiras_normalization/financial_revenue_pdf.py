"""Parser deterministico do Demonstrativo de Receita Orcamentaria Sintetico.

O parser recebe texto extraido de um PDF ja preservado. Ele nao baixa arquivos,
nao usa modelo de linguagem e nao publica nada. Se uma linha nao obedecer ao
layout observado, a execucao falha para que o documento seja revisado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .revenue import RevenueNormalizationError, parse_brl_amount


class RevenuePdfContractError(RevenueNormalizationError):
    """O texto nao corresponde ao contrato observado do relatorio."""


@dataclass(frozen=True)
class RevenuePdfRow:
    revenue_code: str
    description: str
    forecast_amount: Decimal
    period_amount: Decimal
    accumulated_amount: Decimal
    difference_more: Decimal
    difference_less: Decimal


@dataclass(frozen=True)
class RevenuePdfReport:
    period_start: date
    period_end: date
    fiscal_year: int
    total_forecast_amount: Decimal
    total_period_amount: Decimal
    total_accumulated_amount: Decimal
    total_difference_more: Decimal
    total_difference_less: Decimal
    rows: tuple[RevenuePdfRow, ...]


_DATE_RANGE = re.compile(
    r"Data:\s*De\s*(?P<start>\d{2}/\d{2}/\d{4})\s*at[eé]\s*"
    r"(?P<end>\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)
_CODE = r"\d+(?:\.\d+){9}"
_AMOUNT = r"-?(?:\d{1,3}(?:\.\d{3})*|\d+),\d{2}"
_ROW = re.compile(
    rf"^(?P<code>{_CODE})\s+(?P<description>.+?)\s+"
    rf"(?P<forecast>{_AMOUNT})\s+(?P<period>{_AMOUNT})\s+"
    rf"(?P<accumulated>{_AMOUNT})\s+(?P<more>{_AMOUNT})\s+"
    # Nos relatórios analíticos históricos o código de três dígitos da fonte
    # é extraído colado ao último valor (por exemplo, ``0,00010``). Ele é
    # evidência de desagregação da linha, mas o contrato público vigente é por
    # código de receita; por isso o código da fonte é reconhecido e descartado
    # somente depois que os valores foram separados sem ambiguidade.
    rf"(?P<less>{_AMOUNT})(?P<source_code>\d{{3}})?\s*$"
)
_TOTAL = re.compile(
    rf"^Total\s+da\s+Receita\s*:\s*"
    rf"(?P<forecast>{_AMOUNT})\s+(?P<period>{_AMOUNT})\s+"
    rf"(?P<accumulated>{_AMOUNT})"
    rf"(?:\s+(?P<more>{_AMOUNT})\s+(?P<less>{_AMOUNT}))?\s*$",
    re.IGNORECASE,
)


def _parse_date(value: str) -> date:
    day, month, year = (int(part) for part in value.split("/"))
    try:
        return date(year, month, day)
    except ValueError as error:
        raise RevenuePdfContractError(f"data invalida no relatorio: {value}") from error


def _amount(value: str) -> Decimal:
    if value.startswith("-"):
        return -parse_brl_amount(value[1:])
    return parse_brl_amount(value)


def parse_revenue_pdf_text(text: str) -> RevenuePdfReport:
    """Converte o texto extraido em linhas tipadas, sem ponto flutuante."""

    if not isinstance(text, str) or not text.strip():
        raise RevenuePdfContractError("texto do relatorio vazio")
    period = _DATE_RANGE.search(text)
    if period is None:
        raise RevenuePdfContractError("periodo do relatorio nao encontrado")
    period_start = _parse_date(period.group("start"))
    period_end = _parse_date(period.group("end"))
    if period_start > period_end:
        raise RevenuePdfContractError("inicio do periodo posterior ao fim")

    rows: list[RevenuePdfRow] = []
    row_index_by_code: dict[str, int] = {}
    total_match = None
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        total_match = total_match or _TOTAL.match(stripped)
        match = _ROW.match(stripped)
        if match is None:
            continue
        code = match.group("code")
        description = " ".join(match.group("description").split())
        if not description:
            raise RevenuePdfContractError(f"descricao vazia na linha {line_number}")
        parsed_row = RevenuePdfRow(
            revenue_code=code,
            description=description,
            forecast_amount=_amount(match.group("forecast")),
            period_amount=_amount(match.group("period")),
            accumulated_amount=_amount(match.group("accumulated")),
            difference_more=_amount(match.group("more")),
            difference_less=_amount(match.group("less")),
        )
        existing_index = row_index_by_code.get(code)
        if existing_index is None:
            row_index_by_code[code] = len(rows)
            rows.append(parsed_row)
            continue
        existing = rows[existing_index]
        if existing.description != description:
            raise RevenuePdfContractError(
                f"codigo de receita repetido com descricao divergente na linha "
                f"{line_number}: {code}"
            )
        rows[existing_index] = RevenuePdfRow(
            revenue_code=code,
            description=description,
            forecast_amount=existing.forecast_amount + parsed_row.forecast_amount,
            period_amount=existing.period_amount + parsed_row.period_amount,
            accumulated_amount=(
                existing.accumulated_amount + parsed_row.accumulated_amount
            ),
            difference_more=existing.difference_more + parsed_row.difference_more,
            difference_less=existing.difference_less + parsed_row.difference_less,
        )

    if not rows:
        raise RevenuePdfContractError("nenhuma linha de receita reconhecida")
    if total_match is None:
        raise RevenuePdfContractError("total declarado da receita nao encontrado")
    return RevenuePdfReport(
        period_start=period_start,
        period_end=period_end,
        fiscal_year=period_end.year,
        total_forecast_amount=_amount(total_match.group("forecast")),
        total_period_amount=_amount(total_match.group("period")),
        total_accumulated_amount=_amount(total_match.group("accumulated")),
        total_difference_more=_amount(total_match.group("more") or "0,00"),
        total_difference_less=_amount(total_match.group("less") or "0,00"),
        rows=tuple(rows),
    )
