from __future__ import annotations

import unittest

from barreiras_collectors.commands.plan_payroll_backfill import plan_months


class PayrollBackfillPlanTests(unittest.TestCase):
    def test_orders_bounded_window_from_newest_to_oldest(self) -> None:
        self.assertEqual(
            plan_months(
                start_month="2024-03",
                end_month="2024-08",
                max_months=6,
            ),
            (
                "2024-08",
                "2024-07",
                "2024-06",
                "2024-05",
                "2024-04",
                "2024-03",
            ),
        )

    def test_crosses_year_boundary_without_skipping_months(self) -> None:
        self.assertEqual(
            plan_months(
                start_month="2023-12",
                end_month="2024-02",
                max_months=3,
            ),
            ("2024-02", "2024-01", "2023-12"),
        )

    def test_rejects_invalid_or_excessive_windows(self) -> None:
        cases = (
            {"start_month": "2024-7", "end_month": "2024-08", "max_months": 3},
            {"start_month": "2024-09", "end_month": "2024-08", "max_months": 3},
            {"start_month": "2024-03", "end_month": "2024-08", "max_months": 3},
            {"start_month": "2024-08", "end_month": "2024-08", "max_months": 2},
        )
        for values in cases:
            with self.subTest(values=values), self.assertRaises(ValueError):
                plan_months(**values)


if __name__ == "__main__":
    unittest.main()
