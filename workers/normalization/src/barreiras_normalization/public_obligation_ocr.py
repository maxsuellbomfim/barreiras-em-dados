"""Fallback OCR estrito para a seção de restos a pagar dos balancetes."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable

from barreiras_docproc.ocr import OcrEngine, OcrPageResult, ocr_page
from barreiras_docproc.pdf_text import PdfCanonicalText, derive_pdf_text

from .public_obligation_pdf import (
    PublicObligationPdfContractError,
    PublicObligationSectionAbsentError,
    PublicObligationSectionIncompleteError,
    PublicObligationStructuralError,
    is_transfer_section_boundary,
    parse_legacy_combined_restos_summary,
    parse_restos_a_pagar_summary,
)
from .public_obligation_publisher import (
    PublicObligationExtraction,
    PublicObligationExtractionProvenance,
)

# Os balancetes problemáticos conhecidos estão rotacionados para a direita.
# Começar por 270° também mantém o diagnóstico útil dentro do limite do log.
_ROTATIONS = (270, 90, 0)
_AMOUNTISH = re.compile(r"\d[\d.]*,\d{1,2}")


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(
        character for character in normalized if not unicodedata.combining(character)
    ).upper()


def _has_section_heading(text: str | None) -> bool:
    if not text:
        return False
    return any(
        " ".join(_fold(line).split()) == "RESTOS A PAGAR" for line in text.splitlines()
    )


def _has_section_totals_footer(text: str | None) -> bool:
    if not text:
        return False
    return any(
        " ".join(_fold(line).split()).startswith(
            "TOTAL EXTRA, RESTOS A PAGAR E TRANSFERENCIA FINANCEIRA"
        )
        for line in text.splitlines()
    )


def _has_section_boundary(text: str | None) -> bool:
    if not text:
        return False
    return any(is_transfer_section_boundary(line) for line in text.splitlines())


def _diagnostic_excerpt(text: str) -> str:
    """Expõe somente o fim da seção pública, sem bytes ou credenciais."""
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    folded = [_fold(line) for line in lines]
    starts = [index for index, line in enumerate(folded) if line == "RESTOS A PAGAR"]
    start = starts[-1] if starts else 0
    boundaries = [
        index
        for index in range(start + 1, len(lines))
        if is_transfer_section_boundary(folded[index])
    ]
    end = boundaries[0] if boundaries else len(lines)
    selected = [
        line
        for line in lines[start:end]
        if _AMOUNTISH.search(line) or _fold(line) == "TOTAL"
    ]
    if len(selected) > 1:
        return " | ".join(selected)[-1800:]
    section = " | ".join(lines[start:end])
    if len(section) <= 1800:
        return section
    return f"{section[:900]} | ... | {section[-900:]}"


class PublicObligationOcrExtractor:
    """Faz OCR apenas da seção-alvo e aceita somente um total que fecha."""

    def __init__(
        self,
        *,
        engine: OcrEngine,
        alternative_engines: tuple[OcrEngine, ...] = (),
        pdf_text_deriver: Callable[[bytes], PdfCanonicalText] = derive_pdf_text,
        layout_text_deriver: Callable[[bytes], PdfCanonicalText] | None = None,
        page_ocr: Callable[..., OcrPageResult] = ocr_page,
    ) -> None:
        self.engine = engine
        self.alternative_engines = alternative_engines
        self.pdf_text_deriver = pdf_text_deriver
        self.layout_text_deriver = layout_text_deriver
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
            page.page_number for page in pdf.pages if _has_section_heading(page.text)
        ]
        if len(section_pages) == 1:
            section_page = section_pages[0]
            footer_pages = [
                page.page_number
                for page in pdf.pages
                if _has_section_totals_footer(page.text)
                and page.page_number > section_page
            ]
            boundary_pages = [
                page.page_number
                for page in pdf.pages[section_page:]
                if _has_section_boundary(page.text)
            ]
            continuation_page = (
                boundary_pages[0]
                if boundary_pages
                else footer_pages[0]
                if footer_pages
                else section_page + 1
            )
            if (
                footer_pages
                and not boundary_pages
                and continuation_page == footer_pages[0]
            ):
                reconciled = []
                pages_by_number = {page.page_number: page for page in pdf.pages}
                section_text = pages_by_number[section_page].text or ""
                footer_text = pages_by_number[footer_pages[0]].text or ""
                for transfer_page in reversed(
                    [page for page in pdf.pages if page.page_number < section_page]
                ):
                    if not _has_section_boundary(transfer_page.text):
                        continue
                    try:
                        summary = parse_legacy_combined_restos_summary(
                            expense_extra_text=section_text,
                            transfer_text=transfer_page.text or "",
                            combined_footer_text=footer_text,
                            fiscal_year=fiscal_year,
                            reference_month=reference_month,
                        )
                    except PublicObligationPdfContractError:
                        continue
                    reconciled.append((summary, transfer_page.page_number))
                distinct = {summary for summary, _page in reconciled}
                if len(distinct) == 1:
                    summary, transfer_page_number = reconciled[0]
                    return PublicObligationExtraction(
                        summary=summary,
                        provenance=PublicObligationExtractionProvenance(
                            extraction_method="embedded_text",
                            extraction_parser_version=pdf.parser_version,
                            page_numbers=(
                                transfer_page_number,
                                section_page,
                                footer_pages[0],
                            ),
                        ),
                    )
                if len(distinct) > 1:
                    raise ValueError(
                        "Totais combinados divergentes entre secoes de transferencia."
                    )
                raise PublicObligationSectionIncompleteError(
                    "A seção RESTOS A PAGAR está incompleta no PDF oficial: "
                    "a fonte termina sem o total mensal e sem a fronteira da seção."
                )
            page_numbers = tuple(
                page.page_number
                for page in pdf.pages[section_page - 1 : continuation_page]
                if page.page_number in (section_page, continuation_page)
                or bool(page.text)
            )
        else:
            footer_pages = [
                page.page_number
                for page in pdf.pages
                if _has_section_totals_footer(page.text)
            ]
            if (
                not section_pages
                and not footer_pages
                and pdf.pages
                and all(page.text for page in pdf.pages)
            ):
                raise PublicObligationSectionAbsentError(
                    "A fonte oficial integral não contém a seção RESTOS A PAGAR."
                )
            if len(section_pages) != 0 or len(footer_pages) != 1:
                raise ValueError("OCR exige uma seção RESTOS A PAGAR inequívoca.")
            footer_page = footer_pages[0]
            if footer_page <= 1:
                raise ValueError("OCR exige uma seção RESTOS A PAGAR inequívoca.")
            page_numbers = (footer_page - 1, footer_page)

        if not page_numbers:
            raise ValueError("OCR exige uma seção RESTOS A PAGAR inequívoca.")

        if self.layout_text_deriver is not None:
            layout_pdf = self.layout_text_deriver(raw_body)
            layout_text = "\n".join(
                page.text or ""
                for page in layout_pdf.pages
                if page.page_number in page_numbers
            )
            try:
                summary = parse_restos_a_pagar_summary(
                    layout_text,
                    fiscal_year=fiscal_year,
                    reference_month=reference_month,
                )
            except PublicObligationStructuralError:
                pass
            else:
                return PublicObligationExtraction(
                    summary=summary,
                    provenance=PublicObligationExtractionProvenance(
                        extraction_method="embedded_layout",
                        extraction_parser_version=layout_pdf.parser_version,
                        page_numbers=page_numbers,
                    ),
                )

        successes: list[PublicObligationExtraction] = []
        errors: list[str] = []
        for engine in (self.engine, *self.alternative_engines):
            for rotation in _ROTATIONS:
                results = [
                    self.page_ocr(
                        engine,
                        raw_body,
                        page_number,
                        rotation_degrees=rotation,
                    )
                    for page_number in page_numbers
                ]
                recognized_text = "\n".join(result.text for result in results)
                try:
                    summary = parse_restos_a_pagar_summary(
                        recognized_text,
                        fiscal_year=fiscal_year,
                        reference_month=reference_month,
                    )
                except PublicObligationPdfContractError as error:
                    errors.append(
                        f"{rotation}: {error}; "
                        f"trecho={_diagnostic_excerpt(recognized_text)}"
                    )
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
            detail = errors[0][:2200]
            raise ValueError(f"OCR não produziu total validado: {detail}")
        distinct = {extraction.summary for extraction in successes}
        if len(distinct) != 1:
            raise ValueError("OCR produziu totais divergentes entre orientações.")
        return successes[0]
