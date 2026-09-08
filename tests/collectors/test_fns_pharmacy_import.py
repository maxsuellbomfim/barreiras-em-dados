import unittest

from barreiras_collectors.persistence.fns_pharmacy import prepare_pharmacy_import

from tests.collectors.test_fns_pharmacy_identity import register
from tests.collectors.test_fns_pharmacy_reconciliation import observation


class PharmacyImportTests(unittest.TestCase):
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
