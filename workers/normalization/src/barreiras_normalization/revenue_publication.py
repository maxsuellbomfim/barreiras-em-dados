"""Contrato publicável para linhas do demonstrativo municipal de receitas."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from .financial_revenue_pdf import RevenuePdfReport
from .revenue import RevenueNormalizationError

PUBLICATION_METHODOLOGY_VERSION = "public-revenue-pdf/1.0.0"
CollectionDirection = Literal["credit", "deduction"]


class RevenuePublicationError(RevenueNormalizationError):
    """O relatório não cumpre os critérios mínimos de publicação automática."""


@dataclass(frozen=True)
class RevenuePublicationRow:
    revenue_code: str
    description: str
    collection_direction: CollectionDirection
    forecast_amount: Decimal
    collected_amount: Decimal
    accumulated_amount: Decimal
    difference_more: Decimal
    difference_less: Decimal


@dataclass(frozen=True)
class RevenuePublicationBatch:
    period_start: str
    period_end: str
    fiscal_year: int
    total_period_amount: Decimal
    rows: tuple[RevenuePublicationRow, ...]
    methodology_version: str
    batch_sha256: str


def _finite(value: Decimal, *, field: str) -> Decimal:
    if not value.is_finite():
        raise RevenuePublicationError(f"{field} não é finito")
    return value


def _magnitude(
    value: Decimal,
    *,
    direction: CollectionDirection,
    field: str,
) -> Decimal:
    value = _finite(value, field=field)
    if direction == "credit" and value < 0:
        raise RevenuePublicationError(f"{field} negativo em linha de crédito")
    if direction == "deduction" and value > 0:
        raise RevenuePublicationError(f"{field} positivo em linha de dedução")
    return abs(value)


def _absolute_component(value: Decimal, *, field: str) -> Decimal:
    return abs(_finite(value, field=field))


def build_publication_batch(report: RevenuePdfReport) -> RevenuePublicationBatch:
    """Converte o relatório em magnitudes publicáveis sem usar ponto flutuante."""

    total_period = _finite(report.total_period_amount, field="total_period_amount")
    rows: list[RevenuePublicationRow] = []
    seen_codes: set[str] = set()
    for row in report.rows:
        if row.revenue_code in seen_codes:
            raise RevenuePublicationError(
                f"código de receita repetido: {row.revenue_code}"
            )
        seen_codes.add(row.revenue_code)
        direction: CollectionDirection = (
            "deduction" if row.revenue_code.startswith("9.") else "credit"
        )
        rows.append(
            RevenuePublicationRow(
                revenue_code=row.revenue_code,
                description=row.description,
                collection_direction=direction,
                forecast_amount=_magnitude(
                    row.forecast_amount,
                    direction=direction,
                    field="forecast_amount",
                ),
                collected_amount=_magnitude(
                    row.period_amount,
                    direction=direction,
                    field="period_amount",
                ),
                accumulated_amount=_magnitude(
                    row.accumulated_amount,
                    direction=direction,
                    field="accumulated_amount",
                ),
                difference_more=_absolute_component(
                    row.difference_more, field="difference_more"
                ),
                difference_less=_absolute_component(
                    row.difference_less, field="difference_less"
                ),
            )
        )
    if not rows:
        raise RevenuePublicationError("relatório sem linhas publicáveis")
    canonical = {
        "period_start": report.period_start.isoformat(),
        "period_end": report.period_end.isoformat(),
        "fiscal_year": report.fiscal_year,
        "total_period_amount": str(total_period),
        "rows": [
            {
                "revenue_code": row.revenue_code,
                "description": row.description,
                "collection_direction": row.collection_direction,
                "forecast_amount": str(row.forecast_amount),
                "collected_amount": str(row.collected_amount),
                "accumulated_amount": str(row.accumulated_amount),
                "difference_more": str(row.difference_more),
                "difference_less": str(row.difference_less),
            }
            for row in rows
        ],
    }
    digest = hashlib.sha256(
        json.dumps(
            canonical,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return RevenuePublicationBatch(
        period_start=report.period_start.isoformat(),
        period_end=report.period_end.isoformat(),
        fiscal_year=report.fiscal_year,
        total_period_amount=total_period,
        rows=tuple(rows),
        methodology_version=PUBLICATION_METHODOLOGY_VERSION,
        batch_sha256=digest,
    )
