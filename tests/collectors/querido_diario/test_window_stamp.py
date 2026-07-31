from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path

from barreiras_collectors.connectors.querido_diario import QueridoDiarioClient
from barreiras_collectors.http import HttpResponse

ROOT = Path(__file__).parents[3]
FIXTURE_PATH = ROOT / "fixtures" / "sources" / "querido_diario" / "gazettes-page-1.json"


class StaticTransport:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds, max_body_bytes
        return HttpResponse(
            status=200,
            headers={"Content-Type": "application/json"},
            body=self.body,
            final_url=url,
        )


class NoopRateLimiter:
    def acquire(self) -> None:
        return None


class WindowStampTests(unittest.TestCase):
    def make_client(self) -> QueridoDiarioClient:
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        body = json.dumps(
            fixture["response"],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return QueridoDiarioClient(
            transport=StaticTransport(body),
            rate_limiter=NoopRateLimiter(),  # type: ignore[arg-type]
        )

    def test_page_carries_declared_collection_window(self) -> None:
        page = next(
            self.make_client().iter_gazette_pages(
                published_since=date(2026, 6, 10),
                published_until=date(2026, 6, 11),
                page_size=100,
            )
        )

        self.assertEqual(page.window_start, "2026-06-10")
        self.assertEqual(page.window_end, "2026-06-11")

    def test_window_is_none_when_not_declared(self) -> None:
        page = next(self.make_client().iter_gazette_pages(page_size=100))

        self.assertIsNone(page.window_start)
        self.assertIsNone(page.window_end)


if __name__ == "__main__":
    unittest.main()
