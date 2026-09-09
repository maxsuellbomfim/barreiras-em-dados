import unittest

from barreiras_collectors.persistence.fns_pharmacy import (
    prepare_pharmacy_import,
    prepare_pharmacy_refresh,
)

from tests.collectors.test_fns_pharmacy_identity import register
from tests.collectors.test_fns_pharmacy_reconciliation import observation
from tests.collectors.test_fns_pharmacy_refresh import append_payment


class PharmacyImportTests(unittest.TestCase):
    def test_refresh_plan_requires_validated_additions_and_binds_baseline(self):
        before = observation()
        after = append_payment(before)
        after["payment_capture"]["received_at"] = "2026-09-09T04:00:00Z"
        reg = register()
        reg["retrieved_at"] = "2026-09-08T16:00:00Z"
        args = dict(
            previous=before,
            current=after,
            previous_register=reg,
            current_register=reg,
            previous_approved=True,
            previous_snapshot_id=19,
        )
        result = prepare_pharmacy_refresh(**args)
        self.assertEqual(result["status"], "append_only")
        plan = result["plan"]
        self.assertEqual(plan["refresh"], {plan["snapshots"][0]["scope_key"]: 19})
        self.assertFalse(plan["publication_allowed"])
        args["current"] = before
        self.assertIsNone(prepare_pharmacy_refresh(**args)["plan"])
        args["current"] = after
        args["previous_approved"] = False
        self.assertIsNone(prepare_pharmacy_refresh(**args)["plan"])

    def test_plan_is_deterministic_and_never_approves(self):
        obs = observation()
        obs["payment_capture"]["received_at"] = "2026-09-08T16:00:00+00:00"
        reg = register()
        reg["retrieved_at"] = "2026-09-08T16:00:00+00:00"
        plan = prepare_pharmacy_import([obs], register_capture=reg)
        self.assertEqual(plan, prepare_pharmacy_import([obs], register_capture=reg))
        self.assertEqual(len(plan["artifacts"]), 2)
        self.assertEqual(len(plan["snapshots"][0]["documents"]), 1)
        self.assertFalse(plan["publication_allowed"])
        self.assertEqual(
            plan["snapshots"][0]["documents"][0]["payload"]["net"], "10.00"
        )

    def test_invalid_or_repeated_capture_cannot_be_import_plan(self):
        obs = observation()
        reg = register()
        with self.assertRaises(ValueError):
            prepare_pharmacy_import([obs], register_capture=reg)
        obs["payment_capture"]["received_at"] = "2026-09-08T16:00:00Z"
        reg["retrieved_at"] = "2026-09-08T16:00:00Z"
        with self.assertRaises(ValueError):
            prepare_pharmacy_import([obs, obs], register_capture=reg)
