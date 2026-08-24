from __future__ import annotations

import logging
import unittest
from datetime import date

from barreiras_collectors.collection_control import CollectionOutcome
from barreiras_collectors.commands.collect_tcm_ba_monthly_catalog import (
    TcmBaMonthlyCollectionSummary,
    execute_controlled_tcm_month,
    execute_tcm_monthly_backfill,
    month_range,
)


class FakeControl:
    def __init__(self) -> None:
        self.completions = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        del exc_type, exc_value, traceback
        return False

    def complete(self, **values):
        self.completions.append(values)


def summary(*, year: int, month: int, documents: int = 1824):
    return TcmBaMonthlyCollectionSummary(
        year=year,
        month=month,
        documents=documents,
        artifacts=193,
        inserted_records=documents + 1,
        existing_records=0,
        artifact_hashes=("a" * 64,),
    )


class TcmBaMonthlyCatalogCommandTests(unittest.TestCase):
    def test_builds_inclusive_month_range(self) -> None:
        self.assertEqual(
            month_range("2023-11", "2024-02", collected_on=date(2026, 8, 24)),
            ((2023, 11), (2023, 12), (2024, 1), (2024, 2)),
        )
        with self.assertRaises(ValueError):
            month_range("2021-01", "2027-01", collected_on=date(2026, 8, 24))

    def test_closes_month_only_after_exact_catalog_is_persisted(self) -> None:
        control = FakeControl()
        result = execute_controlled_tcm_month(
            control=control,
            operation=lambda: summary(year=2023, month=4),
        )

        self.assertEqual(result.documents, 1824)
        completion = control.completions[0]
        self.assertEqual(completion["outcome"], CollectionOutcome.COMPLETE)
        self.assertEqual(completion["observed_records"], 1824)
        self.assertEqual(completion["checkpoint"]["competence"], "04/2023")
        self.assertEqual(completion["metrics"]["artifacts_preserved"], 193)

    def test_attempts_later_months_before_reporting_failures(self) -> None:
        attempted = []

        def operation_factory(year: int, month: int):
            def operation():
                attempted.append((year, month))
                if month == 4:
                    raise RuntimeError("fonte indisponível")
                return summary(year=year, month=month)

            return operation

        with self.assertRaisesRegex(RuntimeError, "2023-04"):
            execute_tcm_monthly_backfill(
                months=((2023, 4), (2023, 5)),
                control_factory=lambda _year, _month: FakeControl(),
                operation_factory=operation_factory,
                logger=logging.getLogger(__name__),
            )
        self.assertEqual(attempted, [(2023, 4), (2023, 5)])


if __name__ == "__main__":
    unittest.main()
