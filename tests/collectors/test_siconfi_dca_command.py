from __future__ import annotations

import logging
import unittest
from datetime import date

from barreiras_collectors.collection_control import CollectionOutcome
from barreiras_collectors.commands.collect_siconfi_dca import (
    SiconfiDcaCollectionSummary,
    execute_controlled_siconfi_collection,
    execute_yearly_siconfi_backfill,
    resolve_year_range,
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


def summary(*, year: int = 2021, rows: int = 1109) -> SiconfiDcaCollectionSummary:
    return SiconfiDcaCollectionSummary(
        years=1,
        pages=1,
        rows=rows,
        inserted_records=rows,
        existing_records=0,
        artifact_hashes=("a" * 64,),
        year_from=year,
        year_to=year,
    )


class SiconfiDcaCommandTests(unittest.TestCase):
    def test_resolves_historical_range_without_accepting_future_year(self) -> None:
        self.assertEqual(
            resolve_year_range(2021, 2026, collected_on=date(2026, 8, 24)),
            (date(2021, 1, 1), date(2026, 8, 24)),
        )
        with self.assertRaises(ValueError):
            resolve_year_range(2021, 2027, collected_on=date(2026, 8, 24))

    def test_closes_coverage_only_after_all_requested_years_complete(self) -> None:
        control = FakeControl()

        result = execute_controlled_siconfi_collection(
            control=control,
            operation=lambda: summary(),
        )

        self.assertEqual(result.rows, 1109)
        self.assertEqual(control.completions[0]["outcome"], CollectionOutcome.COMPLETE)
        self.assertEqual(control.completions[0]["observed_records"], 1109)
        self.assertEqual(control.completions[0]["checkpoint"]["year_to"], 2021)

    def test_classifies_each_exercise_as_complete_or_confirmed_empty(self) -> None:
        controls = {2025: FakeControl(), 2026: FakeControl()}

        results = execute_yearly_siconfi_backfill(
            fiscal_years=(2025, 2026),
            control_factory=lambda year: controls[year],  # type: ignore[arg-type]
            operation_factory=lambda year: (
                lambda: summary(year=year, rows=1089 if year == 2025 else 0)
            ),
            logger=logging.getLogger(__name__),
        )

        self.assertEqual(tuple(year for year, _summary in results), (2025, 2026))
        self.assertEqual(
            controls[2025].completions[0]["outcome"], CollectionOutcome.COMPLETE
        )
        self.assertEqual(
            controls[2026].completions[0]["outcome"], CollectionOutcome.EMPTY
        )
        self.assertEqual(controls[2026].completions[0]["observed_records"], 0)

    def test_attempts_later_exercises_before_reporting_annual_failures(self) -> None:
        attempted: list[int] = []

        def operation_factory(year: int):
            def operation() -> SiconfiDcaCollectionSummary:
                attempted.append(year)
                if year == 2022:
                    raise RuntimeError("fonte indisponível")
                return summary(year=year)

            return operation

        with self.assertRaisesRegex(RuntimeError, "2022"):
            execute_yearly_siconfi_backfill(
                fiscal_years=(2022, 2023),
                control_factory=lambda _year: FakeControl(),  # type: ignore[arg-type]
                operation_factory=operation_factory,
                logger=logging.getLogger(__name__),
            )

        self.assertEqual(attempted, [2022, 2023])


if __name__ == "__main__":
    unittest.main()
