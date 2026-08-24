from __future__ import annotations

import unittest
from datetime import date

from barreiras_collectors.collection_control import CollectionOutcome
from barreiras_collectors.commands.collect_siconfi_dca import (
    SiconfiDcaCollectionSummary,
    execute_controlled_siconfi_collection,
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


def summary(*, rows: int = 1109) -> SiconfiDcaCollectionSummary:
    return SiconfiDcaCollectionSummary(
        years=1,
        pages=1,
        rows=rows,
        inserted_records=rows,
        existing_records=0,
        artifact_hashes=("a" * 64,),
        year_from=2021,
        year_to=2021,
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


if __name__ == "__main__":
    unittest.main()
