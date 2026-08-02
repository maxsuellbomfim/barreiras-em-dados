"""Contrato determinístico para o resumo de execução da receita municipal.

The transparency API is preserved raw first. This module only turns a validated
fixture-shaped record into typed values; it does not publish totals or write to
PostgreSQL.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation


class RevenueNormalizationError(ValueError):
    """A record is missing a required field or has an ambiguous value."""


@dataclass(frozen=True)
class NormalizedRevenue:
    external_id: str
    fiscal_year: int
    revenue_date: date | None
    description: str
    collected_amount: Decimal
    currency: str = "BRL"


_YEAR_PATTERN = re.compile(r"^\d{4}$")
_AMOUNT_PATTERN = re.compile(r"^(?:\d{1,3}(?:\.\d{3})*|\d+)(?:,\d{1,2})?$")


def _required_text(record: Mapping[str, object], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise RevenueNormalizationError(f"{field} deve ser texto não vazio")
    return value.strip()


def _parse_year(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        year = value
    elif isinstance(value, str) and _YEAR_PATTERN.fullmatch(value.strip()):
        year = int(value.strip())
    else:
        raise RevenueNormalizationError("ano deve ser um ano fiscal com quatro dígitos")
    if not 1900 <= year <= 2200:
        raise RevenueNormalizationError("ano fiscal fora do intervalo permitido")
    return year


def _parse_date(value: object) -> date | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise RevenueNormalizationError("data deve estar no formato ISO YYYY-MM-DD")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as error:
        raise RevenueNormalizationError(
            "data deve estar no formato ISO YYYY-MM-DD"
        ) from error


def parse_brl_amount(value: object) -> Decimal:
    """Parse a non-negative Brazilian amount without binary floating point."""

    if not isinstance(value, str):
        raise RevenueNormalizationError("valor_arrecadado deve ser texto monetário")
    normalized = value.strip().replace("R$", "").replace(" ", "")
    if not _AMOUNT_PATTERN.fullmatch(normalized):
        raise RevenueNormalizationError(
            "valor_arrecadado deve usar moeda brasileira, por exemplo 1.234,56"
        )
    integer_part, separator, decimal_part = normalized.partition(",")
    canonical = integer_part.replace(".", "")
    if separator:
        canonical = f"{canonical}.{decimal_part.ljust(2, '0')}"
    try:
        amount = Decimal(canonical).quantize(Decimal("0.01"))
    except InvalidOperation as error:
        raise RevenueNormalizationError("valor_arrecadado não é numérico") from error
    if amount < 0:
        raise RevenueNormalizationError("receita não pode ser negativa")
    return amount


def normalize_revenue_record(record: Mapping[str, object]) -> NormalizedRevenue:
    """Normalize one observed ``pdc-resumo-execucao-da-receita`` row."""

    return NormalizedRevenue(
        external_id=_required_text(record, "id"),
        fiscal_year=_parse_year(record.get("ano")),
        revenue_date=_parse_date(record.get("data")),
        description=_required_text(record, "descricao"),
        collected_amount=parse_brl_amount(record.get("valor_arrecadado")),
    )


def normalize_revenue_page(
    payload: Mapping[str, object],
) -> tuple[NormalizedRevenue, ...]:
    """Validate the page envelope before normalizing any row."""

    if payload.get("resource") != "pdc-resumo-execucao-da-receita":
        raise RevenueNormalizationError(
            "resource não corresponde ao contrato de receita"
        )
    count = payload.get("count")
    rows = payload.get("data")
    if not isinstance(count, int) or count < 0 or not isinstance(rows, Sequence):
        raise RevenueNormalizationError(
            "count inteiro e data em lista são obrigatórios"
        )
    if isinstance(rows, (str, bytes)) or count != len(rows):
        raise RevenueNormalizationError("count deve representar a página retornada")
    normalized: list[NormalizedRevenue] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise RevenueNormalizationError(f"linha {index} deve ser um objeto")
        normalized.append(normalize_revenue_record(row))
    return tuple(normalized)
