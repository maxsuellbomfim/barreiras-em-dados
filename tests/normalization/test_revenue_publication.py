from __future__ import annotations

import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from barreiras_normalization.financial_revenue_pdf import parse_revenue_pdf_text
from barreiras_normalization.revenue_publication import (
    PUBLICATION_METHODOLOGY_VERSION,
    RevenuePublicationError,
    build_publication_batch,
)

FIXTURE = (
    Path(__file__).parents[2]
    / "fixtures"
    / "documents"
    / "financial-revenue-report-sample.txt"
)


class RevenuePublicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.report = parse_revenue_pdf_text(FIXTURE.read_text(encoding="utf-8"))

    def test_publication_keeps_accumulated_amount_and_deduction_direction(self) -> None:
        batch = build_publication_batch(self.report)

        self.assertEqual(batch.rows[0].collected_amount, Decimal("106245940.88"))
        self.assertEqual(batch.rows[0].accumulated_amount, Decimal("532630204.77"))
        self.assertEqual(batch.total_period_amount, Decimal("97976757.57"))
        self.assertEqual(batch.rows[2].collection_direction, "deduction")
        self.assertEqual(batch.rows[2].collected_amount, Decimal("4071293.91"))
        self.assertEqual(batch.methodology_version, PUBLICATION_METHODOLOGY_VERSION)
        self.assertEqual(len(batch.batch_sha256), 64)

    def test_publication_rejects_positive_amount_in_deduction(self) -> None:
        row = replace(self.report.rows[2], period_amount=Decimal("1.00"))
        with self.assertRaises(RevenuePublicationError):
            build_publication_batch(replace(self.report, rows=(row,)))

    def test_publication_keeps_non_deduction_negative_adjustment(self) -> None:
        row = replace(
            self.report.rows[0],
            revenue_code="1.7.2.4.00.0.0.00.00.00",
            forecast_amount=Decimal("-88458.00"),
            period_amount=Decimal("-3776.33"),
            accumulated_amount=Decimal("-696223.67"),
        )
        batch = build_publication_batch(replace(self.report, rows=(row,)))

        self.assertEqual(batch.rows[0].collection_direction, "adjustment")
        self.assertEqual(batch.rows[0].collected_amount, Decimal("3776.33"))

    def test_publication_digest_is_deterministic(self) -> None:
        first = build_publication_batch(self.report)
        second = build_publication_batch(self.report)

        self.assertEqual(first.batch_sha256, second.batch_sha256)


if __name__ == "__main__":
    unittest.main()
