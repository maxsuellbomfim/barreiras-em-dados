from __future__ import annotations

import hashlib
import json
import unittest

from barreiras_collectors.connectors.pncp import (
    PncpContractsResponseError,
    fetch_contratos_page,
)
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.resilience import RetryPolicy


class SequencedTransport:
    def __init__(self, *responses: tuple[int, bytes]) -> None:
        self.responses = list(responses)

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds, max_body_bytes
        status, body = self.responses.pop(0)
        return HttpResponse(
            status=status,
            headers={"X-Test": "kept"},
            body=body,
            final_url=url + "&final=1",
        )


def fetch(body: bytes, *, status: int = 200, pagina: int = 1):
    return fetch_contratos_page(
        ano=2026,
        sequencial=32,
        pagina=pagina,
        transport=SequencedTransport((status, body)),
        retry_policy=RetryPolicy(max_attempts=1),
        sleep=lambda _seconds: None,
    )


class PncpContractResponseEvidenceTests(unittest.TestCase):
    def test_explicit_unpublished_message_is_diagnostic_not_empty(self):
        payload = {
            "status": "404",
            "message": "Não há contrato publicado no PNCP para esta contratação.",
            "path": "/pncp-api/v1/orgaos/13654405000195/contratos/contratacao/2026/32",
        }
        for changes, reason in (
            ({}, "source_reports_no_published_contract"),
            ({"status": "500"}, "http_not_found"),
            ({"path": payload["path"].replace("/32", "/99")}, "http_not_found"),
            ({"message": "Não encontrado"}, "http_not_found"),
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(PncpContractsResponseError) as raised:
                    fetch(json.dumps({**payload, **changes}).encode(), status=404)
                self.assertEqual(raised.exception.reason, reason)
                self.assertNotIn(payload["message"], str(raised.exception))

    def test_404_and_204_are_typed_without_body_or_secret(self) -> None:
        body_marker = "private-body-marker"
        for status, reason in ((404, "http_not_found"), (204, "http_no_content")):
            with self.subTest(status=status):
                with self.assertRaises(PncpContractsResponseError) as raised:
                    fetch(body_marker.encode(), status=status)
                error = raised.exception
                self.assertEqual(error.status, status)
                self.assertEqual(error.http_status, status)
                self.assertEqual(error.reason, reason)
                self.assertNotIn(body_marker, str(error))
                self.assertNotIn(body_marker, repr(error))

    def test_empty_array_is_a_persistable_page_with_raw_evidence(self) -> None:
        body = b"[]"
        page = fetch(body)

        self.assertIsNotNone(page)
        assert page is not None
        self.assertEqual(page.items, ())
        self.assertEqual(page.raw_body, body)
        self.assertEqual(page.body_sha256, hashlib.sha256(body).hexdigest())
        self.assertEqual(page.http_status, 200)
        self.assertIn("/contratos/contratacao/2026/32", page.request_url)
        self.assertEqual(page.final_url, page.request_url + "&final=1")

    def test_paginated_contract_counts_are_preserved(self) -> None:
        body = json.dumps(
            {
                "data": [{"numeroControlePNCP": "contract-1"}],
                "totalRegistros": 3,
                "totalPaginas": 3,
            }
        ).encode()

        page = fetch(body)

        self.assertIsNotNone(page)
        assert page is not None
        self.assertEqual(page.items, ({"numeroControlePNCP": "contract-1"},))
        self.assertEqual(page.total_registros, 3)
        self.assertEqual(page.total_paginas, 3)

    def test_embedded_error_is_typed_and_sanitized(self) -> None:
        body = json.dumps({"error": "private backend detail", "data": []}).encode()

        with self.assertRaises(PncpContractsResponseError) as raised:
            fetch(body)

        self.assertEqual(raised.exception.status, 200)
        self.assertEqual(raised.exception.reason, "invalid_response")
        self.assertNotIn("private backend detail", str(raised.exception))

    def test_other_embedded_error_statuses_cannot_certify_empty(self) -> None:
        for status in (401, 403, 404, 422, 429, 502, 503):
            with self.subTest(status=status):
                body = json.dumps(
                    {
                        "data": [],
                        "totalRegistros": 0,
                        "totalPaginas": 0,
                        "status": status,
                    }
                ).encode()
                with self.assertRaises(PncpContractsResponseError):
                    fetch(body)

    def test_invalid_json_and_root_are_typed_and_sanitized(self) -> None:
        for body in (b"not-json", b'"string-root"', b'{"data": "not-a-list"}'):
            with self.subTest(body=body):
                with self.assertRaises(PncpContractsResponseError) as raised:
                    fetch(body)
                self.assertEqual(raised.exception.status, 200)
                self.assertEqual(raised.exception.reason, "invalid_response")

    def test_count_booleans_negatives_floats_and_invalid_values_fail(self) -> None:
        invalid_values = (True, False, -1, 1.5, "3", None)
        for field in ("totalRegistros", "totalPaginas"):
            for value in invalid_values:
                with self.subTest(field=field, value=value):
                    payload = {
                        "data": [{"numeroControlePNCP": "contract-1"}],
                        "totalRegistros": 1,
                        "totalPaginas": 1,
                    }
                    payload[field] = value
                    with self.assertRaises(PncpContractsResponseError):
                        fetch(json.dumps(payload).encode())

    def test_missing_count_metadata_does_not_assume_completeness(self) -> None:
        for missing in ("totalRegistros", "totalPaginas"):
            with self.subTest(missing=missing):
                payload = {
                    "data": [{"numeroControlePNCP": "contract-1"}],
                    "totalRegistros": 1,
                    "totalPaginas": 1,
                }
                del payload[missing]
                with self.assertRaises(PncpContractsResponseError):
                    fetch(json.dumps(payload).encode())

    def test_invalid_item_types_are_not_dropped(self) -> None:
        for items in ([{"ok": True}, "bad"], [None], [1]):
            with self.subTest(items=items):
                payload = {
                    "data": items,
                    "totalRegistros": len(items),
                    "totalPaginas": 1,
                }
                with self.assertRaises(PncpContractsResponseError):
                    fetch(json.dumps(payload).encode())

    def test_empty_data_must_agree_with_counts_and_requested_position(self) -> None:
        contradictory = (
            {"data": [], "totalRegistros": 1, "totalPaginas": 1},
            {"data": [], "totalRegistros": 0, "totalPaginas": 2},
        )
        for payload in contradictory:
            with self.subTest(payload=payload):
                with self.assertRaises(PncpContractsResponseError):
                    fetch(json.dumps(payload).encode())

        page = fetch(
            json.dumps({"data": [], "totalRegistros": 0, "totalPaginas": 1}).encode()
        )
        self.assertIsNotNone(page)
        assert page is not None
        self.assertEqual(page.items, ())

        page = fetch(
            json.dumps({"data": [], "totalRegistros": 0, "totalPaginas": 0}).encode()
        )
        self.assertIsNotNone(page)


if __name__ == "__main__":
    unittest.main()
