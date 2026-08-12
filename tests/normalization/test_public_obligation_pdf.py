from __future__ import annotations

import unittest
from decimal import Decimal
from pathlib import Path

from barreiras_normalization.public_obligation_pdf import (
    PublicObligationPdfContractError,
    parse_restos_a_pagar_summary,
    validate_restos_a_pagar_progression,
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

    def test_reconstructs_total_exported_as_three_column_blocks(self):
        text = """\
RESTOS A PAGAR
213110101020214
213110101020215
6.501,25 0,00 6.501,25
Total
2020 - Fonte 6102 RP Nao Processados - FMS
2020 - Fonte 0214 RP Nao Processados - FMS
422.276,40
1.311.396,80
22.354.323,42
0,00
705.359,18
1.445.172,84
422.276,40
2.016.755,98
23.799.496,26
TRANSFERENCIA FINANCEIRA
18.779.474,03 4.578.939,29 23.358.413,32
"""

        summary = parse_restos_a_pagar_summary(
            text,
            fiscal_year=2021,
            reference_month=5,
        )

        self.assertEqual(summary.payments_prior_amount, Decimal("22354323.42"))
        self.assertEqual(summary.payments_period_amount, Decimal("1445172.84"))
        self.assertEqual(summary.payments_to_date_amount, Decimal("23799496.26"))

    def test_accepts_total_label_split_by_embedded_pdf_spacing(self):
        text = """\
RESTOS A PAGAR
213110101020128 2021 - Fonte 0100 RP Nao Processados
Tot a 19.895.890,06 588.494,89 20.484.384,95
TRANSFERENCIA FINANCEIRA
"""

        summary = parse_restos_a_pagar_summary(
            text,
            fiscal_year=2022,
            reference_month=6,
        )

        self.assertEqual(summary.payments_prior_amount, Decimal("19895890.06"))
        self.assertEqual(summary.payments_period_amount, Decimal("588494.89"))
        self.assertEqual(summary.payments_to_date_amount, Decimal("20484384.95"))

    def test_accepts_punctuation_between_total_label_and_declared_values(self):
        text = """\
RESTOS A PAGAR
213110101020128 2021 - Fonte 0100 RP Nao Processados
Total . . 20.484.384,95 303.721,65 20.788.106,60
TRANSFERENCIA FINANCEIRA
"""

        summary = parse_restos_a_pagar_summary(
            text,
            fiscal_year=2022,
            reference_month=7,
        )

        self.assertEqual(summary.payments_prior_amount, Decimal("20484384.95"))
        self.assertEqual(summary.payments_period_amount, Decimal("303721.65"))
        self.assertEqual(summary.payments_to_date_amount, Decimal("20788106.60"))

    def test_accepts_brl_amounts_with_spaces_inserted_by_embedded_pdf(self):
        text = """\
RESTOS A PAGAR
213110101020128 2021 - Fonte 0100 RP Nao Processados
Total 21. 214.414, 18 51. 117,60 21.265.531,78
TRANSFERENCIA FINANCEIRA
"""

        summary = parse_restos_a_pagar_summary(
            text,
            fiscal_year=2022,
            reference_month=11,
        )

        self.assertEqual(summary.payments_prior_amount, Decimal("21214414.18"))
        self.assertEqual(summary.payments_period_amount, Decimal("51117.60"))
        self.assertEqual(summary.payments_to_date_amount, Decimal("21265531.78"))

    def test_rejects_ambiguous_column_block_totals(self):
        text = """\
RESTOS A PAGAR
Total
5,00
7,00
12,00
5,00
7,00
12,00
TRANSFERENCIA FINANCEIRA
"""

        with self.assertRaisesRegex(
            PublicObligationPdfContractError,
            "total de restos a pagar",
        ):
            parse_restos_a_pagar_summary(
                text,
                fiscal_year=2021,
                reference_month=5,
            )

    def test_does_not_fall_back_to_row_when_total_line_is_malformed(self):
        text = """\
RESTOS A PAGAR
6.501,25 0,00 6.501,25
Total 24.003.976,26 0.00 24M03-976,26
TRANSFERENCIA FINANCEIRA
"""

        with self.assertRaisesRegex(
            PublicObligationPdfContractError,
            "total de restos a pagar",
        ):
            parse_restos_a_pagar_summary(
                text,
                fiscal_year=2021,
                reference_month=7,
            )

    def test_does_not_publish_account_row_when_total_marker_is_split(self):
        text = """\
RESTOS A PAGAR
213110101020225 1.945.534,03 0,00 1.945.534,03
Tot a
TRANSFERENCIA FINANCEIRA
19.895.890,06 588.494,89 20.484.384,95
"""

        with self.assertRaisesRegex(
            PublicObligationPdfContractError,
            "total de restos a pagar",
        ):
            parse_restos_a_pagar_summary(
                text,
                fiscal_year=2022,
                reference_month=6,
            )

    def test_rejects_progression_that_diverges_from_previous_month(self):
        current = parse_restos_a_pagar_summary(
            """RESTOS A PAGAR
24.003.976,26 0,00 24.003.976,26
TRANSFERENCIA FINANCEIRA
""",
            fiscal_year=2021,
            reference_month=7,
        )

        with self.assertRaisesRegex(
            PublicObligationPdfContractError,
            "mes anterior",
        ):
            validate_restos_a_pagar_progression(
                current,
                previous_month_to_date=Decimal("23799496.26"),
            )

    def test_accepts_progression_equal_to_previous_month(self):
        current = parse_restos_a_pagar_summary(
            """RESTOS A PAGAR
24.003.976,26 0,00 24.003.976,26
TRANSFERENCIA FINANCEIRA
""",
            fiscal_year=2021,
            reference_month=7,
        )

        validate_restos_a_pagar_progression(
            current,
            previous_month_to_date=Decimal("24003976.26"),
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
