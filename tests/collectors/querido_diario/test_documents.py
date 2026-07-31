from __future__ import annotations

import hashlib
import unittest

from barreiras_collectors.connectors.gazette_documents import (
    GazetteDocumentClient,
)
from barreiras_collectors.connectors.querido_diario import (
    PermanentHttpError,
    SourceUnavailableError,
)
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.resilience import RetryPolicy

PDF_URL = "https://data.queridodiario.ok.org.br/2903201/2026-07-01/exemplo.pdf"


class ScriptedTransport:
    def __init__(self, responses: list[HttpResponse | Exception]) -> None:
        self.responses = list(responses)
        self.requests: list[str] = []

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout_seconds: float,
        max_body_bytes: int,
    ) -> HttpResponse:
        del headers, timeout_seconds, max_body_bytes
        self.requests.append(url)
        outcome = self.responses.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class NoopRateLimiter:
    def acquire(self) -> None:
        return None


def response(status: int, body: bytes = b"%PDF-1.7 corpo") -> HttpResponse:
    return HttpResponse(
        status=status,
        headers={
            "Content-Type": "application/pdf",
            "ETag": '"doc-etag"',
            "X-Internal": "must-not-leak",
        },
        body=body,
        final_url=PDF_URL,
    )


def make_client(
    responses: list[HttpResponse | Exception],
    **overrides: object,
) -> tuple[GazetteDocumentClient, ScriptedTransport]:
    transport = ScriptedTransport(responses)
    options: dict[str, object] = {
        "max_document_bytes": 1024,
        "transport": transport,
        "rate_limiter": NoopRateLimiter(),
        "retry_policy": RetryPolicy(max_attempts=3),
        "sleep": lambda _seconds: None,
    }
    options.update(overrides)
    client = GazetteDocumentClient(**options)  # type: ignore[arg-type]
    return client, transport


class GazetteDocumentClientTests(unittest.TestCase):
    def test_success_preserves_bytes_hash_and_safe_headers(self) -> None:
        body = b"%PDF-1.7 conteudo oficial"
        client, transport = make_client([response(200, body)])

        document = client.fetch(PDF_URL, role="pdf")

        self.assertEqual(document.role, "pdf")
        self.assertEqual(document.raw_body, body)
        self.assertEqual(
            document.body_sha256,
            hashlib.sha256(body).hexdigest(),
        )
        self.assertEqual(document.body_size_bytes, len(body))
        self.assertEqual(document.media_type, "application/pdf")
        self.assertEqual(document.attempts, 1)
        self.assertNotIn("x-internal", document.response_headers)
        self.assertEqual(transport.requests, [PDF_URL])

    def test_retries_transient_error_and_succeeds(self) -> None:
        client, transport = make_client([response(503), response(200)])

        document = client.fetch(PDF_URL, role="pdf")

        self.assertEqual(document.attempts, 2)
        self.assertEqual(len(transport.requests), 2)

    def test_permanent_status_fails_without_retry(self) -> None:
        client, transport = make_client([response(404)])

        with self.assertRaises(PermanentHttpError):
            client.fetch(PDF_URL, role="pdf")

        self.assertEqual(len(transport.requests), 1)

    def test_exhausted_retries_raise_source_unavailable(self) -> None:
        client, _transport = make_client(
            [response(500), response(500), response(500)]
        )

        with self.assertRaises(SourceUnavailableError):
            client.fetch(PDF_URL, role="pdf")

    def test_rejects_unknown_role_and_disallowed_host(self) -> None:
        client, transport = make_client([response(200)])

        with self.assertRaises(ValueError):
            client.fetch(PDF_URL, role="html")
        with self.assertRaises(ValueError):
            client.fetch("https://malicioso.example/arquivo.pdf", role="pdf")

        self.assertEqual(transport.requests, [])


if __name__ == "__main__":
    unittest.main()
