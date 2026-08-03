from __future__ import annotations

import unittest
from decimal import Decimal
from pathlib import Path

from barreiras_normalization.expense_publication import (
    EXPENSE_PUBLICATION_METHODOLOGY_VERSION,
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
        self.assertEqual(first.total_paid_period_amount, Decimal("53082371.88"))
        self.assertEqual(first.rows[0].line_number, 1)
        self.assertEqual(len(first.batch_sha256), 64)


if __name__ == "__main__":
    unittest.main()
