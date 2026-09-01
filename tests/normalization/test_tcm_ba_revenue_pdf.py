from __future__ import annotations

import unittest
from decimal import Decimal
from pathlib import Path

from barreiras_normalization.tcm_ba_revenue_pdf import (
    TcmBaRevenueContractError,
    parse_tcm_ba_revenue_pdf_text,
)

FIXTURE = (
    Path(__file__).parents[2]
    / "fixtures"
    / "documents"
    / "tcm-ba-analytical-revenue-sample.txt"
)


class TcmBaRevenuePdfTests(unittest.TestCase):
    def test_parses_exact_siga_report_and_applies_signed_annulments(self) -> None:
        report = parse_tcm_ba_revenue_pdf_text(
            FIXTURE.read_text(encoding="utf-8")
        )

        self.assertEqual(report.period_start.isoformat(), "2021-02-01")
        self.assertEqual(report.period_end.isoformat(), "2021-02-28")
        self.assertEqual(report.fiscal_year, 2021)
        self.assertEqual(len(report.rows), 2)
        self.assertEqual(report.rows[0].period_amount, Decimal("45849799.31"))
        self.assertEqual(report.rows[0].accumulated_amount, Decimal("104918433.62"))
        self.assertEqual(report.rows[1].description, "Receitas de Capital")
        self.assertEqual(report.total_forecast_amount, Decimal("514717532.00"))
        self.assertEqual(report.total_period_amount, Decimal("45849799.31"))
        self.assertEqual(report.total_accumulated_amount, Decimal("110933618.91"))

    def test_rejects_missing_page(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8").replace(
            "Página 1 de 2 Receita Orçamentária\n",
            "",
        )

        with self.assertRaisesRegex(
            TcmBaRevenueContractError,
            "sequência de páginas",
        ):
            parse_tcm_ba_revenue_pdf_text(text)

    def test_rejects_another_municipality(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8").replace(
            "Prefeitura Municipal de BARREIRAS",
            "Prefeitura Municipal de SALVADOR",
        )

        with self.assertRaisesRegex(TcmBaRevenueContractError, "ente municipal"):
            parse_tcm_ba_revenue_pdf_text(text)

    def test_rejects_top_level_sum_that_disagrees_with_total(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8").replace(
            "514.717.532,00 46.633.582,13 -783.782,82 111.717.401,73 "
            "0,00 403.783.913,09TOTAL",
            "514.717.533,00 46.633.582,13 -783.782,82 111.717.401,73 "
            "0,00 403.783.913,09TOTAL",
        )

        with self.assertRaisesRegex(TcmBaRevenueContractError, "total geral"):
            parse_tcm_ba_revenue_pdf_text(text)

    def test_rejects_positive_annulment_in_signed_tcm_layout(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8").replace(
            "470.041.355,00 46.633.582,13 -783.782,82 105.702.216,44 "
            "0,00 365.122.921,38Receitas Correntes",
            "470.041.355,00 46.633.582,13 783.782,82 105.702.216,44 "
            "0,00 365.122.921,38Receitas Correntes",
        )

        with self.assertRaisesRegex(TcmBaRevenueContractError, "anulação"):
            parse_tcm_ba_revenue_pdf_text(text)

    def test_rejects_row_balance_equation_violation(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8").replace(
            "0,00 365.122.921,38Receitas Correntes",
            "0,00 365.122.921,37Receitas Correntes",
        )

        with self.assertRaisesRegex(TcmBaRevenueContractError, "saldo da rubrica"):
            parse_tcm_ba_revenue_pdf_text(text)

    def test_rejects_corrupted_description(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8").replace(
            "Receitas Correntes",
            "Receitas Corr�ntes",
        )

        with self.assertRaisesRegex(TcmBaRevenueContractError, "descrição corrompida"):
            parse_tcm_ba_revenue_pdf_text(text)


if __name__ == "__main__":
    unittest.main()
