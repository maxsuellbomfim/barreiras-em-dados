from __future__ import annotations

import unittest

from barreiras_collectors.collection_control import CollectionOutcome
from barreiras_collectors.commands.collect_bahia_state_loa_amendments import (
    StateLoaAnnexCollectionSummary,
    execute_controlled_state_loa_year,
)


class FakeControl:
    def __init__(self) -> None:
        self.entered = False
        self.completed: dict[str, object] = {}

    def __enter__(self):
        self.entered = True
        return self

    def complete(self, **values):
        self.completed = values

    def __exit__(self, exc_type, exc_value, traceback):
        del exc_type, exc_value, traceback
        return False


class BahiaStateLoaAmendmentCommandTests(unittest.TestCase):
    def test_blocked_2021_is_recorded_without_requesting_a_document(self) -> None:
        control = FakeControl()
        called = False

        def operation():
            nonlocal called
            called = True
            raise AssertionError("a URL incorreta de 2021 nao deve ser baixada")

        summary = execute_controlled_state_loa_year(
            year=2021,
            control=control,  # type: ignore[arg-type]
            operation=operation,
        )

        self.assertTrue(control.entered)
        self.assertFalse(called)
        self.assertEqual(summary.status, "blocked")
        self.assertEqual(control.completed["outcome"], CollectionOutcome.BLOCKED)
        self.assertIn("2020", str(control.completed["block_reason"]))

    def test_supported_year_completes_with_hash_and_budget_stage(self) -> None:
        control = FakeControl()
        summary = StateLoaAnnexCollectionSummary(
            fiscal_year=2025,
            annex_code="III",
            status="complete",
            document_bytes=2048,
            inserted_records=1,
            existing_records=0,
            body_sha256="a" * 64,
        )

        result = execute_controlled_state_loa_year(
            year=2025,
            control=control,  # type: ignore[arg-type]
            operation=lambda: summary,
        )

        self.assertEqual(result, summary)
        self.assertEqual(control.completed["outcome"], CollectionOutcome.COMPLETE)
        self.assertEqual(control.completed["observed_records"], 1)
        self.assertEqual(control.completed["checkpoint"]["budget_stage"], "authorized")
        self.assertEqual(
            control.completed["checkpoint"]["territorial_scope"],
            "municipality_explicit",
        )


if __name__ == "__main__":
    unittest.main()
