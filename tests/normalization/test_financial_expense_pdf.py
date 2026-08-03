from __future__ import annotations

import unittest
from decimal import Decimal
from pathlib import Path

from barreiras_normalization.financial_expense_pdf import (
    ExpensePdfContractError,
    parse_expense_pdf_text,
)


FIXTURE = (
    Path(__file__).parents[2]
    / "fixtures"
    / "documents"
    / "financial-expense-report-sample.txt"
)


class FinancialExpensePdfTests(unittest.TestCase):
    def test_parses_period_rows_and_declared_total_without_float_conversion(self):
        report = parse_expense_pdf_text(FIXTURE.read_text(encoding="utf-8"))

        self.assertEqual(report.period_start.isoformat(), "2022-04-01")
        self.assertEqual(report.period_end.isoformat(), "2022-04-30")
        self.assertEqual(report.fiscal_year, 2022)
        self.assertEqual(len(report.rows), 3)
        self.assertEqual(report.total_updated_amount, Decimal("595221834.00"))
        self.assertEqual(
            report.total_paid_period_amount,
            Decimal("53082371.88"),
        )
        self.assertEqual(report.rows[2].paid_to_date_amount, Decimal("405440.48"))
        self.assertEqual(report.rows[2].expense_code, "3.3.9.0.39.00.00")

    def test_rejects_report_without_declared_total(self):
        text = FIXTURE.read_text(encoding="utf-8").replace("Total :", "Resumo :")

        with self.assertRaises(ExpensePdfContractError):
            parse_expense_pdf_text(text)


if __name__ == "__main__":
    unittest.main()
