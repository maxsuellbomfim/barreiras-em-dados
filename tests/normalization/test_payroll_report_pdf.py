from __future__ import annotations

import unittest
from decimal import Decimal
from pathlib import Path

from barreiras_normalization.payroll_report_pdf import (
    PayrollReportContractError,
    parse_payroll_report_aggregate,
    parse_payroll_report_compensation_distribution,
    parse_payroll_report_regime_breakdown,
)

FIXTURE = (
    Path(__file__).parents[2]
    / "fixtures"
    / "documents"
    / "payroll-report-aggregate-sample.txt"
)


def regime_report(*rows: str, total: str) -> str:
    return "\n".join(
        (
            "PREFEITURA MUNICIPAL DE BARREIRAS",
            "Listagem Sintética E-TCM",
            "FOLHA.........: 1-Normal, 3-Complementar, 9-Rescisão",
            (
                "Mat.   Nome                  Cargo                 "
                "Regime/Vínculo       Local de Trabalho       "
                "Provento Desconto Líquido"
            ),
            *rows,
            f"Total de Funcionários: {total}",
            f"Total de Funcionários Geral: {total}",
        )
    )


class PayrollReportPdfTests(unittest.TestCase):
    def test_groups_regular_payroll_into_reconciled_compensation_bands(
        self,
    ) -> None:
        report = regime_report(
            (
                "100    PESSOA UM             PROFESSOR             "
                "Estatutário          ESCOLA MUNICIPAL        "
                "1.500,00 100,00 1.400,00"
            ),
            (
                "101    PESSOA DOIS           ASSESSOR              "
                "Cargo em Comissão    GABINETE                "
                "3.000,01 250,00 2.750,01"
            ),
            (
                "102    PESSOA TRÊS            SECRETÁRIO            "
                "Agente Político      GABINETE                "
                "21.000,00 2.100,00 18.900,00"
            ),
            total="3 25.500,01 2.450,00 23.050,01",
        )

        distribution = parse_payroll_report_compensation_distribution(report)

        self.assertEqual(distribution.employee_count, 3)
        self.assertEqual(distribution.gross_amount, Decimal("25500.01"))
        self.assertEqual(distribution.maximum_gross_amount, Decimal("21000.00"))
        self.assertEqual(
            [(band.band_code, band.employee_count) for band in distribution.bands],
            [
                ("up_to_1500", 1),
                ("from_3000_01_to_5000", 1),
                ("above_20000", 1),
            ],
        )
        self.assertEqual(
            distribution.parser_version,
            "payroll-compensation-bands/1.0.0",
        )
        serialized = repr(distribution).casefold()
        for forbidden in ("pessoa um", "matrícula", "cpf", "cargo"):
            self.assertNotIn(forbidden, serialized)

    def test_rejects_compensation_bands_for_thirteenth_salary(self) -> None:
        report = regime_report(
            (
                "100    PESSOA UM             PROFESSOR             "
                "Estatutário          ESCOLA MUNICIPAL        "
                "1.500,00 100,00 1.400,00"
            ),
            total="1 1.500,00 100,00 1.400,00",
        ).replace(
            "1-Normal, 3-Complementar, 9-Rescisão",
            "6-13º Final",
        )

        with self.assertRaisesRegex(PayrollReportContractError, "folha regular"):
            parse_payroll_report_compensation_distribution(report)

    def test_groups_only_reconciled_rows_by_official_employment_regime(
        self,
    ) -> None:
        report = regime_report(
            (
                "100    PESSOA UM             PROFESSOR             "
                "Estatutário          ESCOLA MUNICIPAL        "
                "3.000,00 500,00 2.500,00"
            ),
            (
                "101    PESSOA DOIS           ASSESSOR              "
                "Cargo em Comissão    GABINETE                "
                "2.000,00 250,00 1.750,00"
            ),
            total="2 5.000,00 750,00 4.250,00",
        )

        breakdown = parse_payroll_report_regime_breakdown(report)

        by_code = {item.regime_code: item for item in breakdown.categories}
        self.assertEqual(breakdown.employee_count, 2)
        self.assertEqual(breakdown.gross_amount, Decimal("5000.00"))
        self.assertEqual(set(by_code), {"statutory", "commissioned"})
        self.assertEqual(by_code["statutory"].employee_count, 1)
        self.assertEqual(by_code["statutory"].gross_amount, Decimal("3000.00"))
        self.assertEqual(by_code["commissioned"].net_amount, Decimal("1750.00"))
        self.assertEqual(
            breakdown.parser_version,
            "payroll-regime-breakdown/1.0.0",
        )
        self.assertFalse(hasattr(breakdown, "people"))
        self.assertFalse(hasattr(breakdown, "names"))

    def test_accepts_transfer_marker_observed_in_official_employee_row(
        self,
    ) -> None:
        report = regime_report(
            (
                "(T)    PESSOA TRANSFERIDA    ANALISTA              "
                "Estatutário          SECRETARIA              "
                "28.140,83 9.279,01 18.861,82"
            ),
            total="1 28.140,83 9.279,01 18.861,82",
        )

        breakdown = parse_payroll_report_regime_breakdown(report)

        self.assertEqual(breakdown.employee_count, 1)
        self.assertEqual(breakdown.categories[0].regime_code, "statutory")

    def test_rejects_regime_breakdown_when_employee_rows_do_not_reconcile(
        self,
    ) -> None:
        report = regime_report(
            (
                "100    PESSOA UM             PROFESSOR             "
                "Estatutário          ESCOLA MUNICIPAL        "
                "3.000,00 500,00 2.500,00"
            ),
            total="2 5.000,00 750,00 4.250,00",
        )

        with self.assertRaisesRegex(PayrollReportContractError, "regimes"):
            parse_payroll_report_regime_breakdown(report)

    def test_rejects_unknown_regime_instead_of_guessing_category(self) -> None:
        report = regime_report(
            (
                "100    PESSOA UM             PROFESSOR             "
                "Vínculo desconhecido SECRETARIA              "
                "3.000,00 500,00 2.500,00"
            ),
            total="1 3.000,00 500,00 2.500,00",
        )

        with self.assertRaisesRegex(PayrollReportContractError, "vínculo"):
            parse_payroll_report_regime_breakdown(report)

    def test_parses_only_reconciled_aggregate_totals(self) -> None:
        report = parse_payroll_report_aggregate(FIXTURE.read_text(encoding="utf-8"))

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
        mixed = f"{regular}\nListagem Sintética E-TCM\n6-13º FinalFOLHA.........:"

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

    def test_accepts_compact_header_observed_in_february_2024(self) -> None:
        text = (
            "Listagem Sint�tica E-TCM\n"
            "FOLHA.........: 1 - Normal\n"
            "Mat. Nome Cargo Provento Desconto L�quido\n"
            "Total de Funcion�rios: 2 5.000,00 1.000,00 4.000,00\n"
            "Total de Funcion�rios Geral: 2 5.000,00 1.000,00 4.000,00"
        )

        report = parse_payroll_report_aggregate(text)

        self.assertEqual(report.employee_count, 2)
        self.assertEqual(report.gross_amount, Decimal("5000.00"))
        self.assertEqual(report.deduction_amount, Decimal("1000.00"))
        self.assertEqual(report.net_amount, Decimal("4000.00"))
        self.assertEqual(report.payroll_cycle, "regular")
        self.assertEqual(report.parser_version, "payroll-report-aggregate/1.4.0")

    def test_rejects_compact_header_without_required_monetary_column(
        self,
    ) -> None:
        text = (
            "Listagem Sint�tica E-TCM\n"
            "FOLHA.........: 1 - Normal\n"
            "Mat. Nome Cargo Provento L�quido\n"
            "Total de Funcion�rios: 2 5.000,00 1.000,00 4.000,00\n"
            "Total de Funcion�rios Geral: 2 5.000,00 1.000,00 4.000,00"
        )

        with self.assertRaisesRegex(PayrollReportContractError, "cabeçalho"):
            parse_payroll_report_aggregate(text)

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
