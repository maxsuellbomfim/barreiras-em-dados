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
UNIT_TOTAL = (
    "1.401.257,00 43.300,00 219.492,00 1.225.065,00 40.500,00 "
    "1.225.037,00 109.465,46 417.983,96 115.995,62 405.440,48 "
    "819.596,52 28,00Total da Unidade :"
)


class FinancialExpensePdfTests(unittest.TestCase):
    def test_parses_period_rows_and_declared_total_without_float_conversion(self):
        report = parse_expense_pdf_text(FIXTURE.read_text(encoding="utf-8"))

        self.assertEqual(report.period_start.isoformat(), "2022-04-01")
        self.assertEqual(report.period_end.isoformat(), "2022-04-30")
        self.assertEqual(report.fiscal_year, 2022)
        self.assertEqual(len(report.rows), 3)
        self.assertEqual(report.total_updated_amount, Decimal("1225065.00"))
        self.assertEqual(
            report.total_paid_period_amount,
            Decimal("115995.62"),
        )
        self.assertEqual(report.rows[2].paid_to_date_amount, Decimal("405440.48"))
        self.assertEqual(report.rows[2].expense_code, "3.3.9.0.39.00.00")
        self.assertEqual(report.rows[2].budget_unit_code, "010101")
        self.assertEqual(
            report.rows[2].budget_unit_name,
            "CAMARA MUNICIPAL DE BARREIRAS",
        )

    def test_rejects_expense_row_without_preceding_budget_unit(self):
        text = FIXTURE.read_text(encoding="utf-8").replace(
            "010101 - CAMARA MUNICIPAL DE BARREIRAS\n",
            "",
        )

        with self.assertRaisesRegex(
            ExpensePdfContractError,
            "linha de despesa sem unidade orçamentária",
        ):
            parse_expense_pdf_text(text)

    def test_rejects_report_without_declared_total(self):
        text = FIXTURE.read_text(encoding="utf-8").replace("Total :", "Resumo :")

        with self.assertRaises(ExpensePdfContractError):
            parse_expense_pdf_text(text)

    def test_accepts_one_decimal_when_pdf_omits_trailing_zero(self):
        text = FIXTURE.read_text(encoding="utf-8").replace(
            "Total : 1.401.257,00",
            "Total : 1.401.257,0",
        )

        report = parse_expense_pdf_text(text)

        self.assertEqual(report.total_fixed_amount, Decimal("1401257.00"))

    def test_parses_adjacent_fonte_and_fonte_tc_codes_without_dropping_row(self):
        text = FIXTURE.read_text(encoding="utf-8").replace(
            "3.3.9.0.39.00.00. Outros Servicos Terceiros Pessoa 0100",
            "3.3.9.0.39.00.00. Outros Servicos Terceiros Pessoa 15001001",
        )

        report = parse_expense_pdf_text(text)

        self.assertEqual(len(report.rows), 3)
        self.assertEqual(report.rows[2].source_code, "15001001")

    def test_parses_source_code_joined_to_truncated_description(self):
        text = FIXTURE.read_text(encoding="utf-8").replace(
            "Outros Servicos Terceiros Pessoa 0100",
            "Outros Servicos Terceiros Pessoa15001001",
        )

        report = parse_expense_pdf_text(text)

        self.assertEqual(len(report.rows), 3)
        self.assertEqual(report.rows[2].description, "Outros Servicos Terceiros Pessoa")
        self.assertEqual(report.rows[2].source_code, "15001001")

    def test_preserves_official_budget_unit_subtotal(self):
        text = FIXTURE.read_text(encoding="utf-8").replace(
            "Total :",
            f"{UNIT_TOTAL}\nTotal :",
            1,
        )

        report = parse_expense_pdf_text(text)

        self.assertEqual(len(report.unit_totals), 1)
        self.assertEqual(report.unit_totals[0].budget_unit_code, "010101")
        self.assertEqual(
            report.unit_totals[0].reductions_amount,
            Decimal("219492.00"),
        )


if __name__ == "__main__":
    unittest.main()
