"""Extrai blocos literais e ordenados de PDFs do Diário Oficial."""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from .canonical import CanonicalTextError
from .gazette_documents import BoundingBox, DocumentBlock

PDF_LAYOUT_VERSION = "gazette-pdf-layout/1.0.0"
LayoutMethod = Literal["embedded_layout", "embedded_text", "pending_ocr"]


@dataclass(frozen=True)
class PdfLayoutPage:
    page_number: int
    blocks: tuple[DocumentBlock, ...]
    extraction_method: LayoutMethod
    parser_version: str = PDF_LAYOUT_VERSION


def _fragment_bbox(
    text: str,
    text_matrix: list[float],
    font_size: float,
) -> BoundingBox | None:
    if len(text_matrix) < 6:
        return None
    x = float(text_matrix[4])
    y = float(text_matrix[5])
    size = max(float(font_size), 0.0)
    estimated_width = max(len(text.rstrip("\r\n")), 1) * size * 0.5
    return (x, y, x + estimated_width, y + size)


def _fragment_visitor(
    fragments: list[tuple[str, BoundingBox | None]],
) -> Callable[[str, list[float], list[float], object, float], None]:
    def visit_text(
        text: str,
        _current_matrix: list[float],
        text_matrix: list[float],
        _font_dictionary: object,
        font_size: float,
    ) -> None:
        if text.strip():
            fragments.append((text, _fragment_bbox(text, text_matrix, font_size)))

    return visit_text


def derive_pdf_layout(raw_body: bytes) -> tuple[PdfLayoutPage, ...]:
    """Extrai fragmentos com posição; recua para texto integral da página."""
    if not raw_body.startswith(b"%PDF-"):
        raise CanonicalTextError("O artefato não é um PDF válido.")
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise RuntimeError(
            "Instale a dependência opcional 'pdf' para processar PDFs."
        ) from error

    try:
        reader = PdfReader(io.BytesIO(raw_body))
        result: list[PdfLayoutPage] = []
        for page_number, page in enumerate(reader.pages, start=1):
            fragments: list[tuple[str, BoundingBox | None]] = []
            extracted = (
                page.extract_text(visitor_text=_fragment_visitor(fragments)) or ""
            )
            if fragments:
                blocks = tuple(
                    DocumentBlock.create(
                        page_number=page_number,
                        block_order=order,
                        text=text,
                        bbox=bbox,
                    )
                    for order, (text, bbox) in enumerate(fragments)
                )
                method: LayoutMethod = (
                    "embedded_layout"
                    if all(block.bbox is not None for block in blocks)
                    else "embedded_text"
                )
            elif extracted.strip():
                blocks = (
                    DocumentBlock.create(
                        page_number=page_number,
                        block_order=0,
                        text=extracted,
                    ),
                )
                method = "embedded_text"
            else:
                blocks = ()
                method = "pending_ocr"
            result.append(
                PdfLayoutPage(
                    page_number=page_number,
                    blocks=blocks,
                    extraction_method=method,
                )
            )
        return tuple(result)
    except CanonicalTextError:
        raise
    except Exception as error:
        raise CanonicalTextError(
            "O PDF não pôde ser lido para extração de layout."
        ) from error
