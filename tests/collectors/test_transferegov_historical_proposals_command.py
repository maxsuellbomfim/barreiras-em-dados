from __future__ import annotations

import unittest
from datetime import date

from barreiras_collectors.collection_control import CollectionOutcome
from barreiras_collectors.commands.collect_transferegov_historical_proposals import (
    HistoricalProposalCollectionSummary,
    execute_controlled_historical_proposals,
    resolve_coverage_period,
)


class FakeControl:
    def __init__(self) -> None:
        self.entered = False
        self.completed = None

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        del exc_type, exc_value, traceback
        return False

    def complete(self, **values):
        self.completed = values


class HistoricalProposalCommandTests(unittest.TestCase):
    def test_current_year_coverage_ends_on_collection_date(self) -> None:
        self.assertEqual(
            resolve_coverage_period(
                year_from=2021,
                year_to=2026,
                collected_on=date(2026, 8, 13),
            ),
            (date(2021, 1, 1), date(2026, 8, 13)),
        )

    def test_future_year_cannot_be_classified(self) -> None:
        with self.assertRaisesRegex(ValueError, "ano futuro"):
            resolve_coverage_period(
                year_from=2021,
                year_to=2027,
                collected_on=date(2026, 8, 13),
            )

    def test_control_opens_before_download_and_closes_only_after_persistence(
        self,
    ) -> None:
        control = FakeControl()

        def operation():
            self.assertTrue(control.entered)
            return HistoricalProposalCollectionSummary(
                proposals=69,
                archive_bytes=205_017_763,
                inserted_records=69,
                existing_records=0,
                archive_sha256="a" * 64,
                catalog_etag="0xETAG",
                year_from=2021,
                year_to=2026,
            )

        summary = execute_controlled_historical_proposals(
            control=control,  # type: ignore[arg-type]
            operation=operation,
        )

        self.assertEqual(summary.proposals, 69)
        self.assertEqual(control.completed["outcome"], CollectionOutcome.COMPLETE)
        self.assertEqual(control.completed["observed_records"], 69)
        self.assertEqual(
            control.completed["checkpoint"],
            {
                "catalog_etag": "0xETAG",
                "archive_sha256": "a" * 64,
                "year_from": 2021,
                "year_to": 2026,
            },
        )
        self.assertEqual(
            control.completed["metrics"]["archive_bytes"],
            205_017_763,
        )

    def test_confirmed_period_without_municipal_rows_is_empty(self) -> None:
        control = FakeControl()

        summary = HistoricalProposalCollectionSummary(
            proposals=0,
            archive_bytes=205_017_763,
            inserted_records=0,
            existing_records=0,
            archive_sha256="b" * 64,
            catalog_etag="0xETAG",
            year_from=2021,
            year_to=2026,
        )

        execute_controlled_historical_proposals(
            control=control,  # type: ignore[arg-type]
            operation=lambda: summary,
        )

        self.assertEqual(control.completed["outcome"], CollectionOutcome.EMPTY)
        self.assertEqual(control.completed["observed_records"], 0)


if __name__ == "__main__":
    unittest.main()
