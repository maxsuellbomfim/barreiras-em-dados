"""OCR das páginas escaneadas, com método declarado e versão fixada.

O texto produzido aqui nunca se disfarça de texto embutido: as linhas de
página levam `extraction_method='ocr'` e um parser_version próprio, para que
qualquer leitor saiba a origem e o grau de confiança do conteúdo.
"""

from __future__ import annotations

import hashlib
import io
import shutil
import subprocess
from dataclasses import dataclass
from typing import Protocol

from .canonical import sanitize_text

OCR_PARSER_VERSION = "gazette-ocr-text/1.0.0"
TCM_BA_OCR_PARSER_VERSION = "tcm-ba-document-ocr-text/1.0.0"


def parser_version_for_source(source: str) -> str:
    if source == "querido-diario":
        return OCR_PARSER_VERSION
    if source == "tcm-ba":
        return TCM_BA_OCR_PARSER_VERSION
    raise OcrError("Fonte OCR desconhecida.")


# 300 DPI é o ponto doce do Tesseract; PDFs usam 72 pontos por polegada.
RENDER_SCALE = 300 / 72
OCR_LANGUAGE = "por"


class OcrError(RuntimeError):
    """Falha explícita ao renderizar ou reconhecer uma página."""


@dataclass(frozen=True)
class OcrPageResult:
    page_number: int
    text: str
    sha256: str
    parser_version: str


class OcrEngine(Protocol):
    def image_to_text(self, png_bytes: bytes) -> str: ...


class TesseractEngine:
    """Chama o binário tesseract com idioma português via stdin/stdout."""

    def __init__(
        self,
        language: str = OCR_LANGUAGE,
        *,
        page_segmentation_mode: int | None = None,
    ) -> None:
        if page_segmentation_mode is not None and not 0 <= page_segmentation_mode <= 13:
            raise OcrError("Modo de segmentação do Tesseract deve estar entre 0 e 13.")
        binary = shutil.which("tesseract")
        if binary is None:
            raise OcrError(
                "Binário tesseract não encontrado; instale tesseract-ocr e "
                "tesseract-ocr-por."
            )
        self.binary = binary
        self.language = language
        self.page_segmentation_mode = page_segmentation_mode
        mode = page_segmentation_mode if page_segmentation_mode is not None else 3
        self.parser_version = f"{OCR_PARSER_VERSION}+tesseract-psm{mode}"

    def image_to_text(self, png_bytes: bytes) -> str:
        arguments = [self.binary, "stdin", "stdout", "-l", self.language]
        if self.page_segmentation_mode is not None:
            arguments.extend(["--psm", str(self.page_segmentation_mode)])
        completed = subprocess.run(  # noqa: S603 - argumentos fixos.
            arguments,
            input=png_bytes,
            capture_output=True,
            timeout=120,
            check=False,
        )
        if completed.returncode != 0:
            raise OcrError(
                "Tesseract falhou: "
                f"{completed.stderr.decode('utf-8', 'replace')[:200]}"
            )
        return completed.stdout.decode("utf-8", "replace")


def rasterize_page(
    pdf_bytes: bytes,
    page_number: int,
    *,
    rotation_degrees: int = 0,
) -> bytes:
    """Renderiza uma página (1-indexada) do PDF em PNG a ~300 DPI."""
    if rotation_degrees not in {0, 90, 180, 270}:
        raise OcrError("Rotação do OCR deve ser 0, 90, 180 ou 270 graus.")
    try:
        import pypdfium2
    except ImportError as error:
        raise OcrError(
            "Instale a dependência opcional 'ocr' para renderizar PDFs."
        ) from error

    try:
        document = pypdfium2.PdfDocument(pdf_bytes)
        try:
            page = document[page_number - 1]
            bitmap = page.render(scale=RENDER_SCALE)
            image = bitmap.to_pil()
            if rotation_degrees:
                image = image.rotate(rotation_degrees, expand=True)
        finally:
            document.close()
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    except OcrError:
        raise
    except Exception as error:
        raise OcrError(
            f"A página {page_number} não pôde ser renderizada."
        ) from error


def ocr_page(
    engine: OcrEngine,
    pdf_bytes: bytes,
    page_number: int,
    *,
    rotation_degrees: int = 0,
) -> OcrPageResult:
    """OCR de uma página; página em branco vira texto vazio explícito."""
    recognized = engine.image_to_text(
        rasterize_page(
            pdf_bytes,
            page_number,
            rotation_degrees=rotation_degrees,
        )
    )
    normalized = sanitize_text(
        recognized.replace("\r\n", "\n").replace("\r", "\n")
    ).strip()
    return OcrPageResult(
        page_number=page_number,
        text=normalized,
        sha256=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        parser_version=getattr(engine, "parser_version", OCR_PARSER_VERSION),
    )
