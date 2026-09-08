import hashlib
import json
import unittest
from copy import deepcopy

from barreiras_collectors.connectors.fns_comparison_freshness import (
    inspect_comparison_freshness,
)


class FreshnessTests(unittest.TestCase):
    def setUp(self):
        url = "https://consultafns.saude.gov.br/recursos/consulta-detalhada/"
        self.evidence = [
            dict(
                request_url=url + "detalhe-pagamento?acoes=66458&page=1&count=10",
                final_url=url + "detalhe-pagamento?acoes=66458&page=1&count=10",
                sha256="a" * 64,
            ),
            dict(
                request_url=url
                + "detalhe-ordem-bancaria?numeroDocumentoSiafi=012009&page=1&count=10",
                final_url=url
                + "detalhe-ordem-bancaria?numeroDocumentoSiafi=012009&page=1&count=10",
                sha256="b" * 64,
            ),
        ]
        self.payload = dict(
            methodology_version="fns-document-comparison/1.0.0",
            publication_allowed=False,
            status="consistent_documentary_pair",
            payment_evidence=self.evidence[:1],
            order_evidence=self.evidence[1:],
        )
        self.artifacts = [
            dict(e, retrieved_at="2026-09-08T00:00:00+00:00", http_status=200)
            for e in self.evidence
        ]

    def inspect(self):
        sha = hashlib.sha256(
            json.dumps(
                self.payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        return inspect_comparison_freshness(self.payload, sha, self.artifacts)

    def test_current_is_documentary_only_and_output_minimized(self):
        r = self.inspect()
        self.assertEqual(r["status"], "current_preserved_evidence")
        self.assertEqual(r["comparison_status"], "consistent_documentary_pair")
        self.assertFalse(r["publication_allowed"])
        self.assertNotIn("request_url", r)

    def test_newer_bytes_invalidate_previous_match(self):
        self.artifacts.append(
            dict(
                self.artifacts[-1], retrieved_at="2026-09-09T00:00:00Z", sha256="c" * 64
            )
        )
        self.assertEqual(self.inspect()["status"], "stale_evidence")

    def test_reobserved_same_bytes_and_reordered_query_are_not_duplicates(self):
        a = dict(self.artifacts[-1], retrieved_at="2026-09-09T00:00:00Z")
        a["request_url"] = a["request_url"].replace(
            "numeroDocumentoSiafi=012009&page=1&count=10",
            "count=10&page=1&numeroDocumentoSiafi=012009",
        )
        self.artifacts.append(a)
        self.assertEqual(self.inspect()["status"], "current_preserved_evidence")

    def test_tied_conflicting_observations_block(self):
        self.artifacts.append(dict(self.artifacts[-1], sha256="c" * 64))
        self.assertEqual(self.inspect()["status"], "conflicting_evidence")

    def test_missing_or_bad_response_never_confirms(self):
        original = deepcopy(self.artifacts)
        self.artifacts.pop()
        self.assertEqual(self.inspect()["status"], "missing_evidence")
        self.artifacts = original
        self.artifacts[-1]["http_status"] = 500
        self.assertEqual(self.inspect()["status"], "invalid_evidence")

    def test_invalid_hash_method_or_timestamp_blocks(self):
        self.assertEqual(
            inspect_comparison_freshness(self.payload, "0" * 64, self.artifacts)[
                "status"
            ],
            "invalid_comparison",
        )
        self.payload["methodology_version"] = "new-method"
        self.assertEqual(self.inspect()["status"], "unsupported_methodology")
        self.payload["methodology_version"] = "fns-document-comparison/1.0.0"
        self.artifacts[-1]["retrieved_at"] = "2026-09-08"
        self.assertEqual(self.inspect()["status"], "invalid_evidence")

    def test_empty_order_remains_absence_when_current(self):
        self.payload["status"] = "order_not_found"
        self.assertEqual(self.inspect()["comparison_status"], "order_not_found")

    def test_new_pagination_does_not_leave_old_comparison_current(self):
        a = dict(self.artifacts[-1], retrieved_at="2026-09-09T00:00:00Z")
        a["request_url"] = a["request_url"].replace("page=1", "page=2")
        a["final_url"] = a["request_url"]
        self.artifacts.append(a)
        self.assertEqual(self.inspect()["status"], "pagination_changed")
