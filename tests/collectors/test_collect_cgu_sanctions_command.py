from __future__ import annotations

import unittest

from barreiras_collectors.collection_control import CollectionOutcome
from barreiras_collectors.commands.collect_cgu_sanctions import (
    CGUSanctionCollectionSummary,
    execute_controlled_sanction_collection,
    plan_supplier_batch,
)


class RecordingControl:
    def __init__(self) -> None:
        self.completed = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def complete(self, **values):
        self.completed = values


class CGUSanctionCommandTests(unittest.TestCase):
    def test_plans_stable_bounded_batches_by_cnpj_cursor(self) -> None:
        suppliers = [
            "44493204000187",
            "13654405000195",
            "11222333000181",
            "44493204000187",
        ]

        first = plan_supplier_batch(suppliers, after_cnpj=None, limit=2)
        second = plan_supplier_batch(
            suppliers,
            after_cnpj=first.next_after_cnpj,
            limit=2,
        )

        self.assertEqual(first.cnpjs, ("11222333000181", "13654405000195"))
        self.assertEqual(first.remaining_suppliers, 1)
        self.assertEqual(first.next_after_cnpj, "13654405000195")
        self.assertEqual(second.cnpjs, ("44493204000187",))
        self.assertEqual(second.remaining_suppliers, 0)
        self.assertIsNone(second.next_after_cnpj)
        self.assertEqual(first.cnpjs + second.cnpjs, tuple(sorted(set(suppliers))))

    def test_rejects_invalid_limit_and_checkpoint(self) -> None:
        with self.assertRaisesRegex(ValueError, "limit"):
            plan_supplier_batch((), after_cnpj=None, limit=0)
        with self.assertRaisesRegex(ValueError, "checkpoint"):
            plan_supplier_batch((), after_cnpj="invalido", limit=100)

    def test_marks_incomplete_supplier_cycle_as_partial_with_checkpoint(self) -> None:
        control = RecordingControl()
        summary = CGUSanctionCollectionSummary(
            queried_cnpjs=100,
            sanctions=3,
            sanctioned_cnpjs=2,
            skipped_natural_persons=0,
            bundle_bytes=500,
            inserted_records=3,
            existing_records=0,
            bundle_sha256="a" * 64,
            total_suppliers=250,
            remaining_suppliers=150,
            next_after_cnpj="13654405000195",
        )

        execute_controlled_sanction_collection(
            control=control,
            operation=lambda: summary,
        )

        self.assertEqual(control.completed["outcome"], CollectionOutcome.PARTIAL)
        self.assertEqual(
            control.completed["checkpoint"]["next_after_cnpj"],
            "13654405000195",
        )
        self.assertEqual(control.completed["checkpoint"]["remaining_suppliers"], 150)

    def test_marks_last_supplier_batch_as_complete_and_resets_cursor(self) -> None:
        control = RecordingControl()
        summary = CGUSanctionCollectionSummary(
            queried_cnpjs=42,
            sanctions=1,
            sanctioned_cnpjs=1,
            skipped_natural_persons=0,
            bundle_bytes=500,
            inserted_records=1,
            existing_records=0,
            bundle_sha256="b" * 64,
            total_suppliers=242,
            remaining_suppliers=0,
            next_after_cnpj=None,
        )

        execute_controlled_sanction_collection(
            control=control,
            operation=lambda: summary,
        )

        self.assertEqual(control.completed["outcome"], CollectionOutcome.COMPLETE)
        self.assertIsNone(control.completed["checkpoint"]["next_after_cnpj"])


if __name__ == "__main__":
    unittest.main()
