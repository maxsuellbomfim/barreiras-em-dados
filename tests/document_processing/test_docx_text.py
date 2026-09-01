from __future__ import annotations

import hashlib
import io
import unittest
import zipfile

from barreiras_docproc.docx_text import (
    DOCX_PARSER_VERSION,
    DocxStructureError,
    derive_docx_text,
)

WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def docx_bytes(document_xml: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
              <Default Extension="xml" ContentType="application/xml"/>
            </Types>""",
        )
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


class DocxTextTests(unittest.TestCase):
    def test_extracts_visible_paragraphs_breaks_and_table_rows(self) -> None:
        body = docx_bytes(
            f"""<?xml version="1.0" encoding="UTF-8"?>
            <w:document xmlns:w="{WORD_NAMESPACE}">
              <w:body>
                <w:p><w:r><w:t>Lei nº 1.234</w:t></w:r></w:p>
                <w:p>
                  <w:r><w:t>Texto</w:t><w:tab/><w:t>com</w:t><w:br/><w:t>quebra</w:t></w:r>
                </w:p>
                <w:tbl>
                  <w:tr>
                    <w:tc><w:p><w:r><w:t>Órgão</w:t></w:r></w:p></w:tc>
                    <w:tc><w:p><w:r><w:t>Valor</w:t></w:r></w:p></w:tc>
                  </w:tr>
                  <w:tr>
                    <w:tc><w:p><w:r><w:t>Saúde</w:t></w:r></w:p></w:tc>
                    <w:tc><w:p><w:r><w:t>R$ 10,00</w:t></w:r></w:p></w:tc>
                  </w:tr>
                </w:tbl>
              </w:body>
            </w:document>"""
        )

        result = derive_docx_text(body)

        self.assertEqual(result.parser_version, DOCX_PARSER_VERSION)
        self.assertEqual(result.input_sha256, hashlib.sha256(body).hexdigest())
        self.assertEqual(
            [(block.kind, block.text) for block in result.blocks],
            [
                ("paragraph", "Lei nº 1.234"),
                ("paragraph", "Texto\tcom\nquebra"),
                ("table_row", "Órgão\tValor"),
                ("table_row", "Saúde\tR$ 10,00"),
            ],
        )
        expected_text = (
            "Lei nº 1.234\nTexto\tcom\nquebra\nÓrgão\tValor\nSaúde\tR$ 10,00"
        )
        self.assertEqual(result.text, expected_text)
        self.assertEqual(
            result.text_sha256,
            hashlib.sha256(expected_text.encode("utf-8")).hexdigest(),
        )

    def test_rejects_a_generic_zip_without_word_document(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("notes.txt", "não é um DOCX")

        with self.assertRaisesRegex(
            DocxStructureError,
            "estrutura obrigatória",
        ):
            derive_docx_text(buffer.getvalue())

    def test_rejects_malformed_wordprocessingml(self) -> None:
        body = docx_bytes("<w:document>")

        with self.assertRaisesRegex(DocxStructureError, "XML principal"):
            derive_docx_text(body)

    def test_rejects_document_without_visible_text(self) -> None:
        body = docx_bytes(
            f"""<w:document xmlns:w="{WORD_NAMESPACE}">
              <w:body><w:p><w:r/></w:p></w:body>
            </w:document>"""
        )

        with self.assertRaisesRegex(DocxStructureError, "texto visível"):
            derive_docx_text(body)

    def test_rejects_excessive_uncompressed_document_xml(self) -> None:
        body = docx_bytes(" " * (16 * 1024 * 1024 + 1))

        with self.assertRaisesRegex(DocxStructureError, "limite seguro"):
            derive_docx_text(body)


if __name__ == "__main__":
    unittest.main()
