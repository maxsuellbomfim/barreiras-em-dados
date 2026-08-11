"""Extração determinística de obrigações reportadas em balancetes municipais.

O demonstrativo de despesa extra apresenta pagamentos de restos a pagar em
três colunas: acumulado até o mês anterior, pago no mês e acumulado até o mês.
No texto extraído de PDFs rotacionados, o trio é emitido na ordem visual
inversa. Este módulo apenas recompõe essa linha declarada e valida a identidade
aritmética; ele não calcula nem nomeia uma dívida total.
"""

from __future__ import annotations

import calendar
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .revenue import RevenueNormalizationError, parse_brl_amount


class PublicObligationPdfContractError(RevenueNormalizationError):
    """O balancete não contém uma linha inequívoca de restos a pagar."""


@dataclass(frozen=True)
class RestosAPagarSummary:
    fiscal_year: int
    period_start: date
    period_end: date
    obligation_type: str
    description: str
    payments_prior_amount: Decimal
    payments_period_amount: Decimal
    payments_to_date_amount: Decimal


_AMOUNT = r"(?:\d{1,3}(?:\.\d{3})*|\d+),\d{1,2}"
_TOTAL_LINE = re.compile(
    rf"^(?P<to_date>{_AMOUNT})\s+"
    rf"(?P<period>{_AMOUNT})\s+"
    rf"(?P<prior>{_AMOUNT})$"
)


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )
    return without_marks.upper()


def parse_restos_a_pagar_summary(
    text: str,
    *,
    fiscal_year: int,
    reference_month: int,
) -> RestosAPagarSummary:
    """Lê o total declarado da seção, usando Decimal e período informado pela API."""

    if not isinstance(text, str) or not text.strip():
        raise PublicObligationPdfContractError("texto do balancete vazio")
    if not 1988 <= fiscal_year <= 9999:
        raise PublicObligationPdfContractError("ano fiscal fora do intervalo permitido")
    if not 1 <= reference_month <= 12:
        raise PublicObligationPdfContractError("mes de referencia invalido")

    lines = [" ".join(line.split()) for line in text.splitlines()]
    folded = [_fold(line) for line in lines]
    headings = [index for index, line in enumerate(folded) if line == "RESTOS A PAGAR"]
    if len(headings) != 1:
        raise PublicObligationPdfContractError(
            "secao RESTOS A PAGAR ausente ou ambigua"
        )
    start = headings[0] + 1
    try:
        end = next(
            index
            for index in range(start, len(lines))
            if folded[index] == "TRANSFERENCIA FINANCEIRA"
        )
    except StopIteration as error:
        raise PublicObligationPdfContractError(
            "limite da secao RESTOS A PAGAR nao encontrado"
        ) from error

    candidates = [
        match
        for line in lines[start:end]
        if (match := _TOTAL_LINE.fullmatch(line)) is not None
    ]
    if not candidates:
        raise PublicObligationPdfContractError(
            "total de restos a pagar nao encontrado antes da proxima secao"
        )
    total = candidates[-1]
    payments_to_date = parse_brl_amount(total.group("to_date"))
    payments_period = parse_brl_amount(total.group("period"))
    payments_prior = parse_brl_amount(total.group("prior"))
    if payments_prior + payments_period != payments_to_date:
        raise PublicObligationPdfContractError(
            "total de restos a pagar nao fecha: anterior + mes diverge do acumulado"
        )

    period_start = date(fiscal_year, reference_month, 1)
    period_end = date(
        fiscal_year,
        reference_month,
        calendar.monthrange(fiscal_year, reference_month)[1],
    )
    return RestosAPagarSummary(
        fiscal_year=fiscal_year,
        period_start=period_start,
        period_end=period_end,
        obligation_type="restos_a_pagar_total",
        description="Pagamentos de restos a pagar informados no balancete mensal",
        payments_prior_amount=payments_prior,
        payments_period_amount=payments_period,
        payments_to_date_amount=payments_to_date,
    )
