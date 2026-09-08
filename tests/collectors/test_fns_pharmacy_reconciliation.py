import hashlib
import json
import unittest

from barreiras_collectors.connectors.fns_pharmacy_reconciliation import (
    reconcile_pharmacy_captures,
)

from tests.collectors.test_fns_pharmacy_identity import CNPJ, payment, register

OTHER = "11444777000161"


def observation(beneficiary=CNPJ, net="10.00", competence="JAN de 2025"):
    capture = payment()
    capture["request_url"] = capture["final_url"] = capture["request_url"].replace(
        CNPJ, beneficiary
    )
    data = json.loads(capture["body"])
    row = data["resultado"]["dados"][0]
    row["id"].update(ano=2025, mes=1)
    row["competencia"] = competence
    row.update(
        valorTotal=net,
        valorLiquido=net,
        valorDescontoTotal="0.00",
        valorTotalGeral=net,
        valorLiquidoGeral=net,
        valorDescontoTotalGeral="0.00",
    )
    capture["body"] = json.dumps(data).encode()
    capture["byte_size"] = len(capture["body"])
    capture["sha256"] = hashlib.sha256(capture["body"]).hexdigest()
    return dict(beneficiary=beneficiary, payment_year=2025, payment_capture=capture)


class PharmacyReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.register_capture = register(
            [
                [CNPJ, "FARMACIA A", "R", "B"],
                [OTHER, "FARMACIA B", "R", "B"],
            ]
        )

    def inspect(self, captures):
        return reconcile_pharmacy_captures(
            captures,
            register_capture=self.register_capture,
        )

    def test_shared_query_does_not_merge_beneficiaries_or_add_order_total(self):
        result = self.inspect([observation(), observation(OTHER, "20.00")])
        self.assertEqual(result["status"], "reconciled_private")
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(result["shared_order_queries"], 1)
        self.assertEqual(
            {r["amounts"]["net"] for r in result["records"]}, {"10.00", "20.00"}
        )
        self.assertFalse(result["publication_allowed"])
        self.assertNotIn("total", result)
        for secret in (CNPJ, OTHER, "DO_NOT_EXPOSE"):
            self.assertNotIn(secret, json.dumps(result))

    def test_replaying_same_capture_keeps_one_record_with_evidence(self):
        obs = observation()
        result = self.inspect([obs, obs])
        self.assertEqual(result["status"], "reconciled_private")
        self.assertEqual(len(result["records"]), 1)
        self.assertEqual(result["repeated_observations"], 1)
        self.assertEqual(len(result["records"][0]["evidence"]), 1)

    def test_changed_amount_or_competence_blocks_all_candidates(self):
        for altered in (
            observation(net="12.00"),
            observation(competence="FEV de 2025"),
        ):
            result = self.inspect([observation(), altered])
            self.assertEqual(result["status"], "review_required")
            self.assertEqual(result["records"], [])
            self.assertIn("conflicting_document", result["review_reasons"])

    def test_invalid_capture_or_unknown_institution_blocks_entire_batch(self):
        obs = observation()
        obs["payment_capture"]["sha256"] = "0" * 64
        self.assertEqual(
            self.inspect([observation(OTHER), obs])["status"], "invalid_evidence"
        )
        self.assertEqual(self.inspect([])["status"], "invalid_evidence")
        self.assertEqual(
            self.inspect([observation()] * 21)["status"], "invalid_evidence"
        )

    def test_new_snapshot_missing_document_is_not_silent_deletion(self):
        obs = observation()
        data = json.loads(obs["payment_capture"]["body"])
        data["resultado"]["dados"][0]["numeroDocumentoSiafi"] = "000002"
        capture = obs["payment_capture"]
        capture["body"] = json.dumps(data).encode()
        capture["byte_size"] = len(capture["body"])
        capture["sha256"] = hashlib.sha256(capture["body"]).hexdigest()
        result = self.inspect([observation(), obs])
        self.assertEqual(result["status"], "review_required")
        self.assertIn("snapshot_document_set_changed", result["review_reasons"])
        self.assertEqual(result["records"], [])

    def test_new_bytes_same_document_keep_both_evidence_references(self):
        obs = observation()
        capture = obs["payment_capture"]
        capture["body"] = json.dumps(json.loads(capture["body"]), indent=2).encode()
        capture["byte_size"] = len(capture["body"])
        capture["sha256"] = hashlib.sha256(capture["body"]).hexdigest()
        result = self.inspect([observation(), obs])
        reverse = self.inspect([obs, observation()])
        self.assertEqual(result, reverse)
        self.assertEqual(result["status"], "reconciled_private")
        self.assertEqual(len(result["records"]), 1)
        self.assertEqual(len(result["records"][0]["evidence"]), 2)

    def test_invalid_order_scope_cannot_create_shared_query(self):
        obs = observation()
        capture = obs["payment_capture"]
        data = json.loads(capture["body"])
        data["resultado"]["dados"][0]["id"]["mes"] = 13
        capture["body"] = json.dumps(data).encode()
        capture["byte_size"] = len(capture["body"])
        capture["sha256"] = hashlib.sha256(capture["body"]).hexdigest()
        self.assertEqual(self.inspect([obs])["status"], "invalid_evidence")
