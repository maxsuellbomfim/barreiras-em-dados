from __future__ import annotations

import unittest

from barreiras_collectors.connectors.official_diary_catalog import (
    parse_catalog_html,
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


if __name__ == "__main__":
    unittest.main()

