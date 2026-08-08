from __future__ import annotations

import json
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from barreiras_collectors.connectors.querido_diario import (
    PartialCollectionError,
    PermanentHttpError,
    QueridoDiarioClient,
    SourceContractError,
    SourceUnavailableError,
)
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    RetryPolicy,
)

ROOT = Path(__file__).parents[3]
FIXTURE_PATH = ROOT / "fixtures" / "sources" / "querido_diario" / "gazettes-page-1.json"


class FakeTransport:
    def __init__(self, responses: list[HttpResponse | BaseException]) -> None:
        self.responses = list(responses)
        self.calls: list[str] = []

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout_seconds: float,
        max_body_bytes: int,
    ) -> HttpResponse:
        self.calls.append(url)
        if not self.responses:
            raise AssertionError("FakeTransport sem resposta configurada.")
        result = self.responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        if len(result.body) > max_body_bytes:
            raise AssertionError("Fixture excede limite do teste.")
        return result


class NoopRateLimiter:
    def acquire(self) -> None:
        return None


class FakeClock:
    def __init__(self) -> None:
        self.seconds = 0.0
        self.sleeps: list[float] = []
        self.base = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)

    def monotonic(self) -> float:
        return self.seconds

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.seconds += seconds

    def now(self) -> datetime:
        return self.base + timedelta(seconds=self.seconds)


def body_for(total: int, items: list[dict[str, object]]) -> bytes:
    return json.dumps(
        {"total_gazettes": total, "gazettes": items},
        separators=(",", ":"),
    ).encode()


