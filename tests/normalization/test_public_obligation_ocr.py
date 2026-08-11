from __future__ import annotations

import unittest
from dataclasses import dataclass
from decimal import Decimal

from barreiras_normalization.public_obligation_ocr import (
    PublicObligationOcrExtractor,
)
from barreiras_normalization.public_obligation_pdf import (
    PublicObligationSectionAbsentError,
)


@dataclass(frozen=True)
class FakePage:
    page_number: int
    text: str | None


@dataclass(frozen=True)
class FakePdf:
    pages: tuple[FakePage, ...]
    parser_version: str = "gazette-pdf-embedded-text/1.1.0"


@dataclass(frozen=True)
class FakeOcrResult:
    page_number: int
    text: str
    parser_version: str = "gazette-ocr-text/1.0.0"


class FakeEngine:
    def __init__(self, name: str = "primary") -> None:
        self.name = name


class PublicObligationOcrExtractorTests(unittest.TestCase):
    def test_ocr_only_section_page_and_continuation_until_transfer_boundary(self):
        pages = tuple(
            FakePage(number, "RESTOS A PAGAR" if number == 74 else "outra pagina")
            for number in range(1, 76)
        )
        calls: list[tuple[int, int]] = []

        def page_ocr(_engine, _body, page_number, *, rotation_degrees=0):
            calls.append((page_number, rotation_degrees))
            if rotation_degrees == 270 and page_number == 74:
                text = "RESTOS A PAGAR\nlinhas de contas\nTotal"
            elif rotation_degrees == 270 and page_number == 75:
                text = (
                    "22.135.713,16 13.800.485,81 35.936.198,97\n"
                    "TRANSFERÊNCIA FINANCEIRA\n"
                    "48.892.963,86 45.983.041,74 94.876.005,60"
                )
            else:
                text = "texto ilegivel"
            return FakeOcrResult(page_number=page_number, text=text)

        extractor = PublicObligationOcrExtractor(
            engine=FakeEngine(),
            pdf_text_deriver=lambda _body: FakePdf(pages),
            page_ocr=page_ocr,
        )

        extraction = extractor.extract(
            b"%PDF fixture",
            fiscal_year=2026,
            reference_month=2,
        )

        self.assertEqual(
            extraction.summary.payments_prior_amount,
            Decimal("22135713.16"),
        )
        self.assertEqual(
            extraction.summary.payments_period_amount,
            Decimal("13800485.81"),
        )
        self.assertEqual(
            extraction.summary.payments_to_date_amount,
            Decimal("35936198.97"),
        )
        self.assertEqual(extraction.provenance.extraction_method, "ocr")
        self.assertEqual(extraction.provenance.page_numbers, (74, 75))
        self.assertEqual(extraction.provenance.rotation_degrees, 270)
        self.assertEqual(
            extraction.provenance.extraction_parser_version,
            "gazette-ocr-text/1.0.0",
        )
        self.assertEqual(
            calls,
            [(74, 270), (75, 270), (74, 90), (75, 90), (74, 0), (75, 0)],
        )

    def test_requires_exactly_one_page_with_restos_heading(self):
        extractor = PublicObligationOcrExtractor(
            engine=FakeEngine(),
            pdf_text_deriver=lambda _body: FakePdf(
                (FakePage(1, "capa"), FakePage(2, "sem secao"))
            ),
            page_ocr=lambda *_args, **_kwargs: self.fail("OCR nao deveria rodar"),
        )

        with self.assertRaisesRegex(ValueError, "RESTOS A PAGAR"):
            extractor.extract(
                b"%PDF fixture",
                fiscal_year=2026,
                reference_month=1,
            )

    def test_classifies_section_as_absent_when_every_page_has_embedded_text(self):
        extractor = PublicObligationOcrExtractor(
            engine=FakeEngine(),
            pdf_text_deriver=lambda _body: FakePdf(
                (
                    FakePage(1, "demonstrativo orcamentario"),
                    FakePage(2, "assinaturas e encerramento"),
                )
            ),
            page_ocr=lambda *_args, **_kwargs: self.fail("OCR nao deveria rodar"),
        )

        with self.assertRaisesRegex(
            PublicObligationSectionAbsentError,
            "fonte oficial",
        ):
            extractor.extract(
                b"%PDF fixture",
                fiscal_year=2021,
                reference_month=3,
            )

    def test_does_not_classify_absence_when_a_page_has_no_embedded_text(self):
        extractor = PublicObligationOcrExtractor(
            engine=FakeEngine(),
            pdf_text_deriver=lambda _body: FakePdf(
                (FakePage(1, "capa"), FakePage(2, None))
            ),
            page_ocr=lambda *_args, **_kwargs: self.fail("OCR nao deveria rodar"),
        )

        with self.assertRaisesRegex(ValueError, "RESTOS A PAGAR"):
            extractor.extract(
                b"%PDF fixture",
                fiscal_year=2021,
                reference_month=3,
            )

    def test_uses_unique_totals_footer_to_locate_legacy_restos_pages(self):
        pages = tuple(
            FakePage(
                number,
                (
                    "Total Extra, Restos a Pagar e Transferência Financeira"
                    if number == 73
                    else "outra pagina"
                ),
            )
            for number in range(1, 74)
        )
        calls: list[tuple[int, int]] = []

        def page_ocr(_engine, _body, page_number, *, rotation_degrees=0):
            calls.append((page_number, rotation_degrees))
            if rotation_degrees == 270 and page_number == 72:
                text = "RESTOS A PAGAR\nlinhas de contas\nTotal"
            elif rotation_degrees == 270 and page_number == 73:
                text = (
                    "19.859.849,88 0,00 19.859.849,88\n"
                    "TRANSFERÊNCIA FINANCEIRA"
                )
            else:
                text = "texto ilegivel"
            return FakeOcrResult(page_number=page_number, text=text)

        extractor = PublicObligationOcrExtractor(
            engine=FakeEngine(),
            pdf_text_deriver=lambda _body: FakePdf(pages),
            page_ocr=page_ocr,
        )

        extraction = extractor.extract(
            b"%PDF fixture",
            fiscal_year=2025,
            reference_month=10,
        )

        self.assertEqual(
            extraction.summary.payments_to_date_amount,
            Decimal("19859849.88"),
        )
        self.assertEqual(extraction.provenance.page_numbers, (72, 73))
        self.assertEqual(
            calls,
            [(72, 270), (73, 270), (72, 90), (73, 90), (72, 0), (73, 0)],
        )

    def test_rejects_ambiguous_legacy_totals_footers_without_running_ocr(self):
        extractor = PublicObligationOcrExtractor(
            engine=FakeEngine(),
            pdf_text_deriver=lambda _body: FakePdf(
                (
                    FakePage(
                        4,
                        "Total Extra, Restos a Pagar e Transferência Financeira",
                    ),
                    FakePage(
                        8,
                        "Total Extra, Restos a Pagar e Transferência Financeira",
                    ),
                )
            ),
            page_ocr=lambda *_args, **_kwargs: self.fail("OCR nao deveria rodar"),
        )

        with self.assertRaisesRegex(ValueError, "inequívoca"):
            extractor.extract(
                b"%PDF fixture",
                fiscal_year=2025,
                reference_month=10,
            )

    def test_uses_validated_layout_text_before_ocr(self):
        canonical = FakePdf(
            (
                FakePage(1, "capa"),
                FakePage(2, "RESTOS A PAGAR\ntexto em ordem inadequada"),
                FakePage(3, "TRANSFERÊNCIA FINANCEIRA"),
            )
        )
        layout = FakePdf(
            (
                FakePage(1, "capa"),
                FakePage(2, "RESTOS A PAGAR\ncontas"),
                FakePage(
                    3,
                    "0,00 18.542.319,37 18.542.319,37\n"
                    "TRANSFERÊNCIA FINANCEIRA",
                ),
            ),
            parser_version="public-obligation-pdf-layout-text/1.0.0",
        )
        extractor = PublicObligationOcrExtractor(
            engine=FakeEngine(),
            pdf_text_deriver=lambda _body: canonical,
            layout_text_deriver=lambda _body: layout,
            page_ocr=lambda *_args, **_kwargs: self.fail("OCR nao deveria rodar"),
        )

        extraction = extractor.extract(
            b"%PDF fixture",
            fiscal_year=2021,
            reference_month=1,
        )

        self.assertEqual(extraction.provenance.extraction_method, "embedded_layout")
        self.assertEqual(extraction.provenance.page_numbers, (2, 3))
        self.assertEqual(
            extraction.provenance.extraction_parser_version,
            "public-obligation-pdf-layout-text/1.0.0",
        )
        self.assertEqual(
            extraction.summary.payments_to_date_amount,
            Decimal("18542319.37"),
        )

    def test_retries_ocr_with_alternative_segmentation_engine(self):
        primary = FakeEngine("primary")
        alternative = FakeEngine("alternative")
        calls: list[tuple[str, int, int]] = []

        def page_ocr(engine, _body, page_number, *, rotation_degrees=0):
            calls.append((engine.name, page_number, rotation_degrees))
            if engine is alternative and rotation_degrees == 0:
                if page_number == 105:
                    text = "RESTOS A PAGAR\ncontas"
                else:
                    text = (
                        "22.354.323,42 1.445.172,84 23.799.496,26\n"
                        "TRANSFERÊNCIA FINANCEIRA"
                    )
                return FakeOcrResult(
                    page_number=page_number,
                    text=text,
                    parser_version="gazette-ocr-text/1.0.0+tesseract-psm3",
                )
            return FakeOcrResult(page_number=page_number, text="texto ilegivel")

        extractor = PublicObligationOcrExtractor(
            engine=primary,
            alternative_engines=(alternative,),
            pdf_text_deriver=lambda _body: FakePdf(
                tuple(
                    FakePage(
                        number,
                        "RESTOS A PAGAR" if number == 105 else "outra pagina",
                    )
                    for number in range(1, 108)
                )
            ),
            layout_text_deriver=lambda _body: FakePdf(
                tuple(FakePage(number, None) for number in range(1, 108)),
                parser_version="public-obligation-pdf-layout-text/1.0.0",
            ),
            page_ocr=page_ocr,
        )

        extraction = extractor.extract(
            b"%PDF fixture",
            fiscal_year=2021,
            reference_month=5,
        )

        self.assertEqual(extraction.provenance.extraction_method, "ocr")
        self.assertEqual(extraction.provenance.rotation_degrees, 0)
        self.assertEqual(
            extraction.provenance.extraction_parser_version,
            "gazette-ocr-text/1.0.0+tesseract-psm3",
        )
        self.assertIn(("primary", 105, 270), calls)
        self.assertIn(("alternative", 105, 0), calls)


if __name__ == "__main__":
    unittest.main()
