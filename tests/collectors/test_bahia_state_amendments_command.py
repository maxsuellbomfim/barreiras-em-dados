from __future__ import annotations

import unittest

from barreiras_collectors.collection_control import CollectionOutcome
from barreiras_collectors.commands.collect_bahia_state_amendments import (
    BahiaStateAmendmentCollectionSummary,
    execute_controlled_state_amendments,
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


class BahiaStateAmendmentCommandTests(unittest.TestCase):
    def test_control_starts_before_http_and_closes_after_both_artifacts(self) -> None:
        control = FakeControl()

        def operation():
            self.assertTrue(control.entered)
            return BahiaStateAmendmentCollectionSummary(
                archive_members=5,
                archive_rows=87_123,
                unparseable_members=(),
                archive_bytes=2_469_201,
                inserted_records=6,
                existing_records=0,
                catalog_sha256="a" * 64,
                archive_sha256="b" * 64,
                resource_last_modified="2026-08-12T09:34:57",
            )

        summary = execute_controlled_state_amendments(
            control=control,  # type: ignore[arg-type]
            operation=operation,
        )

        self.assertEqual(summary.archive_members, 5)
        self.assertEqual(control.completed["outcome"], CollectionOutcome.COMPLETE)
        self.assertEqual(control.completed["observed_records"], 5)
        self.assertEqual(control.completed["metrics"]["archive_rows"], 87_123)
        self.assertEqual(
            control.completed["checkpoint"]["territorial_scope"],
            "not_available_in_archive",
        )

    def test_malformed_source_view_is_preserved_as_partial_coverage(self) -> None:
        control = FakeControl()

        summary = BahiaStateAmendmentCollectionSummary(
            archive_members=5,
            archive_rows=60_000,
            unparseable_members=(
                "VW_PAINEL_EMENDAS_PARLAMENTARES_PAGAMENTOS.csv",
            ),
            archive_bytes=2_469_201,
            inserted_records=6,
            existing_records=0,
            catalog_sha256="a" * 64,
            archive_sha256="b" * 64,
            resource_last_modified="2026-08-12T09:34:57",
        )

        execute_controlled_state_amendments(
            control=control,  # type: ignore[arg-type]
            operation=lambda: summary,
        )

        self.assertEqual(control.completed["outcome"], CollectionOutcome.PARTIAL)
        self.assertEqual(
            control.completed["metrics"]["unparseable_members"],
            ["VW_PAINEL_EMENDAS_PARLAMENTARES_PAGAMENTOS.csv"],
        )


if __name__ == "__main__":
    unittest.main()
