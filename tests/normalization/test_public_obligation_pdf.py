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

    def test_parses_total_prefixed_line_from_march_balancete(self):
        text = """\
RESTOS A PAGAR
213110101020802 RP Processados - FMC_Fonte 1500 173.584,72 0,00 173.584,72
Total 35.936.198,97 4.782.988,29 40.719.187,26
TRANSFERÊNCIA FINANCEIRA
351120200000001 Repasse Concedido ao FMS 18.585.649,70 10.536.855,72 29.122.505,42
"""

        summary = parse_restos_a_pagar_summary(
            text,
            fiscal_year=2026,
            reference_month=3,
        )

        self.assertEqual(summary.payments_prior_amount, Decimal("35936198.97"))
        self.assertEqual(summary.payments_period_amount, Decimal("4782988.29"))
        self.assertEqual(summary.payments_to_date_amount, Decimal("40719187.26"))

    def test_reconstructs_interleaved_total_from_may_balancete(self):
        text = """\
RESTOS A PAGAR
213110101020802
Total
TRANSFERÊNCIA FINANCEIRA
RP Processados - FMC_Fonte 1500 173.584,72
44.697.475,81
0,00
667.168,25
173.584,72
45.364.644,06
351120200000001 Repasse Concedido ao FMS 38.980.428,98 8.324.365,84 47.304.794,82
"""

        summary = parse_restos_a_pagar_summary(
            text,
            fiscal_year=2026,
            reference_month=5,
        )

        self.assertEqual(summary.payments_prior_amount, Decimal("44697475.81"))
        self.assertEqual(summary.payments_period_amount, Decimal("667168.25"))
        self.assertEqual(summary.payments_to_date_amount, Decimal("45364644.06"))

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
