from __future__ import annotations

import unittest
from decimal import Decimal
from pathlib import Path

from barreiras_normalization.payroll_report_pdf import (
    PayrollReportContractError,
    parse_payroll_report_aggregate,
)

FIXTURE = (
    Path(__file__).parents[2]
    / "fixtures"
    / "documents"
    / "payroll-report-aggregate-sample.txt"
)


class PayrollReportPdfTests(unittest.TestCase):
    def test_parses_only_reconciled_aggregate_totals(self) -> None:
        report = parse_payroll_report_aggregate(
            FIXTURE.read_text(encoding="utf-8")
        )

        self.assertEqual(report.employee_count, 5)
        self.assertEqual(report.gross_amount, Decimal("17500.50"))
        self.assertEqual(report.deduction_amount, Decimal("3000.25"))
        self.assertEqual(report.net_amount, Decimal("14500.25"))
        self.assertEqual(report.subtotal_count, 2)
        self.assertEqual(report.payroll_cycle, "regular")
        self.assertEqual(
            set(vars(report)),
            {
                "employee_count",
                "gross_amount",
                "deduction_amount",
                "net_amount",
                "subtotal_count",
                "payroll_cycle",
                "parser_version",
            },
        )

    def test_classifies_thirteenth_salary_components_from_official_header(
        self,
    ) -> None:
        regular = FIXTURE.read_text(encoding="utf-8")
        advance = regular.replace(
            "1-Normal, 3-Complementar, 9-Rescisão",
            "4-Adiant. 13º",
        )
        final = regular.replace(
            "1-Normal, 3-Complementar, 9-Rescisão",
            "6-13º Final",
        )

        self.assertEqual(
            parse_payroll_report_aggregate(advance).payroll_cycle,
            "thirteenth_advance",
        )
        self.assertEqual(
            parse_payroll_report_aggregate(final).payroll_cycle,
            "thirteenth_final",
        )

    def test_rejects_unknown_or_mixed_payroll_cycles(self) -> None:
        regular = FIXTURE.read_text(encoding="utf-8")
        unknown = regular.replace(
            "1-Normal, 3-Complementar, 9-Rescisão",
            "8-Folha desconhecida",
        )
        mixed = (
            f"{regular}\nListagem Sintética E-TCM\n"
            "6-13º FinalFOLHA.........:"
        )

        with self.assertRaisesRegex(PayrollReportContractError, "processamento"):
            parse_payroll_report_aggregate(unknown)
        with self.assertRaisesRegex(PayrollReportContractError, "processamento"):
            parse_payroll_report_aggregate(mixed)

    def test_rejects_mixed_cycles_listed_in_the_same_official_field(
        self,
    ) -> None:
        regular = FIXTURE.read_text(encoding="utf-8")
        mixed = regular.replace(
            "1-Normal, 3-Complementar, 9-Rescisão",
            "1-Normal, 4-Adiant. 13º",
        )

        with self.assertRaisesRegex(PayrollReportContractError, "misto"):
            parse_payroll_report_aggregate(mixed)

    def test_accepts_mojibake_observed_in_official_pdf_text(self) -> None:
        text = (
            "Listagem Sint�tica E-TCM\n"
            "<Todos>FOLHA.........:\n"
            "Mat. Nome Cargo Regime/V�nculo Local de Trabalho "
            "Admiss�o C. Hor�ria Provento Desconto L�quido\n"
            "Total de Funcion�rios: 2 5.000,00 1.000,00 4.000,00\n"
            "Total de Funcion�rios Geral: 2 5.000,00 1.000,00 4.000,00"
        )

        report = parse_payroll_report_aggregate(text)

        self.assertEqual(report.employee_count, 2)
        self.assertEqual(report.payroll_cycle, "regular")

    def test_rejects_grand_total_that_does_not_match_subtotals(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8").replace(
            "Total de Funcionários Geral: 5 17.500,50 3.000,25 14.500,25",
            "Total de Funcionários Geral: 6 17.500,50 3.000,25 14.500,25",
        )

        with self.assertRaisesRegex(PayrollReportContractError, "subtotais"):
            parse_payroll_report_aggregate(text)

    def test_rejects_amounts_that_do_not_close(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8").replace(
            "10.000,00 2.000,00 8.000,00",
            "10.000,00 2.000,00 8.100,00",
        )

        with self.assertRaisesRegex(PayrollReportContractError, "aritmética"):
            parse_payroll_report_aggregate(text)

    def test_rejects_duplicate_grand_total(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8")
        text = f"{text}\nTotal de Funcionários Geral: 5 17.500,50 3.000,25 14.500,25"

        with self.assertRaisesRegex(PayrollReportContractError, "total geral"):
            parse_payroll_report_aggregate(text)

    def test_rejects_unknown_layout_even_when_it_contains_amounts(self) -> None:
        text = (
            "Relatório sem cabeçalho validado\n"
            "Total de Funcionários: 2 5.000,00 1.000,00 4.000,00\n"
            "Total de Funcionários Geral: 2 5.000,00 1.000,00 4.000,00"
        )

        with self.assertRaisesRegex(PayrollReportContractError, "cabeçalho"):
            parse_payroll_report_aggregate(text)


if __name__ == "__main__":
    unittest.main()
