import json
import unittest
from decimal import Decimal
from pathlib import Path

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
