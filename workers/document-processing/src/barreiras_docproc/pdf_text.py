"""Texto embutido de PDFs, página a página, sem OCR.

Página sem texto embutido é um estado explícito (`text` nulo, aguardando
OCR), nunca uma página silenciosamente vazia. PDF ilegível é falha
explícita do artefato, registrada como job `failed` — não derruba o lote.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

from .canonical import CanonicalTextError, sanitize_text

# 1.1.0 rederiva páginas que foram persistidas por versões anteriores do
# parser. A versão faz parte da chave de idempotência da página: as páginas
# 1.0.0 continuam preservadas e nunca são sobrescritas.
PDF_PARSER_VERSION = "gazette-pdf-embedded-text/1.1.0"
PDF_LAYOUT_TEXT_VERSION = "public-obligation-pdf-layout-text/1.0.0"


@dataclass(frozen=True)
class PdfPageText:
    page_number: int
    text: str | None
    sha256: str | None


@dataclass(frozen=True)
class PdfCanonicalText:
    pages: tuple[PdfPageText, ...]
    text: str
    sha256: str
    parser_version: str
    pages_with_text: int


def derive_pdf_text(raw_body: bytes) -> PdfCanonicalText:
    """Extrai o texto embutido de cada página e o texto canônico unido."""
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
        page_texts = [page.extract_text() for page in reader.pages]
    except Exception as error:
        raise CanonicalTextError(
            "O PDF não pôde ser lido para extração de texto."
        ) from error

    pages: list[PdfPageText] = []
    parts: list[str] = []
    for index, extracted in enumerate(page_texts, start=1):
        normalized = sanitize_text(
            (extracted or "").replace("\r\n", "\n").replace("\r", "\n")
        ).strip()
        if normalized:
            pages.append(
                PdfPageText(
                    page_number=index,
                    text=normalized,
                    sha256=hashlib.sha256(
                        normalized.encode("utf-8")
                    ).hexdigest(),
                )
            )
            parts.append(normalized)
        else:
            pages.append(
                PdfPageText(page_number=index, text=None, sha256=None)
            )

    joined = "\n\n".join(parts)
    return PdfCanonicalText(
        pages=tuple(pages),
        text=joined,
        sha256=hashlib.sha256(joined.encode("utf-8")).hexdigest(),
        parser_version=PDF_PARSER_VERSION,
        pages_with_text=len(parts),
    )


def derive_pdf_layout_text(raw_body: bytes) -> PdfCanonicalText:
    """Extrai texto na ordem visual para tabelas rotacionadas preservadas."""
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
        page_texts = [
            page.extract_text(extraction_mode="layout") for page in reader.pages
        ]
    except Exception as error:
        raise CanonicalTextError(
            "O PDF não pôde ser lido para extração de texto em layout."
        ) from error

    pages: list[PdfPageText] = []
    parts: list[str] = []
    for index, extracted in enumerate(page_texts, start=1):
        normalized = sanitize_text(
            (extracted or "").replace("\r\n", "\n").replace("\r", "\n")
        ).strip()
        if normalized:
            pages.append(
                PdfPageText(
                    page_number=index,
                    text=normalized,
                    sha256=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
                )
            )
            parts.append(normalized)
        else:
            pages.append(PdfPageText(page_number=index, text=None, sha256=None))

    joined = "\n\n".join(parts)
    return PdfCanonicalText(
        pages=tuple(pages),
        text=joined,
        sha256=hashlib.sha256(joined.encode("utf-8")).hexdigest(),
        parser_version=PDF_LAYOUT_TEXT_VERSION,
        pages_with_text=len(parts),
    )
