from __future__ import annotations

import hashlib
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from barreiras_collectors.connectors import municipal_expenses as expenses
from barreiras_collectors.http import HttpResponse

FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "sources"
    / "prefeitura-despesas-webrun"
)
GRID = (FIXTURES / "empenhos-grid-2026-08-sample.txt").read_bytes()
RULE = (FIXTURES / "period-rule-2026-08.txt").read_bytes()
TODAY = date(2026, 9, 23)


class SessionTransport:
    def __init__(self, *, rule: bytes = RULE, grid: bytes = GRID) -> None:
        self.rule = rule
        self.grid = grid
        self.calls: list[tuple[str, str]] = []
        self.forms: list[dict[str, str]] = []

    def reset_session(self) -> None:
        self.calls.append(("reset", ""))

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds, max_body_bytes
        self.calls.append(("get", url))
        body = self.grid if "/navigate.do?" in url else b"<html></html>"
        return HttpResponse(status=200, headers={}, body=body, final_url=url)

    def post(self, url, *, form, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds, max_body_bytes
        self.calls.append(("post", url))
        self.forms.append(dict(form))
        return HttpResponse(status=200, headers={}, body=self.rule, final_url=url)


class MonthlyCommitmentsTests(unittest.TestCase):
    def test_reads_closed_month_in_one_session(self) -> None:
        transport = SessionTransport()

        result = expenses.fetch_monthly_commitments(
            2026, 8, today=TODAY, transport=transport
        )

        self.assertEqual(
            [kind for kind, _ in transport.calls], ["reset", "get", "post", "get"]
        )
        self.assertIn("/openform.do?", transport.calls[1][1])
        form = transport.forms[0]
        self.assertEqual(form["ruleName"], expenses.PERIOD_RULE)
        self.assertEqual(
            (form["P_0"], form["P_1"], form["P_6"]), ("01/08/2026", "31/08/2026", "P")
        )
        self.assertEqual(result.declared_total, 3)
        self.assertEqual(result.repeated_rows, 1)
        self.assertEqual(result.coverage, "complete")
        self.assertEqual(result.grid_body, GRID)
        self.assertEqual(result.grid_sha256, hashlib.sha256(GRID).hexdigest())
        self.assertEqual(
            [row[expenses.FIELD_KEY] for row in result.rows],
            ["O-250760", "O-250760", "E-57409"],
        )
        first = result.rows[0]
        self.assertIn("Contrato nº 133/2026", first[expenses.FIELD_HISTORY])
        self.assertEqual(
            first[expenses.FIELD_CREDITOR], "SMART CARTUCHOS E LOCAÇÕES  LTDA"
        )
        self.assertEqual(
            result.source_field_names[expenses.FIELD_HISTORY], "EMP_HISTORICO"
        )
        self.assertEqual(result.column_titles[expenses.FIELD_NUMBER], "Nº Empenho")

    def test_rejects_open_month_before_any_request(self) -> None:
        transport = SessionTransport()

        with self.assertRaises(ValueError):
            expenses.fetch_monthly_commitments(
                2026, 9, today=TODAY, transport=transport
            )

        self.assertEqual(transport.calls, [])

    def test_grid_shorter_than_declared_total_is_failure(self) -> None:
        transport = SessionTransport(
            rule=RULE.replace(b"setTotalRows(3)", b"setTotalRows(5)")
        )

        with self.assertRaises(expenses.MunicipalExpensesContractError):
            expenses.fetch_monthly_commitments(
                2026, 8, today=TODAY, transport=transport
            )

    def test_zero_declared_commitments_is_failure_not_empty(self) -> None:
        transport = SessionTransport(
            rule=RULE.replace(b"setTotalRows(3)", b"setTotalRows(0)")
        )

        with self.assertRaises(expenses.MunicipalExpensesContractError):
            expenses.fetch_monthly_commitments(
                2026, 8, today=TODAY, transport=transport
            )

        self.assertEqual(
            [kind for kind, _ in transport.calls], ["reset", "get", "post"]
        )

    def test_source_error_is_not_zero_commitments(self) -> None:
        refused = b"parent.interactionError('Invalid column name \\'X\\'.', null);"
        transport = SessionTransport(rule=refused)

        with self.assertRaises(expenses.MunicipalExpensesError) as raised:
            expenses.fetch_monthly_commitments(
                2026, 8, today=TODAY, transport=transport
            )

        self.assertNotIsInstance(
            raised.exception, expenses.MunicipalExpensesContractError
        )
        self.assertEqual(
            [kind for kind, _ in transport.calls], ["reset", "get", "post"]
        )

    def test_paginated_grid_is_failure(self) -> None:
        grid = GRID.replace(b"isLastPage = true;", b"isLastPage = false;")

        with self.assertRaises(expenses.MunicipalExpensesContractError):
            expenses.fetch_monthly_commitments(
                2026, 8, today=TODAY, transport=SessionTransport(grid=grid)
            )


class RowContractTests(unittest.TestCase):
    def rows(self):
        return expenses.parse_commitment_grid(GRID.decode("iso-8859-1")).rows

    def test_repeated_key_with_different_content_is_failure(self) -> None:
        first, second, third = self.rows()
        changed = {**second, expenses.FIELD_AMOUNT: "1,00"}

        with self.assertRaises(expenses.MunicipalExpensesContractError):
            expenses.validate_rows(
                (first, changed, third),
                first=date(2026, 8, 1),
                last=date(2026, 8, 31),
            )

    def test_row_outside_requested_month_is_failure(self) -> None:
        with self.assertRaises(expenses.MunicipalExpensesContractError):
            expenses.validate_rows(
                self.rows(), first=date(2026, 7, 1), last=date(2026, 7, 31)
            )

    def test_amounts_use_exact_decimal(self) -> None:
        self.assertEqual(expenses.parse_amount("1.234,56"), Decimal("1234.56"))
        self.assertEqual(expenses.parse_amount("-67,54"), Decimal("-67.54"))
        self.assertEqual(expenses.parse_amount("41200"), Decimal("41200"))
        with self.assertRaises(expenses.MunicipalExpensesContractError):
            expenses.parse_amount("1,234.56")

    def test_months_before_2024_are_partial_at_source(self) -> None:
        self.assertEqual(
            expenses.coverage_for(2023, 12), "partial_source_history_unavailable"
        )
        self.assertEqual(expenses.coverage_for(2024, 1), "complete")


if __name__ == "__main__":
    unittest.main()
