"""Parser fail-closed do demonstrativo analítico de receita do SIGA/TCM-BA."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .financial_revenue_pdf import RevenuePdfReport, RevenuePdfRow
from .revenue import RevenueNormalizationError, parse_brl_amount


class TcmBaRevenueContractError(RevenueNormalizationError):
    """O texto não comprova o contrato do demonstrativo SIGA esperado."""


_AMOUNT = r"-?(?:\d{1,3}(?:\.\d{3})*|\d+),\d{1,2}"
_SIX_AMOUNTS = rf"(?P<amounts>{_AMOUNT}(?:\s+{_AMOUNT}){{5}})"
_ENTITY = re.compile(
    r"^Unidade:\s*(?P<entity>.+?)\s*$",
    re.IGNORECASE,
)
_COMPETENCE = re.compile(
    r"^Compet.ncia:\s*(?P<month>\d{2})/(?P<year>\d{4})\s*$",
    re.IGNORECASE,
)
_PAGE = re.compile(
    r"^P.gina\s+(?P<number>\d+)\s+de\s+(?P<total>\d+)\b",
    re.IGNORECASE,
)
_REVENUE_CODE = r"\d+(?:\.\d+){8}"
_ROW_START = re.compile(
    rf"^(?P<code>{_REVENUE_CODE})\s+{_SIX_AMOUNTS}"
    r"\s*(?P<description>.+)$"
)
_SEVENTH_AMOUNT = re.compile(rf"^(?P<amount>{_AMOUNT})$")
_TOTAL = re.compile(rf"^{_SIX_AMOUNTS}\s*TOTAL$", re.IGNORECASE)
_SUMMARY_TOTALS = re.compile(
    rf"^Totais:\s*(?P<period>{_AMOUNT})\s+"
    rf"(?P<accumulated>{_AMOUNT})\s*$",
    re.IGNORECASE,
)
_TOP_LEVEL_CODE = re.compile(r"^[1-9]\.0\.0\.0\.00\.0\.0\.00\.00$")


@dataclass(frozen=True)
class _RawRevenueRow:
    published: RevenuePdfRow
    values: tuple[Decimal, ...]


def _amount(value: str) -> Decimal:
    sign = Decimal("-1") if value.startswith("-") else Decimal("1")
    return sign * parse_brl_amount(value.removeprefix("-"))


def _amounts(value: str, *, field: str, expected: int) -> tuple[Decimal, ...]:
    parsed = tuple(_amount(item) for item in value.split())
    if len(parsed) != expected:
        raise TcmBaRevenueContractError(
            f"{field} deve conter {expected} valores"
        )
    return parsed


def _validate_pages_and_period(text: str) -> tuple[date, date]:
    lines = [" ".join(line.split()) for line in text.splitlines()]
    pages = [match for line in lines if (match := _PAGE.match(line))]
    if not pages:
        raise TcmBaRevenueContractError("sequência de páginas não encontrada")
    totals = {int(match.group("total")) for match in pages}
    if len(totals) != 1:
        raise TcmBaRevenueContractError("sequência de páginas possui totais distintos")
    total_pages = totals.pop()
    if [int(match.group("number")) for match in pages] != list(
        range(1, total_pages + 1)
    ):
        raise TcmBaRevenueContractError("sequência de páginas está incompleta")

    entities = [match for line in lines if (match := _ENTITY.match(line))]
    if len(entities) != total_pages:
        raise TcmBaRevenueContractError(
            "cada página deve identificar o ente municipal"
        )
    entity_names = {
        " ".join(match.group("entity").upper().split()) for match in entities
    }
    if entity_names != {"PREFEITURA MUNICIPAL DE BARREIRAS"}:
        raise TcmBaRevenueContractError("ente municipal não corresponde a Barreiras")

    periods = [match for line in lines if (match := _COMPETENCE.match(line))]
    if len(periods) != total_pages:
        raise TcmBaRevenueContractError(
            "cada página deve identificar a competência"
        )
    values = {
        (int(match.group("year")), int(match.group("month")))
        for match in periods
    }
    if len(values) != 1:
        raise TcmBaRevenueContractError("competência diverge entre as páginas")
    year, month = values.pop()
    try:
        last_day = calendar.monthrange(year, month)[1]
    except calendar.IllegalMonthError as error:
        raise TcmBaRevenueContractError("competência mensal inválida") from error
    return date(year, month, 1), date(year, month, last_day)


def _build_row(
    *,
    code: str,
    description_parts: list[str],
    first_values: tuple[Decimal, ...],
    annulled_to_date: Decimal,
) -> _RawRevenueRow:
    description = " ".join(" ".join(description_parts).split())
    if not description:
        raise TcmBaRevenueContractError(f"descrição vazia na rubrica {code}")
    if "\ufffd" in description:
        raise TcmBaRevenueContractError(f"descrição corrompida na rubrica {code}")
    values = (*first_values, annulled_to_date)
    forecast, collected, annulled, accumulated, more, less, annulled_total = values
    net_accumulated = accumulated - annulled_total
    if more < 0 or less < 0 or (more > 0 and less > 0):
        raise TcmBaRevenueContractError(f"saldo da rubrica {code} é inválido")
    if more - less != net_accumulated - forecast:
        raise TcmBaRevenueContractError(f"saldo da rubrica {code} não fecha")
    return _RawRevenueRow(
        published=RevenuePdfRow(
            revenue_code=code,
            description=description,
            forecast_amount=forecast,
            period_amount=collected - annulled,
            accumulated_amount=net_accumulated,
            difference_more=more,
            difference_less=less,
        ),
        values=values,
    )


def parse_tcm_ba_revenue_pdf_text(text: str) -> RevenuePdfReport:
    """Extrai o PCMGE016 somente quando páginas, rubricas e totais fecham."""

    if not isinstance(text, str) or not text.strip():
        raise TcmBaRevenueContractError("texto do demonstrativo vazio")
    period_start, period_end = _validate_pages_and_period(text)
    rows: list[_RawRevenueRow] = []
    seen_codes: set[str] = set()
    pending_code: str | None = None
    pending_values: tuple[Decimal, ...] = ()
    pending_description: list[str] = []
    total: tuple[Decimal, ...] | None = None
    summary_totals: tuple[Decimal, Decimal] | None = None

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = " ".join(line.split())
        if not stripped:
            continue
        row_match = _ROW_START.match(stripped)
        if row_match is not None:
            if pending_code is not None:
                raise TcmBaRevenueContractError(
                    f"rubrica {pending_code} não possui o sétimo valor "
                    f"antes da linha {line_number}"
                )
            pending_code = row_match.group("code")
            if pending_code in seen_codes:
                raise TcmBaRevenueContractError(
                    f"código de receita duplicado: {pending_code}"
                )
            pending_values = _amounts(
                row_match.group("amounts"),
                field=f"rubrica na linha {line_number}",
                expected=6,
            )
            pending_description = [row_match.group("description").strip()]
            continue

        seventh_match = _SEVENTH_AMOUNT.match(stripped)
        if pending_code is not None and seventh_match is not None:
            raw_row = _build_row(
                code=pending_code,
                description_parts=pending_description,
                first_values=pending_values,
                annulled_to_date=_amount(seventh_match.group("amount")),
            )
            rows.append(raw_row)
            seen_codes.add(pending_code)
            pending_code = None
            pending_values = ()
            pending_description = []
            continue

        total_match = _TOTAL.match(stripped)
        if total_match is not None:
            if pending_code is not None or total is not None:
                raise TcmBaRevenueContractError("total geral duplicado ou incompleto")
            total = _amounts(
                total_match.group("amounts"), field="total geral", expected=6
            )
            continue

        summary_match = _SUMMARY_TOTALS.match(stripped)
        if summary_match is not None:
            if summary_totals is not None:
                raise TcmBaRevenueContractError("Totais do resumo duplicados")
            summary_totals = (
                _amount(summary_match.group("period")),
                _amount(summary_match.group("accumulated")),
            )
            continue

        if pending_code is not None:
            if _PAGE.match(stripped) or _ENTITY.match(stripped) or _COMPETENCE.match(
                stripped
            ):
                raise TcmBaRevenueContractError(
                    f"rubrica {pending_code} atravessa um limite estrutural"
                )
            pending_description.append(stripped)
            if len(pending_description) > 6:
                raise TcmBaRevenueContractError(
                    f"descrição da rubrica {pending_code} excede o limite seguro"
                )

    if pending_code is not None:
        raise TcmBaRevenueContractError(
            f"rubrica {pending_code} não possui o sétimo valor"
        )
    if not rows:
        raise TcmBaRevenueContractError("nenhuma rubrica analítica reconhecida")
    if total is None:
        raise TcmBaRevenueContractError("total geral não encontrado")
    if summary_totals is None:
        raise TcmBaRevenueContractError("Totais do resumo não encontrados")

    top_level = [
        row
        for row in rows
        if _TOP_LEVEL_CODE.match(row.published.revenue_code)
    ]
    if not top_level:
        raise TcmBaRevenueContractError("categorias de primeiro nível não encontradas")
    top_sums = tuple(
        sum((row.values[index] for row in top_level), start=Decimal("0"))
        for index in range(7)
    )
    if top_sums[:6] != total:
        raise TcmBaRevenueContractError(
            "total geral diverge das categorias de primeiro nível"
        )
    if summary_totals != (total[1], total[3]):
        raise TcmBaRevenueContractError("Totais do resumo divergem do total geral")

    return RevenuePdfReport(
        period_start=period_start,
        period_end=period_end,
        fiscal_year=period_end.year,
        total_forecast_amount=total[0],
        total_period_amount=total[1] - total[2],
        total_accumulated_amount=total[3] - top_sums[6],
        total_difference_more=total[4],
        total_difference_less=total[5],
        rows=tuple(row.published for row in rows),
    )
