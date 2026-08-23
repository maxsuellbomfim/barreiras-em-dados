from __future__ import annotations

import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from barreiras_normalization.expense_publication import (
    EXPENSE_PUBLICATION_METHODOLOGY_VERSION,
    ExpensePublicationError,
    build_expense_publication_batch,
)
from barreiras_normalization.financial_expense_pdf import parse_expense_pdf_text

FIXTURE = (
    Path(__file__).parents[2]
    / "fixtures"
    / "documents"
    / "financial-expense-report-sample.txt"
)
UNIT_TOTAL = (
    "1.401.257,00 43.300,00 219.492,00 1.225.065,00 40.500,00 "
    "1.225.037,00 109.465,46 417.983,96 115.995,62 405.440,48 "
    "819.596,52 28,00Total da Unidade :"
)


class ExpensePublicationTests(unittest.TestCase):
    def test_publication_is_typed_and_deterministic(self):
        report = parse_expense_pdf_text(FIXTURE.read_text(encoding="utf-8"))

        first = build_expense_publication_batch(report)
        second = build_expense_publication_batch(report)

        self.assertEqual(first.batch_sha256, second.batch_sha256)
        self.assertEqual(
            first.methodology_version,
            EXPENSE_PUBLICATION_METHODOLOGY_VERSION,
        )
        self.assertEqual(first.total_paid_period_amount, Decimal("115995.62"))
        self.assertEqual(first.rows[0].line_number, 1)
        self.assertEqual(first.rows[0].budget_unit_code, "010101")
        self.assertEqual(
            first.rows[0].budget_unit_name,
            "CAMARA MUNICIPAL DE BARREIRAS",
        )
        self.assertEqual(len(first.batch_sha256), 64)
        self.assertEqual(first.total_source_conflicts, ())

    def test_rejects_report_when_recognized_lines_do_not_reconcile_total(self):
        report = parse_expense_pdf_text(FIXTURE.read_text(encoding="utf-8"))
        incomplete = replace(report, rows=report.rows[:-1])

        with self.assertRaisesRegex(
            ExpensePublicationError,
            "soma das linhas diverge do total declarado sem subtotais",
        ):
            build_expense_publication_batch(incomplete)

    def test_publishes_source_self_conflict_only_when_unit_subtotal_reconciles(self):
        text = FIXTURE.read_text(encoding="utf-8").replace(
            "Total :",
            f"{UNIT_TOTAL}\nTotal :",
            1,
        )
        text = text.replace(
            "Total : 1.401.257,00 43.300,00 219.492,00",
            "Total : 1.401.257,00 43.300,00 219.491,92",
            1,
        )

        batch = build_expense_publication_batch(parse_expense_pdf_text(text))

        self.assertEqual(len(batch.rows), 3)
        self.assertEqual(len(batch.total_source_conflicts), 1)
        conflict = batch.total_source_conflicts[0]
        self.assertEqual(conflict.field_name, "total_reductions_amount")
        self.assertEqual(conflict.declared_amount, Decimal("219491.92"))
        self.assertEqual(conflict.calculated_amount, Decimal("219492.00"))
        self.assertEqual(conflict.difference_amount, Decimal("0.08"))


if __name__ == "__main__":
    unittest.main()
