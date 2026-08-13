from __future__ import annotations

import csv
import io
import unittest
import zipfile
from decimal import Decimal

from barreiras_collectors.connectors.bahia_state_amendments import (
    EXPECTED_MEMBER_COLUMNS,
)


def _archive_with_expense_rows(rows: list[tuple[str, ...]]) -> bytes:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for member_name, columns in EXPECTED_MEMBER_COLUMNS.items():
            output = io.StringIO(newline="")
            writer = csv.writer(output, delimiter=";", lineterminator="\n")
            writer.writerow(columns)
            if member_name == "VW_PAINEL_EMENDAS_PARLAMENTARES_DESPESAS.csv":
                writer.writerows(rows)
            package.writestr(member_name, output.getvalue().encode("utf-8-sig"))
    return archive.getvalue()


class BahiaStateExecutionParserTests(unittest.TestCase):
    def test_extracts_financial_stages_without_claiming_municipal_attribution(
        self,
    ) -> None:
        try:
            from barreiras_normalization.bahia_state_execution import (
                parse_state_execution_archive,
            )
        except ImportError:
            self.fail("o parser de execucao estadual ainda nao existe")

        archive = _archive_with_expense_rows(
            [
                (
                    "2026",
                    "Secretaria de Desenvolvimento Rural",
                    "SDR",
                    "Companhia de Desenvolvimento e Acao Regional",
                    "CAR",
                    "Implantacao de Projeto de Apoio",
                    "500069",
                    "Antonio Henrique Junior",
                    "Antonio Henrique Junior",
                    "2026.3.18.18401.417.1926.500069.5",
                    "1442532,00",
                    "1442532,00",
                    "31200,00",
                    "0,00",
                    "-1200,00",
                )
            ]
        )

        aggregates = parse_state_execution_archive(archive)

        self.assertEqual(len(aggregates), 1)
        aggregate = aggregates[0]
        self.assertEqual(aggregate.fiscal_year, 2026)
        self.assertEqual(aggregate.agency_code, "SDR")
        self.assertEqual(aggregate.budget_unit_code, "CAR")
        self.assertEqual(aggregate.action_code, "1926")
        self.assertEqual(aggregate.author_external_code, "500069")
        self.assertEqual(aggregate.current_budget_amount, Decimal("1442532.00"))
        self.assertEqual(aggregate.committed_amount, Decimal("31200.00"))
        self.assertEqual(aggregate.liquidated_amount, Decimal("0.00"))
        self.assertEqual(aggregate.paid_amount, Decimal("-1200.00"))
        self.assertEqual(
            aggregate.territorial_scope,
            "not_available_in_execution_archive",
        )
        self.assertEqual(len(aggregate.evidence_sha256), 64)


if __name__ == "__main__":
    unittest.main()
