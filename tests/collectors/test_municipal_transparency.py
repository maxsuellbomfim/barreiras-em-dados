from __future__ import annotations

import json
import unittest
from pathlib import Path

from barreiras_collectors.connectors.municipal_transparency import (
    MunicipalTransparencyContractError,
    MunicipalTransparencyError,
    iter_resource_pages,
)
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.resilience import RetryPolicy

FIXTURE = (
    Path(__file__).parents[2]
    / "fixtures"
    / "sources"
    / "prefeitura-transparencia"
    / "pdc-resumo-execucao-da-receita-page.json"
)


class SequenceTransport:
    def __init__(self, bodies: list[bytes], statuses: list[int] | None = None) -> None:
        self.bodies = list(bodies)
        self.statuses = statuses or [200] * len(self.bodies)
        self.calls = 0

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del timeout_seconds, max_body_bytes
        self.calls += 1
        assert "BarreirasEmDados" in headers["User-Agent"]
        index = min(self.calls - 1, len(self.bodies) - 1)
        return HttpResponse(
            status=self.statuses[index],
            headers={"Content-Type": "application/json; charset=utf-8"},
            body=self.bodies[index],
            final_url=url,
        )


class MunicipalTransparencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_paginates_until_short_page_and_preserves_hash(self) -> None:
        first = dict(self.fixture)
        first["data"] = first["data"][:2]
        first["count"] = 2
        second = dict(self.fixture)
        second["data"] = second["data"][:1]
        second["count"] = 1
        transport = SequenceTransport(
            [json.dumps(first).encode(), json.dumps(second).encode()]
        )

        pages = list(
            iter_resource_pages(
                base_url="https://portaldatransparencia.barreiras.ba.gov.br/api",
                source_code="prefeitura-barreiras-transparencia",
                resource="pdc-resumo-execucao-da-receita",
                limit=2,
                transport=transport,
                requests_per_minute=600,
                sleep=lambda _seconds: None,
            )
        )

        self.assertEqual(len(pages), 2)
        self.assertEqual(pages[0].cursor["offset"], 0)
        self.assertEqual(pages[1].cursor["offset"], 2)
        self.assertEqual(pages[1].items[0]["id"], "sanitized-revenue-1")
        self.assertEqual(transport.calls, 2)
        self.assertEqual(len(pages[0].body_sha256), 64)

    def test_http_200_error_root_is_not_empty_data(self) -> None:
        body = json.dumps({"error": "resource inexistente"}).encode()
        with self.assertRaises(MunicipalTransparencyContractError):
            list(
                iter_resource_pages(
                    base_url="https://portaldatransparencia.barreiras.ba.gov.br/api",
                    source_code="prefeitura-barreiras-transparencia",
                    resource="pdc-resumo-execucao-da-receita",
                    transport=SequenceTransport([body]),
                    requests_per_minute=600,
                    sleep=lambda _seconds: None,
                )
            )

    def test_count_mismatch_is_explicit_failure(self) -> None:
        body = dict(self.fixture)
        body["count"] = 1
        with self.assertRaises(MunicipalTransparencyContractError):
            list(
                iter_resource_pages(
                    base_url="https://portaldatransparencia.barreiras.ba.gov.br/api",
                    source_code="prefeitura-barreiras-transparencia",
                    resource="pdc-resumo-execucao-da-receita",
                    transport=SequenceTransport([json.dumps(body).encode()]),
                    requests_per_minute=600,
                    sleep=lambda _seconds: None,
                )
            )

    def test_retries_retryable_http_status(self) -> None:
        transport = SequenceTransport(
            [b"temporarily unavailable", json.dumps(self.fixture).encode()],
            statuses=[503, 200],
        )
        pages = list(
            iter_resource_pages(
                base_url="https://portaldatransparencia.barreiras.ba.gov.br/api",
                source_code="prefeitura-barreiras-transparencia",
                resource="pdc-resumo-execucao-da-receita",
                transport=transport,
                retry_policy=RetryPolicy(max_attempts=2),
                requests_per_minute=600,
                sleep=lambda _seconds: None,
                random_value=lambda: 0,
            )
        )
        self.assertEqual(len(pages), 1)
        self.assertEqual(transport.calls, 2)

    def test_invalid_source_or_resource_fails_before_network(self) -> None:
        with self.assertRaises(ValueError):
            list(
                iter_resource_pages(
                    base_url="https://portaldatransparencia.barreiras.ba.gov.br/api",
                    source_code="unknown",
                    resource="pdc-resumo-execucao-da-receita",
                    transport=SequenceTransport([]),
                )
            )

    def test_source_and_host_must_match(self) -> None:
        with self.assertRaises(ValueError):
            list(
                iter_resource_pages(
                    base_url="https://portaldatransparencia.cmbarreiras.ba.gov.br/api",
                    source_code="prefeitura-barreiras-transparencia",
                    resource="pdc-resumo-execucao-da-receita",
                    transport=SequenceTransport([]),
                )
            )
        with self.assertRaises(ValueError):
            list(
                iter_resource_pages(
                    base_url="https://portaldatransparencia.barreiras.ba.gov.br/api",
                    source_code="prefeitura-barreiras-transparencia",
                    resource="../secrets",
                    transport=SequenceTransport([]),
                )
            )

    def test_non_retryable_http_status_is_explicit(self) -> None:
        with self.assertRaises(MunicipalTransparencyError):
            list(
                iter_resource_pages(
                    base_url="https://portaldatransparencia.barreiras.ba.gov.br/api",
                    source_code="prefeitura-barreiras-transparencia",
                    resource="pdc-resumo-execucao-da-receita",
                    transport=SequenceTransport([b"forbidden"], statuses=[403]),
                    requests_per_minute=600,
                    sleep=lambda _seconds: None,
                )
            )


if __name__ == "__main__":
    unittest.main()
