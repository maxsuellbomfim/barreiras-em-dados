from __future__ import annotations

import json
import unittest

from barreiras_collectors.commands.collect_pncp_contratacoes import (
    resolve_window,
)
from barreiras_collectors.connectors.pncp import (
    PncpError,
    fetch_contratacoes_page,
)
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.resilience import RetryPolicy


class OneShotTransport:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.body = body
        self.urls: list[str] = []

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds, max_body_bytes
        self.urls.append(url)
        return HttpResponse(
            status=self.status,
            headers={},
            body=self.body,
            final_url=url,
        )


def fetch(status: int, body: bytes):
    return fetch_contratacoes_page(
        since="20260101",
        until="20260131",
        modalidade=6,
        pagina=1,
        transport=OneShotTransport(status, body),
        retry_policy=RetryPolicy(max_attempts=2),
        sleep=lambda _s: None,
    )


class ContratacoesFetchTests(unittest.TestCase):
    def test_page_with_items_preserves_bytes_and_cursor(self) -> None:
        body = json.dumps(
            {
                "totalRegistros": 23,
                "totalPaginas": 3,
                "data": [
                    {
                        "numeroControlePNCP": "13654405000195-1-000001/2026",
                        "objetoCompra": "Fornecimento de alimentos",
                    }
                ],
            }
        ).encode()

        page = fetch(200, body)

        assert page is not None
        self.assertEqual(page.total_paginas, 3)
        self.assertEqual(len(page.items), 1)
        self.assertEqual(page.cursor["modalidade"], 6)
        self.assertEqual(page.raw_body, body)

    def test_http_200_with_error_root_is_failure(self) -> None:
        body = json.dumps({"error": "parametro invalido"}).encode()

        with self.assertRaises(PncpError):
            fetch(200, body)

    def test_204_and_empty_data_mean_no_content(self) -> None:
        self.assertIsNone(fetch(204, b""))
        self.assertIsNone(
            fetch(
                200,
                json.dumps(
                    {"totalRegistros": 0, "totalPaginas": 0, "data": []}
                ).encode(),
            )
        )

    def test_non_json_is_explicit_failure(self) -> None:
        with self.assertRaises(PncpError):
            fetch(200, b"<html>bloqueio</html>")


class WindowTests(unittest.TestCase):
    def test_explicit_window_is_formatted_for_the_api(self) -> None:
        self.assertEqual(
            resolve_window("2026-01-01", "2026-01-31"),
            ("20260101", "20260131"),
        )

    def test_partial_or_oversized_window_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            resolve_window("2026-01-01", "")
        with self.assertRaises(ValueError):
            resolve_window("2026-01-01", "2026-03-15")


if __name__ == "__main__":
    unittest.main()
