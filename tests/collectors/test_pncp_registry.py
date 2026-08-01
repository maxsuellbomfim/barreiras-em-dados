from __future__ import annotations

import hashlib
import json
import unittest

from barreiras_collectors.connectors.pncp import (
    REGISTRY_RESOURCES,
    PncpError,
    fetch_registry_snapshot,
)
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.resilience import RetryPolicy

ORGAO_URL = REGISTRY_RESOURCES[0][1]


class ScriptedTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = list(responses)
        self.requests: list[str] = []

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds, max_body_bytes
        self.requests.append(url)
        return self.responses.pop(0)


def response(status: int, body: bytes) -> HttpResponse:
    return HttpResponse(
        status=status,
        headers={"Content-Type": "application/json"},
        body=body,
        final_url=ORGAO_URL,
    )


class PncpRegistryTests(unittest.TestCase):
    def test_snapshot_preserves_bytes_and_hash(self) -> None:
        body = json.dumps({"cnpj": "13654405000195"}).encode()
        transport = ScriptedTransport([response(200, body)])

        snapshot = fetch_registry_snapshot(
            "orgao",
            ORGAO_URL,
            transport=transport,
            retry_policy=RetryPolicy(max_attempts=2),
            sleep=lambda _s: None,
        )

        self.assertEqual(snapshot.body, body)
        self.assertEqual(
            snapshot.body_sha256,
            hashlib.sha256(body).hexdigest(),
        )
        self.assertEqual(snapshot.media_type, "application/json")

    def test_retries_transient_and_succeeds(self) -> None:
        body = b"[]"
        transport = ScriptedTransport(
            [response(503, b""), response(200, body)]
        )

        snapshot = fetch_registry_snapshot(
            "unidades",
            ORGAO_URL,
            transport=transport,
            retry_policy=RetryPolicy(max_attempts=3),
            sleep=lambda _s: None,
        )

        self.assertEqual(snapshot.body, body)
        self.assertEqual(len(transport.requests), 2)

    def test_non_json_body_is_explicit_failure(self) -> None:
        transport = ScriptedTransport([response(200, b"<html>bloqueio")])

        with self.assertRaises(PncpError):
            fetch_registry_snapshot(
                "orgao",
                ORGAO_URL,
                transport=transport,
                retry_policy=RetryPolicy(max_attempts=2),
                sleep=lambda _s: None,
            )

    def test_permanent_error_does_not_retry(self) -> None:
        transport = ScriptedTransport([response(404, b"{}")])

        with self.assertRaises(PncpError):
            fetch_registry_snapshot(
                "orgao",
                ORGAO_URL,
                transport=transport,
                retry_policy=RetryPolicy(max_attempts=3),
                sleep=lambda _s: None,
            )

        self.assertEqual(len(transport.requests), 1)


if __name__ == "__main__":
    unittest.main()
