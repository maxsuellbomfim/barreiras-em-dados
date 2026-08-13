from __future__ import annotations

import hashlib
import unittest
from datetime import UTC, datetime

from barreiras_collectors.connectors.bahia_state_loa_amendments import (
    BLOCKED_YEAR_REASONS,
    YEARLY_ANNEXES,
    BahiaStateLoaAnnexError,
    fetch_state_loa_amendment_annex,
)
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.resilience import RetryPolicy


def pdf_bytes(label: str = "official") -> bytes:
    return (
        b"%PDF-1.7\n"
        + label.encode("ascii")
        + b"\n1 0 obj<</Type/Catalog>>endobj\nstartxref\n0\n%%EOF\n"
    )


class SequenceTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, int]] = []

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds
        self.requests.append((url, max_body_bytes))
        return self.responses.pop(0)


def response(
    body: bytes,
    *,
    final_url: str,
    content_type: str = "application/pdf",
    status: int = 200,
) -> HttpResponse:
    return HttpResponse(
        status=status,
        headers={
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
            "ETag": '"official-version"',
            "X-Api-Key": "never-preserve",
        },
        body=body,
        final_url=final_url,
    )


class BahiaStateLoaAmendmentTests(unittest.TestCase):
    def test_contract_has_municipal_annexes_without_relabeling_execution(self) -> None:
        self.assertEqual(set(YEARLY_ANNEXES), {2022, 2023, 2024, 2025, 2026})
        for year, contract in YEARLY_ANNEXES.items():
            with self.subTest(year=year):
                self.assertEqual(contract.budget_stage, "authorized")
                self.assertEqual(contract.territorial_scope, "municipality_explicit")
                self.assertTrue(contract.url.startswith("https://www.ba.gov.br/"))
        self.assertEqual(YEARLY_ANNEXES[2025].annex_code, "III")
        self.assertEqual(YEARLY_ANNEXES[2026].annex_code, "I")
        self.assertIn("2020", BLOCKED_YEAR_REASONS[2021])

    def test_fetches_exact_official_pdf_and_keeps_only_safe_headers(self) -> None:
        body = pdf_bytes("loa-2025")
        contract = YEARLY_ANNEXES[2025]
        transport = SequenceTransport([response(body, final_url=contract.url)])

        snapshot = fetch_state_loa_amendment_annex(
            2025,
            transport=transport,
            retry_policy=RetryPolicy(max_attempts=1),
            sleep=lambda _seconds: None,
            now=lambda: datetime(2026, 8, 13, 17, 0, tzinfo=UTC),
        )

        self.assertEqual(snapshot.fiscal_year, 2025)
        self.assertEqual(snapshot.annex_code, "III")
        self.assertEqual(snapshot.total_items, 1)
        self.assertEqual(snapshot.body_sha256, hashlib.sha256(body).hexdigest())
        self.assertEqual(snapshot.items[0]["budget_stage"], "authorized")
        self.assertEqual(
            snapshot.items[0]["territorial_scope"], "municipality_explicit"
        )
        self.assertNotIn("x-api-key", snapshot.response_headers)
        self.assertEqual(transport.requests, [(contract.url, 96 * 1024 * 1024)])

    def test_rejects_redirect_content_drift_and_unsupported_year(self) -> None:
        contract = YEARLY_ANNEXES[2025]
        cases = (
            response(pdf_bytes(), final_url="https://www.ba.gov.br/other.pdf"),
            response(b"not-a-pdf", final_url=contract.url),
            response(pdf_bytes(), final_url=contract.url, content_type="text/html"),
        )
        for candidate in cases:
            with self.subTest(final_url=candidate.final_url):
                with self.assertRaises(BahiaStateLoaAnnexError):
                    fetch_state_loa_amendment_annex(
                        2025,
                        transport=SequenceTransport([candidate]),
                        retry_policy=RetryPolicy(max_attempts=1),
                        sleep=lambda _seconds: None,
                    )

        with self.assertRaisesRegex(BahiaStateLoaAnnexError, "bloqueado"):
            fetch_state_loa_amendment_annex(2021)
        with self.assertRaisesRegex(BahiaStateLoaAnnexError, "suportado"):
            fetch_state_loa_amendment_annex(2020)


if __name__ == "__main__":
    unittest.main()
