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
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .canonical import sanitize_text

# 1.1.0: modelo `por` do tessdata_best (1.0.0 usava o tessdata_fast da
# distribuição). Corrige erros de dígito sem perder acentos; não reconhece `§`
# (auditoria de 25/09/2026). Só páginas ainda não lidas usam esta versão.
OCR_PARSER_VERSION = "gazette-ocr-text/1.1.0"
# Modelo da distribuição (tessdata_fast), ainda usado fora do Diário.
FAST_OCR_PARSER_VERSION = "gazette-ocr-text/1.0.0"
GAZETTE_OCR_MODEL_SHA256 = (
    "711de9dbb8052067bd42f16b9119967f30bada80d57e2ef24f65d09f531adb04"
)
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

# O PDFium não é thread-safe; o Tesseract roda em subprocesso e pode ser
# paralelizado, então só a renderização é serializada.
_PDFIUM_LOCK = threading.Lock()


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
        tessdata_dir: str | None = None,
        expected_model_sha256: str | None = None,
    ) -> None:
        if page_segmentation_mode is not None and not 0 <= page_segmentation_mode <= 13:
            raise OcrError("Modo de segmentação do Tesseract deve estar entre 0 e 13.")
        binary = shutil.which("tesseract")
        if binary is None:
            raise OcrError(
                "Binário tesseract não encontrado; instale tesseract-ocr e "
                "tesseract-ocr-por."
            )
        if (tessdata_dir is None) != (expected_model_sha256 is None):
            raise OcrError("Modelo do Tesseract exige diretório e hash juntos.")
        if tessdata_dir is not None:
            model = Path(tessdata_dir) / f"{language}.traineddata"
            if not model.is_file():
                raise OcrError(f"Modelo do Tesseract ausente: {model}.")
            digest = hashlib.sha256(model.read_bytes()).hexdigest()
            if digest != expected_model_sha256:
                raise OcrError("Modelo do Tesseract diverge do hash fixado.")
        self.binary = binary
        self.language = language
        self.tessdata_dir = tessdata_dir
        self.page_segmentation_mode = page_segmentation_mode
        mode = page_segmentation_mode if page_segmentation_mode is not None else 3
        base = OCR_PARSER_VERSION if tessdata_dir else FAST_OCR_PARSER_VERSION
        self.parser_version = f"{base}+tesseract-psm{mode}"

    def image_to_text(self, png_bytes: bytes) -> str:
        arguments = [self.binary, "stdin", "stdout", "-l", self.language]
        if self.tessdata_dir is not None:
            arguments.extend(["--tessdata-dir", self.tessdata_dir])
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
        with _PDFIUM_LOCK:
            document = pypdfium2.PdfDocument(pdf_bytes)
            try:
                page = document[page_number - 1]
                bitmap = page.render(scale=RENDER_SCALE)
                image = bitmap.to_pil()
            finally:
                document.close()
        if rotation_degrees:
            image = image.rotate(rotation_degrees, expand=True)
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
