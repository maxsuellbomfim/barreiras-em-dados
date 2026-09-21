import hashlib
import json
import unittest
from types import SimpleNamespace

from barreiras_collectors.commands import collect_pncp_publication_evidence as cmd
from barreiras_collectors.connectors.pncp import RegistrySnapshot


class PublicationEvidenceTests(unittest.TestCase):
    def collect(self, payload, page=1):
        saved = []

        def fetch(resource, url):
            body = json.dumps(payload).encode()
            return RegistrySnapshot(
                resource,
                url,
                url,
                "2026-09-21T00:00:00Z",
                200,
                body,
                hashlib.sha256(body).hexdigest(),
                "application/json",
            )

        result = cmd.collect_page(
            since="2026-09-01",
            until="2026-09-07",
            page=page,
            service=SimpleNamespace(
                persist=lambda snapshot: (
                    saved.append(snapshot) or SimpleNamespace(raw_artifact_id="id")
                )
            ),
            fetch=fetch,
        )
        self.assertEqual(len(saved), 1)
        self.assertFalse(result["publication_authorized"])
        return result

    def payload(self):
        return {
            "data": [
                {
                    "numeroControlePNCP": "13654405000195-2-000023/2024",
                    "orgaoEntidade": {"cnpj": "13654405000195"},
                }
            ],
            "numeroPagina": 1,
            "totalPaginas": 1,
            "totalRegistros": 1,
            "paginasRestantes": 0,
        }

    def test_old_contract_year_is_not_excluded_from_publication_window(self):
        result = self.collect(self.payload())
        self.assertEqual(result["records_on_page"], 1)
        self.assertIsNone(result["next_page"])
        self.assertFalse(result["window_complete"])

    def test_explicit_empty_only(self):
        payload = dict(
            data=[],
            numeroPagina=1,
            totalPaginas=0,
            totalRegistros=0,
            paginasRestantes=0,
        )
        self.assertEqual(self.collect(payload)["records_on_page"], 0)
        for invalid in ({}, {"data": []}, {**payload, "totalRegistros": 1}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.collect(invalid)

    def test_invalid_pagination_and_owner_are_rejected(self):
        for changes in (
            {"numeroPagina": 2},
            {"totalPaginas": True},
            {"paginasRestantes": 1},
            {"totalRegistros": 51},
            {"data": [{"numeroControlePNCP": "other"}]},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.collect({**self.payload(), **changes})

    def test_window_is_bounded_before_network(self):
        for since, until, page in [
            ("2026-09-01", "2026-09-08", 1),
            ("2026-09-07", "2026-09-01", 1),
            ("2026-09-01", "2026-09-07", 0),
        ]:
            with self.assertRaises(ValueError):
                cmd.page_request(since, until, page)

    def test_continuation_is_page_scoped(self):
        payload = self.payload()
        payload.update(totalRegistros=51, totalPaginas=2, paginasRestantes=1)
        payload["data"] = [
            {
                **payload["data"][0],
                "numeroControlePNCP": f"13654405000195-2-{i:06d}/2024",
            }
            for i in range(1, 51)
        ]
        result = self.collect(payload)
        self.assertEqual(result["next_page"], 2)
        self.assertFalse(result["window_complete"])
        payload.update(numeroPagina=2, paginasRestantes=0)
        payload["data"] = [self.payload()["data"][0]]
        self.assertIsNone(self.collect(payload, page=2)["next_page"])

    def test_duplicate_controls_fail(self):
        payload = self.payload()
        payload.update(totalRegistros=2)
        payload["data"] *= 2
        with self.assertRaises(ValueError):
            self.collect(payload)

    def test_source_failure_does_not_return_success(self):
        def unavailable(*args):
            raise RuntimeError("HTTP 503")

        with self.assertRaises(RuntimeError):
            cmd.collect_page(
                since="2026-09-01",
                until="2026-09-07",
                page=1,
                service=None,
                fetch=unavailable,
            )
