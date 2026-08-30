from __future__ import annotations

import unittest
from datetime import date
from hashlib import sha256
from urllib.parse import parse_qs, urlparse

from barreiras_collectors.connectors.official_diary_catalog import (
    OfficialCatalogSnapshot,
    OfficialDiaryCatalogClient,
    OfficialPublication,
    build_catalog_url,
    parse_catalog_html,
)
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.persistence.models import (
    RepositoryPersistResult,
    StoredObject,
)
from barreiras_collectors.persistence.service import (
    OfficialDiaryCatalogPersistenceService,
    official_catalog_record_idempotency_key,
)


class OfficialDiaryCatalogTests(unittest.TestCase):
    def test_catalog_record_idempotency_is_scoped_to_snapshot(self) -> None:
        first = official_catalog_record_idempotency_key(
            catalog_body_sha256="a" * 64,
            source_record_key="barreiras-diario:publication:4703:2026-07-31",
            payload_sha256="b" * 64,
        )
        replay = official_catalog_record_idempotency_key(
            catalog_body_sha256="a" * 64,
            source_record_key="barreiras-diario:publication:4703:2026-07-31",
            payload_sha256="b" * 64,
        )
        next_snapshot = official_catalog_record_idempotency_key(
            catalog_body_sha256="c" * 64,
            source_record_key="barreiras-diario:publication:4703:2026-07-31",
            payload_sha256="b" * 64,
        )
        self.assertEqual(first, replay)
        self.assertNotEqual(first, next_snapshot)

    def test_parses_official_edition_fields(self) -> None:
        body = """
        <table><tbody><tr>
          <td>4703</td>
          <td>Diário Oficial - Edição 4703</td>
          <td>DECRETO Nº 123: Constitui Comissão Especial para a Movimentação
              e Otimização das Execuções Fiscais do Município.</td>
          <td>31/07/2026</td>
          <td><a href="/publicacao?referencia=16977">Ver publicações</a></td>
        </tr></tbody></table>
        """.encode()

        publications = parse_catalog_html(body)

        self.assertEqual(len(publications), 1)
        publication = publications[0]
        self.assertEqual(publication.edition_number, 4703)
        self.assertEqual(publication.published_date, "2026-07-31")
        self.assertEqual(publication.reference, "16977")
        self.assertIn("DECRETO Nº 123", publication.summary)
        self.assertEqual(
            publication.publication_url,
            "https://pmbarreiras.diariomtransparente.com.br/publicacao?referencia=16977",
        )

    def test_rejects_catalog_without_publications(self) -> None:
        with self.assertRaises(ValueError):
            parse_catalog_html(b"<html><body>sem edicoes</body></html>")

    def test_accepts_explicit_empty_filtered_catalog(self) -> None:
        body = (
            b"<html><body><span class='nulled'>Nenhum registro cadastrado "
            b"ou compat\xc3\xadvel com a sua filtragem!</span></body></html>"
        )

        self.assertEqual(parse_catalog_html(body, allow_explicit_empty=True), ())

    def test_filtered_catalog_url_keeps_dates_and_page(self) -> None:
        url = build_catalog_url(
            published_since=date(2021, 1, 1),
            published_until=date(2021, 1, 7),
            page=3,
        )

        query = parse_qs(urlparse(url).query)
        self.assertEqual(query["data_inicial"], ["01/01/2021"])
        self.assertEqual(query["data_final"], ["07/01/2021"])
        self.assertEqual(query["filtered"], ["1"])
        self.assertEqual(query["pagina"], ["3"])
    def test_filtered_window_walks_all_declared_pages(self) -> None:
        first_page = """
        <table><tr><td>100</td><td>Diário Oficial - Edição 100</td>
        <td>Resumo oficial suficientemente longo da primeira edição.</td>
        <td>01/01/2021</td><td><a href="/publicacao?referencia=1">Ver</a></td>
        </tr></table><a href="?pagina=2&amp;filtered=1">2</a>
        """.encode()
        second_page = """
        <table><tr><td>101</td><td>Diário Oficial - Edição 101</td>
        <td>Resumo oficial suficientemente longo da segunda edição.</td>
        <td>02/01/2021</td><td><a href="/publicacao?referencia=2">Ver</a></td>
        </tr></table>
        """.encode()

        class Transport:
            def __init__(self) -> None:
                self.urls: list[str] = []
                self.bodies = [first_page, second_page]

            def get(self, url, **_kwargs):
                self.urls.append(url)
                return HttpResponse(200, {}, self.bodies.pop(0), url)

        class RateLimiter:
            @staticmethod
            def acquire() -> None:
                return None

        transport = Transport()
        pages = tuple(
            OfficialDiaryCatalogClient(
                transport=transport,  # type: ignore[arg-type]
                rate_limiter=RateLimiter(),  # type: ignore[arg-type]
            ).iter_window_pages(
                published_since=date(2021, 1, 1),
                published_until=date(2021, 1, 7),
            )
        )

        self.assertEqual([len(page.publications) for page in pages], [1, 1])
        self.assertEqual(len(transport.urls), 2)
        self.assertIn("pagina=2", transport.urls[1])
    def test_storage_uses_existing_gazette_corridor(self) -> None:
        body = b"<html>catalogo</html>"
        digest = sha256(body).hexdigest()
        publication = OfficialPublication(
            edition_number=4703,
            title="Diário Oficial - Edição 4703",
            summary="Resumo oficial",
            published_date="2026-07-31",
            reference="16977",
            publication_url=(
                "https://pmbarreiras.diariomtransparente.com.br/"
                "publicacao?referencia=16977"
            ),
            summary_url=(
                "https://pmbarreiras.diariomtransparente.com.br/"
                "_core/_ajax/resumo.php?id=16977"
            ),
        )
        snapshot = OfficialCatalogSnapshot(
            request_url="https://pmbarreiras.diariomtransparente.com.br/publicacoes",
            final_url="https://pmbarreiras.diariomtransparente.com.br/publicacoes",
            requested_at="2026-08-03T00:00:00+00:00",
            received_at="2026-08-03T00:00:01+00:00",
            attempts=1,
            http_status=200,
            body_sha256=digest,
            body_size_bytes=len(body),
            media_type="text/html",
            response_headers={},
            raw_body=body,
            publications=(publication,),
        )

        class Store:
            def __init__(self) -> None:
                self.keys: list[str] = []

            def put_if_absent(self, *, object_key, **kwargs):
                del kwargs
                self.keys.append(object_key)
                return StoredObject(object_key, digest, len(body), True)

            def read(self, object_key):
                del object_key
                return body

        class Repository:
            def persist(self, batch):
                del batch
                return RepositoryPersistResult("run", "artifact", 1, 0)

        store = Store()
        OfficialDiaryCatalogPersistenceService(
            object_store=store,
            repository=Repository(),
        ).persist(snapshot)

        self.assertTrue(store.keys[0].startswith("barreiras-diario/gazettes/"))


if __name__ == "__main__":
    unittest.main()
