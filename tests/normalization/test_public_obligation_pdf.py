from __future__ import annotations

import unittest
from decimal import Decimal
from pathlib import Path

from barreiras_normalization.public_obligation_pdf import (
    PublicObligationPdfContractError,
    parse_restos_a_pagar_summary,
)

FIXTURE = (
    Path(__file__).parents[2]
    / "fixtures"
    / "documents"
    / "restos-a-pagar-summary-sample.txt"
)


class PublicObligationPdfTests(unittest.TestCase):
    def test_parses_declared_month_and_accumulated_payments_as_decimals(self):
        summary = parse_restos_a_pagar_summary(
            FIXTURE.read_text(encoding="utf-8"),
            fiscal_year=2026,
            reference_month=6,
        )

        self.assertEqual(summary.obligation_type, "restos_a_pagar_total")
        self.assertEqual(summary.period_start.isoformat(), "2026-06-01")
        self.assertEqual(summary.period_end.isoformat(), "2026-06-30")
        self.assertEqual(summary.payments_prior_amount, Decimal("45364644.06"))
        self.assertEqual(summary.payments_period_amount, Decimal("3683221.97"))
        self.assertEqual(summary.payments_to_date_amount, Decimal("49047866.03"))

    def test_rejects_total_whose_declared_arithmetic_does_not_close(self):
        text = FIXTURE.read_text(encoding="utf-8").replace(
            "49.047.866,03 3.683.221,97 45.364.644,06",
            "49.047.866,04 3.683.221,97 45.364.644,06",
        )

        with self.assertRaisesRegex(
            PublicObligationPdfContractError,
            "nao fecha",
        ):
            parse_restos_a_pagar_summary(
                text,
                fiscal_year=2026,
                reference_month=6,
            )

    def test_does_not_capture_transfer_total_after_section_boundary(self):
        text = FIXTURE.read_text(encoding="utf-8").replace(
            "49.047.866,03 3.683.221,97 45.364.644,06\n",
            "",
        )
        text = text.replace("8.159.912,08 0,00 8.159.912,08\n", "")
        text = text.replace("68.110,80 0,00 68.110,80\n", "")

        with self.assertRaisesRegex(
            PublicObligationPdfContractError,
            "total de restos a pagar",
        ):
            parse_restos_a_pagar_summary(
                text,
                fiscal_year=2026,
                reference_month=6,
            )


if __name__ == "__main__":
    unittest.main()