def response_for(
    total: int,
    items: list[dict[str, object]],
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> HttpResponse:
    return HttpResponse(
        status=status,
        headers=headers or {"Content-Type": "application/json; charset=utf-8"},
        body=body_for(total, items),
        final_url="https://api.queridodiario.ok.org.br/gazettes",
    )


class QueridoDiarioClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.items = fixture["response"]["gazettes"]

    def make_client(
        self,
        responses: list[HttpResponse | BaseException],
        *,
        max_attempts: int = 3,
        failure_threshold: int = 2,
    ) -> tuple[QueridoDiarioClient, FakeTransport, FakeClock]:
        transport = FakeTransport(responses)
        clock = FakeClock()
        breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout_seconds=60,
            monotonic=clock.monotonic,
        )
        client = QueridoDiarioClient(
            transport=transport,
            retry_policy=RetryPolicy(
                max_attempts=max_attempts,
                base_delay_seconds=1,
                max_delay_seconds=10,
            ),
            circuit_breaker=breaker,
            rate_limiter=NoopRateLimiter(),  # type: ignore[arg-type]
            sleep=clock.sleep,
            random_value=lambda: 0.5,
            now=clock.now,
        )
        return client, transport, clock

    def test_uses_current_temporal_parameters_and_ibge_id(self) -> None:
        client, transport, _ = self.make_client(
            [response_for(0, [])],
        )

        pages = list(
            client.iter_gazette_pages(
                published_since=date(2026, 7, 1),
                published_until=date(2026, 7, 30),
                page_size=25,
            )
        )

        query = parse_qs(urlparse(transport.calls[0]).query, keep_blank_values=True)
        self.assertEqual(query["territory_ids"], ["2903201"])
        self.assertEqual(query["published_since"], ["2026-07-01"])
        self.assertEqual(query["published_until"], ["2026-07-30"])
        self.assertNotIn("since", query)
        self.assertEqual(pages[0].collection_status, "empty")

    def test_paginates_and_preserves_each_raw_body(self) -> None:
        client, transport, _ = self.make_client(
            [
                response_for(3, self.items),
                response_for(3, [self.items[0]]),
            ]
        )

        pages = list(client.iter_gazette_pages(page_size=2))

        self.assertEqual(len(pages), 2)
        self.assertEqual(pages[0].cursor, {"offset": 0, "size": 2})
        self.assertEqual(pages[1].cursor, {"offset": 2, "size": 2})
        self.assertEqual(len(pages[0].body_sha256), 64)
        self.assertEqual(len(pages[0].idempotency_key), 64)
        self.assertEqual(pages[0].body_size_bytes, len(pages[0].raw_body))
        self.assertEqual(len(transport.calls), 2)

    def test_retries_5xx_with_backoff_then_succeeds(self) -> None:
        client, _, clock = self.make_client(
            [
                response_for(0, [], status=503),
                response_for(1, [self.items[0]]),
            ]
        )

        page = next(client.iter_gazette_pages())

        self.assertEqual(page.attempts, 2)
        self.assertEqual(clock.sleeps, [0.5])

    def test_respects_retry_after_for_429(self) -> None:
        client, _, clock = self.make_client(
            [
                response_for(0, [], status=429, headers={"Retry-After": "7"}),
                response_for(0, []),
            ]
        )

        next(client.iter_gazette_pages())

        self.assertEqual(clock.sleeps, [7.0])

    def test_persistent_failures_open_circuit_between_operations(self) -> None:
        failures = [response_for(0, [], status=503) for _ in range(6)]
        client, transport, _ = self.make_client(failures)

        with self.assertRaises(SourceUnavailableError):
            list(client.iter_gazette_pages())
        with self.assertRaises(SourceUnavailableError):
            list(client.iter_gazette_pages())
        calls_before_open_check = len(transport.calls)
        with self.assertRaises(CircuitOpenError):
            list(client.iter_gazette_pages())
        self.assertEqual(len(transport.calls), calls_before_open_check)

    def test_non_retryable_http_error_is_explicit(self) -> None:
        client, transport, _ = self.make_client(
            [response_for(0, [], status=404)],
        )

        with self.assertRaises(PermanentHttpError):
            list(client.iter_gazette_pages())

        self.assertEqual(len(transport.calls), 1)

    def test_missing_required_source_field_fails_contract(self) -> None:
        invalid = dict(self.items[0])
        invalid.pop("scraped_at")
        client, _, _ = self.make_client([response_for(1, [invalid])])

        with self.assertRaises(SourceContractError):
            list(client.iter_gazette_pages())

    def test_additive_source_field_is_preserved_not_discarded(self) -> None:
        extended = dict(self.items[0])
        extended["new_source_field"] = {"value": 1}
        client, _, _ = self.make_client([response_for(1, [extended])])

        page = next(client.iter_gazette_pages())

        self.assertEqual(
            page.parsed.gazettes[0].source_extensions["new_source_field"],
            {"value": 1},
        )

    def test_premature_empty_page_is_partial_collection_error(self) -> None:
        client, _, _ = self.make_client(
            [
                response_for(3, self.items),
                response_for(3, []),
            ]
        )

        with self.assertRaises(PartialCollectionError):
            list(client.iter_gazette_pages(page_size=2))

    def test_rejects_invalid_date_window_before_http(self) -> None:
        client, transport, _ = self.make_client([])

        with self.assertRaises(ValueError):
            list(
                client.iter_gazette_pages(
                    published_since=date(2026, 8, 1),
                    published_until=date(2026, 7, 1),
                )
            )
        self.assertEqual(transport.calls, [])

    def test_rejects_artifact_url_outside_documented_hosts(self) -> None:
        unsafe_item = {
            **self.items[0],
            "url": "https://127.0.0.1/internal.pdf",
        }
        client, _, _ = self.make_client([response_for(1, [unsafe_item])])

        with self.assertRaises(SourceContractError):
            list(client.iter_gazette_pages())

    def test_canonicalizes_migration_bucket_and_preserves_origin(self) -> None:
        migrated_item = {
            **self.items[0],
            "url": (
                "s3://okbr-qd-migration//2903201/2025-12-31/"
                "9f09140a1df56c925536a91070298ae96e814bd1.pdf"
            ),
            "txt_url": (
                "s3://okbr-qd-migration//2903201/2025-12-31/"
                "9f09140a1df56c925536a91070298ae96e814bd1.txt"
            ),
        }
        response = response_for(1, [migrated_item])
        client, _, _ = self.make_client([response])

        page = next(client.iter_gazette_pages())
        item = page.parsed.gazettes[0]

        self.assertEqual(page.raw_body, response.body)
        self.assertEqual(
            item.url,
            "https://data.queridodiario.ok.org.br/2903201/2025-12-31/"
            "9f09140a1df56c925536a91070298ae96e814bd1.pdf",
        )
        self.assertEqual(
            item.source_extensions["source_url_original"],
            migrated_item["url"],
        )
        self.assertEqual(
            item.source_extensions["source_txt_url_original"],
            migrated_item["txt_url"],
        )
        self.assertEqual(
            item.source_extensions["url_canonicalization"],
            "okbr-qd-migration-s3-v1",
        )

    def test_rejects_unrecognized_s3_bucket(self) -> None:
        unsafe_item = {
            **self.items[0],
            "url": "s3://outro-bucket/2903201/documento.pdf",
        }
        client, _, _ = self.make_client([response_for(1, [unsafe_item])])

        with self.assertRaises(SourceContractError):
            list(client.iter_gazette_pages())


if __name__ == "__main__":
    unittest.main()
