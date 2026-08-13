from __future__ import annotations

import unittest

from barreiras_collectors.collection_control import CollectionOutcome
from barreiras_collectors.commands.collect_transferegov_download_catalog import (
    TransferegovDownloadCatalogSummary,
    execute_controlled_catalog,
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


class TransferegovDownloadCatalogCommandTests(unittest.TestCase):
    def test_control_starts_before_operation_and_closes_complete_coverage(self) -> None:
        control = FakeControl()

        def operation():
            self.assertTrue(control.entered)
            return TransferegovDownloadCatalogSummary(
                selected_files=8,
                selected_bytes=900_000_000,
                inserted_records=8,
                existing_records=0,
                artifact_sha256="a" * 64,
            )

        summary = execute_controlled_catalog(
            control=control,  # type: ignore[arg-type]
            operation=operation,
        )

        self.assertEqual(summary.selected_files, 8)
        self.assertEqual(control.completed["outcome"], CollectionOutcome.COMPLETE)
        self.assertEqual(control.completed["observed_records"], 8)
        self.assertEqual(control.completed["checkpoint"], {"selected_files": 8})
        self.assertEqual(
            control.completed["metrics"]["selected_bytes"],
            900_000_000,
        )


if __name__ == "__main__":
    unittest.main()
