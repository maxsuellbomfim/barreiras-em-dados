"""Adaptador opcional e rastreável para o conversor local AnyDoc.

AnyDoc é usado apenas para produzir texto derivado de documentos. O acervo
bruto, a extração numérica determinística e a evidência por página continuam
sob responsabilidade do pipeline existente.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

ANYDOC_PARSER_VERSION = "firecrawl-anydoc/0.1.2"
MAX_INPUT_BYTES = 64 * 1024 * 1024


class AnyDocUnavailable(RuntimeError):
    """A dependência opcional não está instalada no worker."""


class AnyDocConversionError(RuntimeError):
    """A conversão local não produziu uma saída utilizável."""


@dataclass(frozen=True)
class AnyDocOutput:
    """Saída derivada sem substituir o artefato bruto."""

    markdown: str
    detected_format: str | None
    parser_version: str
    input_sha256: str
    output_sha256: str
    input_bytes: int


def convert_to_markdown(
    body: bytes,
    *,
    format_hint: str | None = None,
) -> AnyDocOutput:
    """Converte bytes com AnyDoc e devolve hashes para rastreabilidade.

    O hint só é necessário para formatos sem assinatura própria, como CSV.
    Nenhum cálculo financeiro deve depender do Markdown retornado.
    """
    if not isinstance(body, bytes):
        raise TypeError("AnyDoc recebe bytes do artefato bruto.")
    if not body:
        raise AnyDocConversionError("O artefato está vazio.")
    if len(body) > MAX_INPUT_BYTES:
        raise AnyDocConversionError("O artefato excede o limite local do worker.")

    try:
        import anydoc
    except ImportError as error:
        raise AnyDocUnavailable(
            "Instale a dependência opcional 'anydoc' para usar este adaptador."
        ) from error

    input_sha256 = hashlib.sha256(body).hexdigest()
    try:
        detected = anydoc.format_from_bytes(body)
        if format_hint:
            markdown = anydoc.to_markdown_bytes(body, format_hint)
        else:
            markdown = anydoc.to_markdown_bytes(body)
    except Exception as error:
        raise AnyDocConversionError(
            "O documento não pôde ser convertido localmente."
        ) from error
    if not isinstance(markdown, str) or not markdown.strip():
        raise AnyDocConversionError("AnyDoc retornou Markdown vazio.")

    return AnyDocOutput(
        markdown=markdown,
        detected_format=detected,
        parser_version=ANYDOC_PARSER_VERSION,
        input_sha256=input_sha256,
        output_sha256=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        input_bytes=len(body),
    )
