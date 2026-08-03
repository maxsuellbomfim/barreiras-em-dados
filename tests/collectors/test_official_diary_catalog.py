from __future__ import annotations

import unittest
from hashlib import sha256

from barreiras_collectors.connectors.official_diary_catalog import (
    OfficialCatalogSnapshot,
    OfficialPublication,
    parse_catalog_html,
)
from barreiras_collectors.persistence.models import (
    RepositoryPersistResult,
    StoredObject,
)
from barreiras_collectors.persistence.service import (
    OfficialDiaryCatalogPersistenceService,
)


class OfficialDiaryCatalogTests(unittest.TestCase):
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
