from __future__ import annotations

import unittest
from pathlib import Path

from barreiras_collectors.connectors.alba import (
    MIN_EXPECTED,
    AlbaError,
    fetch_deputies,
    parse_deputies,
    parse_profile,
)
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.resilience import RetryPolicy

FIXTURE = (
    Path(__file__).parents[2]
    / "fixtures"
    / "sources"
    / "alba"
    / "deputados-sample.html"
)


def listagem(quantidade: int) -> bytes:
    linhas = [
        f'<option value="/deputados/deputado-estadual/{900000 + n}">'
        f"<span>Parlamentar {n}</span></option>"
        for n in range(quantidade)
    ]
    return ("<select>" + "".join(linhas) + "</select>").encode("utf-8")


class OneShotTransport:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.body = body

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del timeout_seconds, max_body_bytes
        assert "BarreirasEmDados" in headers["User-Agent"]
        return HttpResponse(
            status=self.status,
            headers={},
            body=self.body,
            final_url=url,
        )


class ParseDeputiesTests(unittest.TestCase):
    def test_reads_official_identifier_and_name(self) -> None:
        deputies = parse_deputies(FIXTURE.read_text(encoding="utf-8"))

        self.assertEqual(len(deputies), 3)
        self.assertEqual(deputies[0]["id_alba"], "900002")
        self.assertEqual(deputies[0]["nome"], "Beltrana Modelo")
        self.assertTrue(
            deputies[0]["perfil_url"].endswith("/deputado-estadual/900002")
        )

    def test_repeated_entry_is_deduplicated_by_identifier(self) -> None:
        """O portal repete o mesmo parlamentar em outro menu."""
        deputies = parse_deputies(FIXTURE.read_text(encoding="utf-8"))
        identifiers = [item["id_alba"] for item in deputies]

        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_names_are_sorted_deterministically(self) -> None:
        deputies = parse_deputies(FIXTURE.read_text(encoding="utf-8"))

        self.assertEqual(
            [item["nome"] for item in deputies],
            ["Beltrana Modelo", "Fulano de Tal Exemplo", "Sicrano Terceiro"],
        )

    def test_profile_accepts_only_official_photo_host(self) -> None:
        html = (
            '<meta property="og:image" content="/fserver/fotos/Modelo.jpg">'
            '<div class="linha-cv"><strong>Formação Educacional</strong>'
            '<span>Direito pela Universidade Modelo.</span></div>'
        )
        payload = parse_profile(
            html,
            identifier="900002",
            profile_url="https://www.al.ba.gov.br/deputados/deputado-estadual/900002",
            display_name="Beltrana Modelo",
        )
        self.assertEqual(
            payload["foto_url"],
            "https://www.al.ba.gov.br/fserver/fotos/Modelo.jpg",
        )
        self.assertEqual(
            payload["formacao_educacional"],
            "Direito pela Universidade Modelo.",
        )

    def test_profile_discards_external_photo(self) -> None:
        html = '<meta property="og:image" content="https://example.com/foto.jpg">'
        payload = parse_profile(
            html,
            identifier="900002",
            profile_url="https://www.al.ba.gov.br/deputados/deputado-estadual/900002",
            display_name="Beltrana Modelo",
        )
        self.assertIsNone(payload["foto_url"])


class FetchDeputiesTests(unittest.TestCase):
    def test_full_house_is_persistable(self) -> None:
        page = fetch_deputies(
            transport=OneShotTransport(200, listagem(63)),
            retry_policy=RetryPolicy(max_attempts=2),
            sleep=lambda _s: None,
        )

        assert page is not None
        self.assertEqual(len(page.items), 63)
        self.assertEqual(page.source_code, "alba")

    def test_truncated_house_is_explicit_failure(self) -> None:
        """Publicar parte da Assembleia como se fosse o todo é pior."""
        with self.assertRaises(AlbaError):
            fetch_deputies(
                transport=OneShotTransport(200, listagem(MIN_EXPECTED - 1)),
                retry_policy=RetryPolicy(max_attempts=2),
                sleep=lambda _s: None,
            )

    def test_http_error_is_explicit_failure(self) -> None:
        with self.assertRaises(AlbaError):
            fetch_deputies(
                transport=OneShotTransport(404, b""),
                retry_policy=RetryPolicy(max_attempts=2),
                sleep=lambda _s: None,
            )


if __name__ == "__main__":
    unittest.main()
