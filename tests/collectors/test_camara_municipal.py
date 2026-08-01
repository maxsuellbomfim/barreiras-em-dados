from __future__ import annotations

import unittest
from pathlib import Path

from barreiras_collectors.connectors.camara_municipal import (
    CamaraMunicipalError,
    fetch_councillors,
    parse_councillors,
)
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.resilience import RetryPolicy

FIXTURE = (
    Path(__file__).parents[2]
    / "fixtures"
    / "sources"
    / "camara_municipal"
    / "vereadores-sample.html"
)


class OneShotTransport:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.body = body

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del timeout_seconds, max_body_bytes
        # O coletor se identifica: nada de disfarce contra portal público.
        assert "BarreirasEmDados" in headers["User-Agent"]
        return HttpResponse(
            status=self.status,
            headers={},
            body=self.body,
            final_url=url,
        )


class ParseCouncillorsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = FIXTURE.read_text(encoding="utf-8")

    def test_reads_both_markup_variants(self) -> None:
        """Metade das fichas usa <strong>, metade <b>."""
        councillors = parse_councillors(self.html)

        self.assertEqual(len(councillors), 3)
        self.assertEqual(councillors[0]["nome"], "Fulano de Tal Exemplo")
        self.assertEqual(
            councillors[1]["nome"],
            "Beltrana de Tal Modelo (Bel)",
        )
        self.assertEqual(councillors[2]["nome"], "Sicrano Terceiro de Teste")

    def test_extracts_party_mandates_and_photo(self) -> None:
        first, second, third = parse_councillors(self.html)

        self.assertEqual(first["partido"], "PXY")
        self.assertEqual(first["mandatos"], "2º Mandato")
        self.assertTrue(first["foto_url"].endswith("fulano-exemplo.jpg"))
        # Rótulo com espaço antes do fechamento e tag vazia depois.
        self.assertEqual(second["partido"], "PZW")
        # Campo ausente é None explícito, nunca string vazia.
        self.assertIsNone(third["bandeira"])
        self.assertIsNone(third["biografia"])

    def test_block_without_name_is_explicit_failure(self) -> None:
        """Layout novo não pode publicar a Câmara pela metade."""
        quebrado = self.html.replace("<b>NOME:</b>", "<b>PARLAMENTAR:</b>")

        with self.assertRaises(CamaraMunicipalError):
            parse_councillors(quebrado)


class FetchCouncillorsTests(unittest.TestCase):
    def test_page_becomes_persistable_with_items(self) -> None:
        page = fetch_councillors(
            transport=OneShotTransport(
                200,
                FIXTURE.read_bytes(),
            ),
            retry_policy=RetryPolicy(max_attempts=2),
            sleep=lambda _s: None,
        )

        assert page is not None
        self.assertEqual(len(page.items), 3)
        self.assertEqual(page.source_code, "camara-municipal-barreiras")
        self.assertEqual(page.media_type, "text/html")
        self.assertEqual(page.total_registros, 3)

    def test_empty_page_is_explicit_failure(self) -> None:
        with self.assertRaises(CamaraMunicipalError):
            fetch_councillors(
                transport=OneShotTransport(200, b"<html><body></body></html>"),
                retry_policy=RetryPolicy(max_attempts=2),
                sleep=lambda _s: None,
            )

    def test_http_error_is_explicit_failure(self) -> None:
        with self.assertRaises(CamaraMunicipalError):
            fetch_councillors(
                transport=OneShotTransport(404, b""),
                retry_policy=RetryPolicy(max_attempts=2),
                sleep=lambda _s: None,
            )


if __name__ == "__main__":
    unittest.main()
