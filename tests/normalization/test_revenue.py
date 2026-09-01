import json
import unittest
from decimal import Decimal
from pathlib import Path

from barreiras_normalization.financial_revenue_pdf import (
    RevenuePdfContractError,
    parse_revenue_pdf_text,
)
from barreiras_normalization.revenue import (
    RevenueNormalizationError,
    normalize_revenue_page,
    parse_brl_amount,
)

FIXTURE = (
    Path(__file__).parents[2]
    / "fixtures"
    / "sources"
    / "prefeitura-transparencia"
    / "pdc-resumo-execucao-da-receita-page.json"
)


class RevenueNormalizationTests(unittest.TestCase):
    def test_financial_pdf_rows_are_parsed_without_float_conversion(self):
        text = (
            Path(__file__).parents[2]
            / "fixtures"
            / "documents"
            / "financial-revenue-report-sample.txt"
        ).read_text(encoding="utf-8")

        report = parse_revenue_pdf_text(text)

        self.assertEqual(report.fiscal_year, 2026)
        self.assertEqual(report.period_end.isoformat(), "2026-06-30")
        self.assertEqual(len(report.rows), 3)
        self.assertEqual(report.total_period_amount, Decimal("97976757.57"))
        self.assertEqual(report.rows[0].accumulated_amount, Decimal("532630204.77"))
        self.assertEqual(report.rows[2].accumulated_amount, Decimal("-21879379.30"))

    def test_financial_pdf_rejects_duplicate_codes(self):
        text = (
            "Data: De 01/06/2026 até 30/06/2026\n"
            "1.0.0.0.00.0.0.00.00.00 A 1,00 1,00 1,00 0,00 0,00\n"
            "1.0.0.0.00.0.0.00.00.00 B 1,00 1,00 1,00 0,00 0,00\n"
        )
        with self.assertRaises(RevenuePdfContractError):
            parse_revenue_pdf_text(text)

    def test_financial_pdf_aggregates_historical_rows_split_by_source(self):
        text = (
            "Data: De 01/12/2022 até 31/12/2022\n"
            "1.2.4.1.50.0.0.00.00.00 Contribuição para iluminação "
            "100,00 10,00 20,00 0,00 80,00010\n"
            "1.2.4.1.50.0.0.00.00.00 Contribuição para iluminação "
            "50,00 5,00 10,00 0,00 40,00019\n"
            "9.7.1.1.51.1.1.00.00.00 Dedução do FUNDEB "
            "-30,00 -3,00 -6,00 -36,00 0,00010\n"
            "Total da Receita : 120,00 12,00 24,00\n"
        )

        report = parse_revenue_pdf_text(text)

        self.assertEqual(len(report.rows), 2)
        self.assertEqual(report.rows[0].revenue_code, "1.2.4.1.50.0.0.00.00.00")
        self.assertEqual(report.rows[0].forecast_amount, Decimal("150.00"))
        self.assertEqual(report.rows[0].period_amount, Decimal("15.00"))
        self.assertEqual(report.rows[0].accumulated_amount, Decimal("30.00"))
        self.assertEqual(report.rows[0].difference_less, Decimal("120.00"))
        self.assertEqual(report.total_period_amount, Decimal("12.00"))

    def test_financial_pdf_requires_declared_total(self):
        text = (
            "Data: De 01/06/2026 até 30/06/2026\n"
            "1.0.0.0.00.0.0.00.00.00 A 1,00 1,00 1,00 0,00 0,00\n"
        )
        with self.assertRaises(RevenuePdfContractError):
            parse_revenue_pdf_text(text)

    def test_sanitized_fixture_is_typed_without_float_conversion(self):
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

        rows = normalize_revenue_page(payload)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].fiscal_year, 2026)
        self.assertEqual(rows[0].collected_amount, Decimal("0.00"))
        self.assertEqual(rows[0].revenue_date.isoformat(), "2026-07-01")

    def test_brazilian_amounts_are_exact(self):
        self.assertEqual(parse_brl_amount("1.234,5"), Decimal("1234.50"))
        self.assertEqual(parse_brl_amount("R$ 9.999,99"), Decimal("9999.99"))

    def test_ambiguous_amount_is_rejected(self):
        with self.assertRaises(RevenueNormalizationError):
            parse_brl_amount("1234.567")

    def test_page_count_mismatch_is_rejected(self):
        payload = {
            "resource": "pdc-resumo-execucao-da-receita",
            "count": 2,
            "data": [],
        }
        with self.assertRaises(RevenueNormalizationError):
            normalize_revenue_page(payload)
