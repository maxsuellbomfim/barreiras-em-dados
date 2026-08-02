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
        self.assertEqual(batch.rows[2].collection_direction, "deduction")
        self.assertEqual(batch.rows[2].collected_amount, Decimal("4071293.91"))
        self.assertEqual(batch.methodology_version, PUBLICATION_METHODOLOGY_VERSION)
        self.assertEqual(len(batch.batch_sha256), 64)

    def test_publication_rejects_positive_amount_in_deduction(self) -> None:
        row = replace(self.report.rows[2], period_amount=Decimal("1.00"))
        with self.assertRaises(RevenuePublicationError):
            build_publication_batch(replace(self.report, rows=(row,)))

    def test_publication_digest_is_deterministic(self) -> None:
        first = build_publication_batch(self.report)
        second = build_publication_batch(self.report)

        self.assertEqual(first.batch_sha256, second.batch_sha256)


if __name__ == "__main__":
    unittest.main()
