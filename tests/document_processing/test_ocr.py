from __future__ import annotations

import hashlib
import shutil
import unittest

from barreiras_docproc.ocr import (
    OCR_PARSER_VERSION,
    OcrError,
    TesseractEngine,
    ocr_page,
    rasterize_page,
)

from .test_pdf_processing import build_pdf


class FakeEngine:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    def image_to_text(self, png_bytes: bytes) -> str:
        assert png_bytes.startswith(b"\x89PNG")
        self.calls += 1
        return self.text


class RasterizeTests(unittest.TestCase):
    def test_renders_page_to_png(self) -> None:
        body = build_pdf(["Conteúdo de teste"])

        png = rasterize_page(body, 1)

        self.assertTrue(png.startswith(b"\x89PNG"))

    def test_invalid_pdf_raises_explicit_error(self) -> None:
        with self.assertRaises(OcrError):
            rasterize_page(b"nao eh pdf", 1)


class OcrPageTests(unittest.TestCase):
    def test_normalizes_and_hashes_recognized_text(self) -> None:
        body = build_pdf([None])
        engine = FakeEngine("PORTARIA N 77\r\nNOMEAR FULANO \n")

        result = ocr_page(engine, body, 1)

        self.assertEqual(result.text, "PORTARIA N 77\nNOMEAR FULANO")
        self.assertEqual(
            result.sha256,
            hashlib.sha256(result.text.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(result.parser_version, OCR_PARSER_VERSION)
        self.assertEqual(engine.calls, 1)

    def test_blank_page_becomes_explicit_empty_text(self) -> None:
        result = ocr_page(FakeEngine("   \n  "), build_pdf([None]), 1)

        self.assertEqual(result.text, "")
        self.assertEqual(
            result.sha256,
            hashlib.sha256(b"").hexdigest(),
        )


@unittest.skipUnless(
    shutil.which("tesseract"),
    "tesseract não instalado neste ambiente",
)
class TesseractSmokeTests(unittest.TestCase):
    def test_engine_runs_on_rendered_page(self) -> None:
        engine = TesseractEngine()
        result = ocr_page(engine, build_pdf(["NOMEAR TESTE"]), 1)

        self.assertIsInstance(result.text, str)


if __name__ == "__main__":
    unittest.main()
