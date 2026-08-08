from __future__ import annotations

import unittest

from barreiras_docproc.gazette_documents import join_literal_blocks
from barreiras_docproc.pdf_layout import (
    PDF_LAYOUT_VERSION,
    derive_pdf_layout,
)

from tests.document_processing.test_pdf_processing import build_pdf


class PdfLayoutTests(unittest.TestCase):
    def test_extracts_complete_literal_text_in_page_order(self) -> None:
        body = build_pdf(
            [
                "PORTARIA Nº 261 acompanhamento e fiscalização completos.",
                "Art. 2º Esta Portaria entra em vigor na publicação.",
            ]
        )

        pages = derive_pdf_layout(body)

        self.assertEqual([page.page_number for page in pages], [1, 2])
        self.assertEqual(
            [page.parser_version for page in pages],
            [PDF_LAYOUT_VERSION] * 2,
        )
        self.assertTrue(all(page.blocks for page in pages))
        text = join_literal_blocks(
            tuple(block for page in pages for block in page.blocks)
        )
        self.assertIn("acompanhamento e fiscalização completos", text)
        self.assertIn("Esta Portaria entra em vigor", text)

    def test_marks_scanned_page_without_inventing_blocks(self) -> None:
        body = build_pdf(["Página textual", None])

        pages = derive_pdf_layout(body)

        self.assertEqual(pages[0].extraction_method, "embedded_layout")
        self.assertEqual(pages[1].extraction_method, "pending_ocr")
        self.assertEqual(pages[1].blocks, ())

    def test_blocks_expose_real_coordinates_when_pdf_provides_them(self) -> None:
        pages = derive_pdf_layout(build_pdf(["TEXTO OFICIAL INTEGRAL"]))

        block = pages[0].blocks[0]

        self.assertIsNotNone(block.bbox)
        assert block.bbox is not None
        self.assertGreaterEqual(block.bbox[0], 0)
        self.assertGreaterEqual(block.bbox[1], 0)


if __name__ == "__main__":
    unittest.main()
