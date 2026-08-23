"""Contrato publicável para demonstrativos municipais de despesas."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal

from .financial_expense_pdf import ExpensePdfReport, ExpensePdfRow
from .revenue import RevenueNormalizationError

EXPENSE_PUBLICATION_METHODOLOGY_VERSION = "public-expense-pdf/1.3.0"


class ExpensePublicationError(RevenueNormalizationError):
    """O relatório não cumpre os critérios mínimos de publicação."""


@dataclass(frozen=True)
class ExpensePublicationRow:
    line_number: int
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
class ExpenseTotalSourceConflict:
    field_name: str
    declared_amount: Decimal
    calculated_amount: Decimal
    difference_amount: Decimal


@dataclass(frozen=True)
class ExpensePublicationBatch:
    period_start: str
    period_end: str
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
    rows: tuple[ExpensePublicationRow, ...]
    total_source_conflicts: tuple[ExpenseTotalSourceConflict, ...]
    methodology_version: str
    batch_sha256: str


def _finite(value: Decimal, *, field: str) -> Decimal:
    if not value.is_finite():
        raise ExpensePublicationError(f"{field} não é finito")
    return value


_TOTAL_TO_ROW_FIELD = {
    "total_fixed_amount": "fixed_amount",
    "total_additions_amount": "additions_amount",
    "total_reductions_amount": "reductions_amount",
    "total_updated_amount": "updated_amount",
    "total_committed_period_amount": "committed_period_amount",
    "total_committed_to_date_amount": "committed_to_date_amount",
    "total_liquidated_period_amount": "liquidated_period_amount",
    "total_liquidated_to_date_amount": "liquidated_to_date_amount",
    "total_paid_period_amount": "paid_period_amount",
    "total_paid_to_date_amount": "paid_to_date_amount",
    "total_unpaid_committed_amount": "unpaid_committed_amount",
    "total_balance_amount": "balance_amount",
}


def _reconcile_report_totals(
    report: ExpensePdfReport,
    totals: dict[str, Decimal],
) -> tuple[ExpenseTotalSourceConflict, ...]:
    row_sums = {
        total_field: sum(
            (getattr(row, row_field) for row in report.rows),
            start=Decimal("0"),
        )
        for total_field, row_field in _TOTAL_TO_ROW_FIELD.items()
    }
    global_mismatches = {
        total_field
        for total_field, row_sum in row_sums.items()
        if row_sum != totals[total_field]
    }

    if report.unit_totals:
        totals_by_unit = {}
        for unit_total in report.unit_totals:
            key = (unit_total.budget_unit_code, unit_total.budget_unit_name)
            if key in totals_by_unit:
                raise ExpensePublicationError(
                    "unidade orçamentária possui mais de um subtotal oficial"
                )
            totals_by_unit[key] = unit_total
        rows_by_unit: dict[tuple[str, str], list[ExpensePdfRow]] = {}
        for row in report.rows:
            key = (row.budget_unit_code, row.budget_unit_name)
            rows_by_unit.setdefault(key, []).append(row)
        if set(totals_by_unit) != set(rows_by_unit):
            raise ExpensePublicationError(
                "subtotais oficiais não cobrem exatamente as unidades das linhas"
            )
        for key, unit_rows in rows_by_unit.items():
            unit_total = totals_by_unit[key]
            for _total_field, row_field in _TOTAL_TO_ROW_FIELD.items():
                unit_sum = sum(
                    (getattr(row, row_field) for row in unit_rows),
                    start=Decimal("0"),
                )
                if unit_sum != getattr(unit_total, row_field):
                    raise ExpensePublicationError(
                        "soma das linhas diverge do subtotal oficial da unidade: "
                        f"{key[0]} {row_field}"
                    )
    elif global_mismatches:
        total_field = sorted(global_mismatches)[0]
        row_field = _TOTAL_TO_ROW_FIELD[total_field]
        raise ExpensePublicationError(
            "soma das linhas diverge do total declarado sem subtotais "
            f"comprobatórios: {row_field}={row_sums[total_field]} "
            f"{total_field}={totals[total_field]}"
        )

    return tuple(
        ExpenseTotalSourceConflict(
            field_name=total_field,
            declared_amount=totals[total_field],
            calculated_amount=row_sums[total_field],
            difference_amount=row_sums[total_field] - totals[total_field],
        )
        for total_field in _TOTAL_TO_ROW_FIELD
        if total_field in global_mismatches
    )


def build_expense_publication_batch(
    report: ExpensePdfReport,
) -> ExpensePublicationBatch:
    totals = {
        "total_fixed_amount": _finite(
            report.total_fixed_amount, field="total_fixed_amount"
        ),
        "total_additions_amount": _finite(
            report.total_additions_amount, field="total_additions_amount"
        ),
        "total_reductions_amount": _finite(
            report.total_reductions_amount, field="total_reductions_amount"
        ),
        "total_updated_amount": _finite(
            report.total_updated_amount, field="total_updated_amount"
        ),
        "total_committed_period_amount": _finite(
            report.total_committed_period_amount,
            field="total_committed_period_amount",
        ),
        "total_committed_to_date_amount": _finite(
            report.total_committed_to_date_amount,
            field="total_committed_to_date_amount",
        ),
        "total_liquidated_period_amount": _finite(
            report.total_liquidated_period_amount,
            field="total_liquidated_period_amount",
        ),
        "total_liquidated_to_date_amount": _finite(
            report.total_liquidated_to_date_amount,
            field="total_liquidated_to_date_amount",
        ),
        "total_paid_period_amount": _finite(
            report.total_paid_period_amount, field="total_paid_period_amount"
        ),
        "total_paid_to_date_amount": _finite(
            report.total_paid_to_date_amount, field="total_paid_to_date_amount"
        ),
        "total_unpaid_committed_amount": _finite(
            report.total_unpaid_committed_amount,
            field="total_unpaid_committed_amount",
        ),
        "total_balance_amount": _finite(
            report.total_balance_amount, field="total_balance_amount"
        ),
    }
    if not report.rows:
        raise ExpensePublicationError("relatório sem linhas publicáveis")

    total_source_conflicts = _reconcile_report_totals(report, totals)

    rows: list[ExpensePublicationRow] = []
    for line_number, row in enumerate(report.rows, start=1):
        values = {
            "fixed_amount": _finite(row.fixed_amount, field="fixed_amount"),
            "additions_amount": _finite(row.additions_amount, field="additions_amount"),
            "reductions_amount": _finite(
                row.reductions_amount, field="reductions_amount"
            ),
            "updated_amount": _finite(row.updated_amount, field="updated_amount"),
            "committed_period_amount": _finite(
                row.committed_period_amount, field="committed_period_amount"
            ),
            "committed_to_date_amount": _finite(
                row.committed_to_date_amount, field="committed_to_date_amount"
            ),
            "liquidated_period_amount": _finite(
                row.liquidated_period_amount, field="liquidated_period_amount"
            ),
            "liquidated_to_date_amount": _finite(
                row.liquidated_to_date_amount, field="liquidated_to_date_amount"
            ),
            "paid_period_amount": _finite(
                row.paid_period_amount, field="paid_period_amount"
            ),
            "paid_to_date_amount": _finite(
                row.paid_to_date_amount, field="paid_to_date_amount"
            ),
            "unpaid_committed_amount": _finite(
                row.unpaid_committed_amount, field="unpaid_committed_amount"
            ),
            "balance_amount": _finite(row.balance_amount, field="balance_amount"),
        }
        rows.append(
            ExpensePublicationRow(
                line_number=line_number,
                budget_unit_code=row.budget_unit_code,
                budget_unit_name=row.budget_unit_name,
                expense_code=row.expense_code,
                description=row.description,
                source_code=row.source_code,
                **values,
            )
        )

    canonical = {
        "period_start": report.period_start.isoformat(),
        "period_end": report.period_end.isoformat(),
        "fiscal_year": report.fiscal_year,
        **{key: str(value) for key, value in totals.items()},
        "rows": [
            {
                "line_number": row.line_number,
                "budget_unit_code": row.budget_unit_code,
                "budget_unit_name": row.budget_unit_name,
                "expense_code": row.expense_code,
                "description": row.description,
                "source_code": row.source_code,
                **{
                    key: str(getattr(row, key))
                    for key in (
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
                },
            }
            for row in rows
        ],
        "total_source_conflicts": [
            {
                "field_name": conflict.field_name,
                "declared_amount": str(conflict.declared_amount),
                "calculated_amount": str(conflict.calculated_amount),
                "difference_amount": str(conflict.difference_amount),
            }
            for conflict in total_source_conflicts
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
    return ExpensePublicationBatch(
        period_start=report.period_start.isoformat(),
        period_end=report.period_end.isoformat(),
        fiscal_year=report.fiscal_year,
        **totals,
        rows=tuple(rows),
        total_source_conflicts=total_source_conflicts,
        methodology_version=EXPENSE_PUBLICATION_METHODOLOGY_VERSION,
        batch_sha256=digest,
    )
