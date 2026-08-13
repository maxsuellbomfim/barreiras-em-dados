from __future__ import annotations

import unittest
from urllib.error import URLError

from barreiras_reconciliation.tse_registry_fetch import (
    CandidateRegistryDownloadError,
    fetch_candidate_registry,
)


class FakeResponse:
    def __init__(self, payload: bytes, url: str) -> None:
        self.payload = payload
        self.url = url
        self.status = 200

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int) -> bytes:
        return self.payload[:size]

    def geturl(self) -> str:
        return self.url


class TseRegistryFetchTests(unittest.TestCase):
    def test_accepts_only_the_official_https_host(self) -> None:
        calls: list[str] = []

        def opener(request: object, *, timeout: float) -> FakeResponse:
            calls.append(request.full_url)
            self.assertEqual(timeout, 60.0)
            return FakeResponse(b"PK official", request.full_url)

        result = fetch_candidate_registry(2024, opener=opener, max_bytes=100)

        self.assertEqual(result, b"PK official")
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].startswith("https://cdn.tse.jus.br/"))

    def test_rejects_a_redirect_outside_the_official_host(self) -> None:
        def opener(request: object, *, timeout: float) -> FakeResponse:
            return FakeResponse(b"PK", "https://example.org/candidates.zip")

        with self.assertRaisesRegex(CandidateRegistryDownloadError, "host oficial"):
            fetch_candidate_registry(2024, opener=opener, max_bytes=100)

    def test_rejects_an_oversized_archive(self) -> None:
        def opener(request: object, *, timeout: float) -> FakeResponse:
            return FakeResponse(b"x" * 11, request.full_url)

        with self.assertRaisesRegex(CandidateRegistryDownloadError, "limite"):
            fetch_candidate_registry(2024, opener=opener, max_bytes=10)

    def test_retries_transient_transport_failures(self) -> None:
        attempts = 0

        def opener(request: object, *, timeout: float) -> FakeResponse:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise URLError("temporary")
            return FakeResponse(b"PK", request.full_url)

        result = fetch_candidate_registry(
            2024,
            opener=opener,
            max_bytes=100,
            sleep=lambda _: None,
        )

        self.assertEqual(result, b"PK")
        self.assertEqual(attempts, 3)


if __name__ == "__main__":
    unittest.main()
