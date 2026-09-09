import copy
import hashlib
import json
import unittest
from urllib.parse import parse_qs, urlsplit

from barreiras_collectors.connectors.fns_collection_resume import collect_year
from barreiras_collectors.http import HttpResponse


class Store:
    def __init__(self):
        self.data = {}

    def load(self, key):
        return copy.deepcopy(self.data.get(key))

    def save(self, key, value):
        self.data[key] = copy.deepcopy(value)


class Transport:
    def __init__(self, store):
        self.store, self.calls = store, []
        self.fail = False
        self.catalog_total = 1

    def get(self, url, **kwargs):
        assert self.store.data["run"]["status"] == "running"
        self.calls.append(url)
        if self.fail:
            raise OSError("PRIVATE_URL_AND_IDENTIFIER")
        q = parse_qs(urlsplit(url).query)
        page, count = int(q["page"][0]), int(q["count"][0])
        total = self.catalog_total if count == 10 else 26
        rows = (
            [
                dict(cpfCnpj=str(i + 1), uf="BA", codigoMunicipioIBGE="290320")
                for i in range((page - 1) * count, min(page * count, total))
            ]
            if count == 10
            else [
                dict(uf="BA", anoPagamento="2025", numeroDocumentoSiafi=str(i))
                for i in range((page - 1) * count, min(page * count, total))
            ]
        )
        body = json.dumps(
            dict(
                resultado=dict(
                    dados=rows,
                    total=total,
                    pagina=page - 1,
                    totalPaginas=(total + count - 1) // count,
                    itensPorPagina=count,
                )
            )
        ).encode()
        return HttpResponse(200, {"Content-Type": "application/json"}, body, url)


class ResumeTests(unittest.TestCase):
    def test_private_observations_are_delivered_only_after_complete_acquisition(self):
        store = Store()
        transport = Transport(store)
        observations = []
        partial = collect_year(
            2025,
            store,
            transport,
            max_requests=1,
            sleep=lambda _: None,
            observations=observations,
        )
        self.assertEqual(partial["status"], "partial")
        self.assertEqual(observations, [])
        complete = collect_year(
            2025, store, transport, sleep=lambda _: None, observations=observations
        )
        self.assertEqual(complete["status"], "complete")
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["beneficiary"], "1")
        self.assertEqual(len(observations[0]["payment_captures"]), 2)
        self.assertNotIn("payment_captures", complete)
        self.assertNotIn("beneficiary", complete)
        self.assertEqual(len(transport.calls), 3)
        # A reused result list cannot append stale observations from another run.
        failed = collect_year(
            2025, store, transport, sleep=lambda _: None, observations=observations
        )
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(len(observations), 1)

    def test_multi_page_catalog_and_official_empty_are_distinct(self):
        for total, expected_status, pages in [(0, "empty", 1), (11, "complete", 24)]:
            store = Store()
            transport = Transport(store)
            transport.catalog_total = total
            result = collect_year(
                2025, store, transport, max_requests=50, sleep=lambda _: None
            )
            self.assertEqual(result["status"], expected_status)
            self.assertEqual(result["catalog_entities"], total)
            self.assertEqual(result["pages_preserved"], pages)

    def test_pause_resume_and_completed_replay_do_not_refetch(self):
        store = Store()
        transport = Transport(store)
        waits = []
        first = collect_year(2025, store, transport, max_requests=1, sleep=waits.append)
        self.assertEqual(first["status"], "partial")
        second = collect_year(
            2025, store, transport, max_requests=3, sleep=waits.append
        )
        self.assertEqual(second["status"], "complete")
        self.assertEqual(second["pages_preserved"], 3)
        self.assertFalse(second["publication_allowed"])
        self.assertEqual(len(transport.calls), 3)
        self.assertEqual(
            collect_year(2025, store, transport, sleep=waits.append)["status"],
            "complete",
        )
        self.assertEqual(len(transport.calls), 3)
        self.assertTrue(all(w >= 10 for w in waits))

    def test_failures_are_sanitized_retry_bounded_and_resumable(self):
        store = Store()
        transport = Transport(store)
        transport.fail = True
        result = collect_year(2025, store, transport, sleep=lambda _: None)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(transport.calls), 3)
        self.assertNotIn("PRIVATE", json.dumps(store.data))
        transport.fail = False
        self.assertEqual(
            collect_year(2025, store, transport, sleep=lambda _: None)["status"],
            "complete",
        )

    def test_changed_page_totals_corruption_and_year_reuse_block(self):
        for mode in ["total", "hash", "year"]:
            store = Store()
            transport = Transport(store)
            collect_year(2025, store, transport, sleep=lambda _: None)
            if mode != "year":
                key = hashlib.sha256(transport.calls[-1].encode()).hexdigest()
                if mode == "hash":
                    store.data[key]["sha256"] = "0" * 64
                else:
                    data = json.loads(store.data[key]["body"])
                    data["resultado"]["total"] = 27
                    raw = json.dumps(data).encode()
                    store.data[key].update(
                        body=raw,
                        byte_size=len(raw),
                        sha256=hashlib.sha256(raw).hexdigest(),
                    )
            self.assertEqual(
                collect_year(
                    2024 if mode == "year" else 2025,
                    store,
                    transport,
                    sleep=lambda _: None,
                )["status"],
                "failed",
            )
