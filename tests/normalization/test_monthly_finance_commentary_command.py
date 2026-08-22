from __future__ import annotations

import unittest

from barreiras_normalization.commands.publish_monthly_finance_commentary import (
    MonthlyFinanceCommentaryRepository,
)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Connection:
    def __init__(self, rows_by_year):
        self.rows_by_year = rows_by_year
        self.calls = []
        self.closed = False

    def execute(self, query, parameters):
        self.calls.append((query, parameters))
        fiscal_year = parameters[0]
        return _Result(self.rows_by_year.get(fiscal_year, []))

    def close(self):
        self.closed = True


def _closure(*, closure_id: str, year: int, month: int):
    return {
        "closure_id": closure_id,
        "period_start": f"{year:04d}-{month:02d}-01",
        "period_end": f"{year:04d}-{month:02d}-28",
        "public_body_name": "Município de Barreiras",
        "closure_status": "operational",
        "coverage_note": "Cobertura validada.",
        "revenue_report_amount": "100.00",
        "expense_paid_amount": "80.00",
        "operational_difference_amount": "20.00",
    }


class MonthlyFinanceCommentaryRepositoryTests(unittest.TestCase):
    def test_pending_closures_filters_inside_rpc_one_year_at_a_time(self):
        connection = _Connection(
            {
                2026: [_closure(closure_id="2026-02", year=2026, month=2)],
                2025: [_closure(closure_id="2025-12", year=2025, month=12)],
            }
        )
        repository = MonthlyFinanceCommentaryRepository(lambda: connection)

        closures = repository.pending_closures(
            limit=2,
            fiscal_year_from=2021,
            fiscal_year_to=2026,
        )

        self.assertEqual(
            [closure.closure_id for closure in closures],
            ["2026-02", "2025-12"],
        )
        self.assertEqual(
            [parameters[0] for _, parameters in connection.calls],
            [2026, 2025],
        )
        self.assertEqual(
            [parameters for _, parameters in connection.calls],
            [(2026, 2), (2025, 1)],
        )
        for query, _ in connection.calls:
            normalized_query = " ".join(query.lower().split())
            self.assertIn(
                "get_public_monthly_finance_closures( 120, %s::smallint )",
                normalized_query,
            )
            self.assertNotIn("(120, null)", normalized_query)
            self.assertIn("commentary.facts = jsonb_build_object", normalized_query)
            self.assertIn("'closure_status', closure.closure_status", normalized_query)
            self.assertIn(
                "'operational_difference_amount', "
                "closure.operational_difference_amount::text",
                normalized_query,
            )
        self.assertTrue(connection.closed)


if __name__ == "__main__":
    unittest.main()
