import copy
import hashlib
import json
import unittest

from barreiras_collectors.connectors.fns_pharmacy_refresh import assess_refresh

from tests.collectors.test_fns_pharmacy_identity import register
from tests.collectors.test_fns_pharmacy_reconciliation import observation


def append_payment(obs):
    updated = copy.deepcopy(obs)
    capture = updated["payment_capture"]
    data = json.loads(capture["body"])
    row = copy.deepcopy(data["resultado"]["dados"][0])
    row["numeroDocumentoSiafi"] = "000002"
    data["resultado"]["dados"].append(row)
    data["resultado"]["total"] = 2
    for item in data["resultado"]["dados"]:
        item["valorTotalGeral"] = item["valorLiquidoGeral"] = "20.00"
    capture["body"] = json.dumps(data).encode()
    capture["sha256"] = hashlib.sha256(capture["body"]).hexdigest()
    capture["byte_size"] = len(capture["body"])
    return updated


class RefreshTests(unittest.TestCase):
    def inspect(
        self, current=None, previous=None, approved=True, current_register=None
    ):
        reg = register()
        return assess_refresh(
            previous=previous or observation(),
            current=current or observation(),
            previous_register=reg,
            current_register=current_register or reg,
            previous_approved=approved,
        )

    def test_same_documents_are_unchanged_not_a_new_publication(self):
        self.assertEqual(self.inspect()["status"], "unchanged")

    def test_only_additions_are_eligible_and_do_not_compute_money(self):
        result = self.inspect(current=append_payment(observation()))
        self.assertEqual(result["status"], "append_only")
        self.assertEqual(result["added_documents"], 1)
        self.assertEqual(result["retained_documents"], 1)
        self.assertFalse(result["publication_allowed"])
        self.assertNotIn("total", result)

    def test_missing_or_changed_previous_documents_require_review(self):
        for current, previous in [
            (observation(), append_payment(observation())),
            (observation(net="12.00"), observation()),
            (observation(competence="FEV de 2025"), observation()),
        ]:
            self.assertEqual(
                self.inspect(current, previous)["status"], "review_required"
            )

    def test_approval_register_change_and_invalid_bytes_never_pass(self):
        self.assertEqual(self.inspect(approved=False)["status"], "review_required")
        changed = register([["11222333000181", "OUTRO NOME", "R", "B"]])
        self.assertEqual(
            self.inspect(current_register=changed)["status"], "review_required"
        )
        obs = observation()
        obs["payment_capture"]["sha256"] = "0" * 64
        result = self.inspect(current=obs)
        self.assertEqual(result["status"], "invalid_evidence")
        self.assertNotIn("11222333000181", json.dumps(result))

    def test_different_year_or_beneficiary_is_not_same_scope(self):
        obs = observation()
        obs["payment_year"] = 2026
        self.assertEqual(self.inspect(current=obs)["status"], "review_required")
        self.assertEqual(
            self.inspect(current=observation("11444777000161"))["status"],
            "review_required",
        )

    def test_new_serialization_and_reordering_do_not_create_documents(self):
        previous = append_payment(observation())
        current = copy.deepcopy(previous)
        capture = current["payment_capture"]
        data = json.loads(capture["body"])
        data["resultado"]["dados"].reverse()
        capture["body"] = json.dumps(data, indent=2).encode()
        capture["sha256"] = hashlib.sha256(capture["body"]).hexdigest()
        capture["byte_size"] = len(capture["body"])
        result = self.inspect(current, previous)
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual(result["added_documents"], 0)
