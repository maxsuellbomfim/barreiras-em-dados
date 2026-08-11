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


class PublicObligationStructuralError(PublicObligationPdfContractError):
    """Estrutura ausente ou incompleta pode justificar uma nova extração."""


class PublicObligationSectionAbsentError(PublicObligationStructuralError):
    """O documento integral legível não contém o demonstrativo procurado."""


class PublicObligationArithmeticError(PublicObligationPdfContractError):
    """Valores declarados foram encontrados, mas não fecham aritmeticamente."""


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
    rf"^(?P<label>TOTAL\s+)?(?P<first>{_AMOUNT})\s+"
    rf"(?P<second>{_AMOUNT})\s+"
    rf"(?P<third>{_AMOUNT})$",
    re.IGNORECASE,
)
_AMOUNT_TOKEN = re.compile(_AMOUNT)
_TRANSFER_ACCOUNT = re.compile(r"^351\d{9,}")


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )
    return without_marks.upper()


def _closed_total(
    first: str,
    second: str,
    third: str,
) -> tuple[Decimal, Decimal, Decimal] | None:
    left = parse_brl_amount(first)
    middle = parse_brl_amount(second)
    right = parse_brl_amount(third)
    if left + middle == right:
        return left, middle, right
    if right + middle == left:
        return right, middle, left
    return None


def _interleaved_total_after_boundary(
    lines: list[str],
    folded: list[str],
    *,
    section_start: int,
    boundary: int,
) -> tuple[Decimal, Decimal, Decimal] | None:
    has_total_marker = any(
        folded[index] == "TOTAL"
        for index in range(max(section_start, boundary - 3), boundary)
    )
    if not has_total_marker:
        return None

    tokens: list[str] = []
    for index in range(boundary + 1, min(len(lines), boundary + 12)):
        if _TRANSFER_ACCOUNT.match(folded[index]):
            break
        tokens.extend(_AMOUNT_TOKEN.findall(lines[index]))
        if len(tokens) >= 6:
            break
    if len(tokens) < 6:
        return None

    candidates = [
        candidate
        for offset in (0, 1)
        if (
            candidate := _closed_total(
                tokens[offset], tokens[offset + 2], tokens[offset + 4]
            )
        )
        is not None
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: candidate[2])


def _columnar_total_before_boundary(
    lines: list[str],
    folded: list[str],
    *,
    section_start: int,
    boundary: int,
) -> tuple[Decimal, Decimal, Decimal] | None:
    """Reconstrói o total quando o PDF exporta cada coluna em um bloco.

    Alguns balancetes rotacionados emitem primeiro todas as descrições, depois
    todos os valores da coluna anterior, todos os valores do mês e, por fim,
    todos os acumulados. O acumulado total é o último valor antes da próxima
    seção. Aceitamos somente quando existe um marcador ``Total`` e há uma única
    dupla ordenada cuja soma fecha exatamente nesse último valor.
    """
    total_markers = [
        index
        for index in range(section_start, boundary)
        if folded[index] == "TOTAL"
    ]
    if len(total_markers) != 1:
        return None

    tokens = [
        token
        for line in lines[total_markers[0] + 1 : boundary]
        for token in _AMOUNT_TOKEN.findall(line)
    ]
    if len(tokens) < 3:
        return None

    values = [parse_brl_amount(token) for token in tokens]
    accumulated = values[-1]
    matches = [
        (prior, period, accumulated)
        for prior_index, prior in enumerate(values[:-2])
        for period in values[prior_index + 1 : -1]
        if prior + period == accumulated
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def parse_restos_a_pagar_summary(
    text: str,
    *,
    fiscal_year: int,
    reference_month: int,
) -> RestosAPagarSummary:
    """Lê o total declarado da seção, usando Decimal e período informado pela API."""

    if not isinstance(text, str) or not text.strip():
        raise PublicObligationStructuralError("texto do balancete vazio")
    if not 1988 <= fiscal_year <= 9999:
        raise PublicObligationStructuralError("ano fiscal fora do intervalo permitido")
    if not 1 <= reference_month <= 12:
        raise PublicObligationStructuralError("mes de referencia invalido")

    lines = [" ".join(line.split()) for line in text.splitlines()]
    folded = [_fold(line) for line in lines]
    headings = [index for index, line in enumerate(folded) if line == "RESTOS A PAGAR"]
    if len(headings) != 1:
        raise PublicObligationStructuralError(
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
        raise PublicObligationStructuralError(
            "limite da secao RESTOS A PAGAR nao encontrado"
        ) from error

    candidates = [
        match
        for line in lines[start:end]
        if (match := _TOTAL_LINE.fullmatch(line)) is not None
    ]
    total_values: tuple[Decimal, Decimal, Decimal] | None = None
    if candidates:
        explicit = [match for match in candidates if match.group("label")]
        total = explicit[-1] if explicit else candidates[-1]
        total_values = _closed_total(
            total.group("first"),
            total.group("second"),
            total.group("third"),
        )
        if total_values is None:
            raise PublicObligationArithmeticError(
                "total de restos a pagar nao fecha: anterior + mes diverge do acumulado"
            )
    else:
        total_values = _interleaved_total_after_boundary(
            lines,
            folded,
            section_start=start,
            boundary=end,
        )
        if total_values is None:
            total_values = _columnar_total_before_boundary(
                lines,
                folded,
                section_start=start,
                boundary=end,
            )
    if total_values is None:
        raise PublicObligationStructuralError(
            "total de restos a pagar nao encontrado antes da proxima secao"
        )
    payments_prior, payments_period, payments_to_date = total_values

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
