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

    def test_rejects_report_when_recognized_lines_do_not_reconcile_total(self):
        report = parse_expense_pdf_text(FIXTURE.read_text(encoding="utf-8"))
        incomplete = replace(report, rows=report.rows[:-1])

        with self.assertRaisesRegex(
            ExpensePublicationError,
            "soma das linhas diverge do total declarado",
        ):
            build_expense_publication_batch(incomplete)


if __name__ == "__main__":
    unittest.main()
