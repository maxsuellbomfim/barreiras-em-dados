"""Extração literal e rastreável de documentos DOCX oficiais.

O resultado é texto derivado para busca e leitura. Ele nunca substitui os
bytes preservados nem serve como fonte para cálculos financeiros.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

DOCX_PARSER_VERSION = "docx-wordprocessingml/1.0.0"
MAX_DOCUMENT_XML_BYTES = 16 * 1024 * 1024
WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WORD = f"{{{WORD_NAMESPACE}}}"


class DocxStructureError(RuntimeError):
    """O pacote não possui uma estrutura DOCX processável."""


@dataclass(frozen=True)
class DocxTextBlock:
    """Bloco visível conservado na ordem do documento."""

    kind: str
    text: str


@dataclass(frozen=True)
class DocxText:
    """Texto derivado com identidade verificável do bruto e da saída."""

    text: str
    blocks: tuple[DocxTextBlock, ...]
    parser_version: str
    input_sha256: str
    text_sha256: str


def _visible_text(element) -> str:
    fragments: list[str] = []
    for node in element.iter():
        if node.tag == f"{WORD}t" and node.text:
            fragments.append(node.text)
        elif node.tag == f"{WORD}tab":
            fragments.append("\t")
        elif node.tag in {f"{WORD}br", f"{WORD}cr"}:
            fragments.append("\n")
    return "".join(fragments)


def _table_row_text(row) -> str:
    cells: list[str] = []
    for cell in row.findall(f"{WORD}tc"):
        paragraphs = [
            text
            for paragraph in cell.iter(f"{WORD}p")
            if (text := _visible_text(paragraph))
        ]
        cells.append("\n".join(paragraphs))
    return "\t".join(cells)


def _document_blocks(document_xml: bytes) -> tuple[DocxTextBlock, ...]:
    try:
        document = ElementTree.fromstring(document_xml)
    except (DefusedXmlException, ParseError) as error:
        raise DocxStructureError(
            "O XML principal do DOCX é inválido."
        ) from error

    body = document.find(f"{WORD}body")
    if body is None:
        raise DocxStructureError("O XML principal do DOCX não possui corpo.")

    blocks: list[DocxTextBlock] = []
    for child in body:
        if child.tag == f"{WORD}p":
            text = _visible_text(child)
            if text:
                blocks.append(DocxTextBlock(kind="paragraph", text=text))
        elif child.tag == f"{WORD}tbl":
            for row in child.findall(f"{WORD}tr"):
                text = _table_row_text(row)
                if text:
                    blocks.append(DocxTextBlock(kind="table_row", text=text))
    return tuple(blocks)


def derive_docx_text(body: bytes) -> DocxText:
    """Extrai texto visível do documento principal sem inferência."""

    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            names = set(archive.namelist())
            if not {"[Content_Types].xml", "word/document.xml"}.issubset(names):
                raise DocxStructureError(
                    "O pacote não contém a estrutura obrigatória de um DOCX."
                )
            if archive.getinfo("word/document.xml").file_size > MAX_DOCUMENT_XML_BYTES:
                raise DocxStructureError(
                    "O XML principal do DOCX excede o limite seguro."
                )
            document_xml = archive.read("word/document.xml")
    except (zipfile.BadZipFile, OSError) as error:
        raise DocxStructureError("O pacote DOCX é inválido.") from error

    blocks = _document_blocks(document_xml)
    text = "\n".join(block.text for block in blocks)
    if not text.strip():
        raise DocxStructureError("O DOCX não contém texto visível.")
    return DocxText(
        text=text,
        blocks=blocks,
        parser_version=DOCX_PARSER_VERSION,
        input_sha256=hashlib.sha256(body).hexdigest(),
        text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )
