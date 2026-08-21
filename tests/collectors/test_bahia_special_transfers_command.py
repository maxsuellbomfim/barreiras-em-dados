from __future__ import annotations

import unittest

from barreiras_collectors.collection_control import CollectionOutcome
from barreiras_collectors.commands.collect_bahia_special_transfers import (
    BahiaSpecialTransferCollectionSummary,
    execute_controlled_special_transfers,
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


class BahiaSpecialTransferCommandTests(unittest.TestCase):
    def test_registers_control_before_operation_and_keeps_publication_blocked(
        self,
    ) -> None:
        control = FakeControl()

        def operation():
            self.assertTrue(control.entered)
            return BahiaSpecialTransferCollectionSummary(
                archive_members=5,
                archive_rows=12_169,
                source_warning_rows=15,
                archive_bytes=554_925,
                inserted_records=6,
                existing_records=0,
                catalog_sha256="a" * 64,
                archive_sha256="b" * 64,
                resource_last_modified="2026-08-20T11:14:09",
            )

        summary = execute_controlled_special_transfers(
            control=control,  # type: ignore[arg-type]
            operation=operation,
        )

        self.assertEqual(summary.archive_members, 5)
        self.assertEqual(control.completed["outcome"], CollectionOutcome.COMPLETE)
        self.assertEqual(control.completed["observed_records"], 5)
        self.assertEqual(control.completed["metrics"]["archive_rows"], 12_169)
        self.assertEqual(control.completed["metrics"]["source_warning_rows"], 15)
        self.assertEqual(
            control.completed["checkpoint"]["public_projection"],
            "blocked_pending_deterministic_reconciliation",
        )
        self.assertTrue(
            control.completed["metrics"]["restricted_identifier_column"]
        )

    def test_refuses_incomplete_archive(self) -> None:
        control = FakeControl()
        summary = BahiaSpecialTransferCollectionSummary(
            archive_members=4,
            archive_rows=10,
            source_warning_rows=0,
            archive_bytes=100,
            inserted_records=0,
            existing_records=0,
            catalog_sha256="a" * 64,
            archive_sha256="b" * 64,
            resource_last_modified="2026-08-20T11:14:09",
        )

        with self.assertRaisesRegex(RuntimeError, "cinco views"):
            execute_controlled_special_transfers(
                control=control,  # type: ignore[arg-type]
                operation=lambda: summary,
            )


if __name__ == "__main__":
    unittest.main()
