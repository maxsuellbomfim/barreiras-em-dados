from __future__ import annotations

import unittest
from decimal import Decimal
from pathlib import Path

from barreiras_normalization.tcm_ba_expense_pdf import (
    TcmBaExpenseContractError,
    parse_tcm_ba_expense_pdf_text,
)

FIXTURE = (
    Path(__file__).parents[2]
    / "fixtures"
    / "documents"
    / "tcm-ba-analytical-expense-sample.txt"
)


class TcmBaExpensePdfTests(unittest.TestCase):
    def test_parses_exact_siga_report_with_multiline_description(self) -> None:
        report = parse_tcm_ba_expense_pdf_text(
            FIXTURE.read_text(encoding="utf-8")
        )

        self.assertEqual(report.period_start.isoformat(), "2023-04-01")
        self.assertEqual(report.period_end.isoformat(), "2023-04-30")
        self.assertEqual(report.fiscal_year, 2023)
        self.assertEqual(len(report.rows), 2)
        self.assertEqual(len(report.unit_totals), 1)
        self.assertEqual(report.rows[1].source_code, "1500")
        self.assertEqual(
            report.rows[1].description,
            "Outros Serviços de Terceiros - Pessoa Física",
        )
        self.assertEqual(report.rows[1].budget_unit_code, "1.3020")
        self.assertEqual(report.total_paid_period_amount, Decimal("10.00"))
        self.assertEqual(report.total_paid_to_date_amount, Decimal("30.00"))
        self.assertEqual(report.total_balance_amount, Decimal("45.00"))

    def test_rejects_a_missing_page_even_when_total_is_present(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8").replace(
            "Página 1 de 2 Despesa Orçamentária\n",
            "",
        )

        with self.assertRaisesRegex(
            TcmBaExpenseContractError,
            "sequência de páginas",
        ):
            parse_tcm_ba_expense_pdf_text(text)

    def test_accepts_source_code_joined_to_first_amount_by_pdf_layout(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8").replace(
            "1500 60,00 10,00",
            "150060,00 10,00",
            1,
        )

        report = parse_tcm_ba_expense_pdf_text(text)

        self.assertEqual(report.rows[0].source_code, "1500")
        self.assertEqual(report.rows[0].fixed_amount, Decimal("60.00"))

    def test_accepts_three_digit_source_codes_used_by_siga_in_2021(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8").replace("1500 ", "100 ")

        report = parse_tcm_ba_expense_pdf_text(text)

        self.assertEqual({row.source_code for row in report.rows}, {"100"})

    def test_resolves_joined_three_digit_source_from_document_evidence(self) -> None:
        text = (
            FIXTURE.read_text(encoding="utf-8")
            .replace("1500 ", "100 ")
            .replace("100 60,00 10,00", "10060,00 10,00", 1)
        )

        report = parse_tcm_ba_expense_pdf_text(text)

        self.assertEqual(report.rows[0].source_code, "100")
        self.assertEqual(report.rows[0].fixed_amount, Decimal("60.00"))

    def test_rejects_joined_source_without_unique_document_evidence(self) -> None:
        text = (
            FIXTURE.read_text(encoding="utf-8")
            .replace("1500 60,00 10,00", "10060,00 10,00", 1)
            .replace("1500 40,00", "200 40,00", 1)
        )

        with self.assertRaisesRegex(
            TcmBaExpenseContractError,
            "interpretação ambígua",
        ):
            parse_tcm_ba_expense_pdf_text(text)

    def test_rejects_another_municipality(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8").replace(
            "Prefeitura Municipal de BARREIRAS",
            "Prefeitura Municipal de SALVADOR",
        )

        with self.assertRaisesRegex(
            TcmBaExpenseContractError,
            "ente municipal",
        ):
            parse_tcm_ba_expense_pdf_text(text)

    def test_rejects_summary_that_disagrees_with_total_do_poder(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8").replace(
            "Saldo da Dotação: 45,00",
            "Saldo da Dotação: 44,99",
        )

        with self.assertRaisesRegex(
            TcmBaExpenseContractError,
            "resumo diverge",
        ):
            parse_tcm_ba_expense_pdf_text(text)

    def test_rejects_unit_subtotal_that_disagrees_with_rows(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8").replace(
            "Total da Unidade: 100,00",
            "Total da Unidade: 99,99",
        )

        with self.assertRaisesRegex(
            TcmBaExpenseContractError,
            "subtotal da unidade diverge",
        ):
            parse_tcm_ba_expense_pdf_text(text)

    def test_rejects_total_do_poder_that_disagrees_with_units(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8").replace(
            "Total do Poder: 100,00",
            "Total do Poder: 100,01",
        )

        with self.assertRaisesRegex(
            TcmBaExpenseContractError,
            "total do poder diverge",
        ):
            parse_tcm_ba_expense_pdf_text(text)


if __name__ == "__main__":
    unittest.main()
