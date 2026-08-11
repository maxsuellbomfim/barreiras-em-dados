"""Fallback OCR estrito para a seção de restos a pagar dos balancetes."""

from __future__ import annotations

import unicodedata
from collections.abc import Callable

from barreiras_docproc.ocr import OcrEngine, OcrPageResult, ocr_page
from barreiras_docproc.pdf_text import PdfCanonicalText, derive_pdf_text

from .public_obligation_pdf import (
    PublicObligationPdfContractError,
    parse_restos_a_pagar_summary,
)
from .public_obligation_publisher import (
    PublicObligationExtraction,
    PublicObligationExtractionProvenance,
)

_ROTATIONS = (0, 90, 270)


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    ).upper()


def _has_section_heading(text: str | None) -> bool:
    if not text:
        return False
    return any(
        " ".join(_fold(line).split()) == "RESTOS A PAGAR"
        for line in text.splitlines()
    )


class PublicObligationOcrExtractor:
    """Faz OCR apenas da seção-alvo e aceita somente um total que fecha."""

    def __init__(
        self,
        *,
        engine: OcrEngine,
        pdf_text_deriver: Callable[[bytes], PdfCanonicalText] = derive_pdf_text,
        page_ocr: Callable[..., OcrPageResult] = ocr_page,
    ) -> None:
        self.engine = engine
        self.pdf_text_deriver = pdf_text_deriver
        self.page_ocr = page_ocr

    def extract(
        self,
        raw_body: bytes,
        *,
        fiscal_year: int,
        reference_month: int,
    ) -> PublicObligationExtraction:
        pdf = self.pdf_text_deriver(raw_body)
        section_pages = [
            page.page_number
            for page in pdf.pages
            if _has_section_heading(page.text)
        ]
        if len(section_pages) != 1:
            raise ValueError(
                "OCR exige exatamente uma página com o título RESTOS A PAGAR."
            )

        section_page = section_pages[0]
        last_page = len(pdf.pages)
        page_numbers = tuple(
            number
            for number in (section_page, section_page + 1)
            if number <= last_page
        )
        successes: list[PublicObligationExtraction] = []
        errors: list[str] = []
        for rotation in _ROTATIONS:
            results = [
                self.page_ocr(
                    self.engine,
                    raw_body,
                    page_number,
                    rotation_degrees=rotation,
                )
                for page_number in page_numbers
            ]
            try:
                summary = parse_restos_a_pagar_summary(
                    "\n".join(result.text for result in results),
                    fiscal_year=fiscal_year,
                    reference_month=reference_month,
                )
            except PublicObligationPdfContractError as error:
                errors.append(f"{rotation}: {error}")
                continue
            parser_versions = {result.parser_version for result in results}
            if len(parser_versions) != 1:
                raise ValueError("Páginas OCR usam versões de parser divergentes.")
            successes.append(
                PublicObligationExtraction(
                    summary=summary,
                    provenance=PublicObligationExtractionProvenance(
                        extraction_method="ocr",
                        extraction_parser_version=parser_versions.pop(),
                        page_numbers=page_numbers,
                        rotation_degrees=rotation,
                    ),
                )
            )

        if not successes:
            detail = "; ".join(errors)[:600]
            raise ValueError(f"OCR não produziu total validado: {detail}")
        distinct = {extraction.summary for extraction in successes}
        if len(distinct) != 1:
            raise ValueError("OCR produziu totais divergentes entre orientações.")
        return successes[0]
