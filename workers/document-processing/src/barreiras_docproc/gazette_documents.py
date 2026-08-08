"""Contratos literais para documentos derivados do Diário Oficial.

Este módulo não resume nem interpreta conteúdo. Ele só representa blocos
ordenados e documentos cujo título e texto podem ser conferidos literalmente.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

DocumentStatus = Literal["validated", "edition_fallback"]
BoundingBox = tuple[float, float, float, float]


def block_sha256(text: str) -> str:
    """Calcula o hash do texto literal, sem normalização destrutiva."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DocumentBlock:
    page_number: int
    block_order: int
    text: str
    sha256: str
    bbox: BoundingBox | None = None

    @classmethod
    def create(
        cls,
        *,
        page_number: int,
        block_order: int,
        text: str,
        bbox: BoundingBox | None = None,
    ) -> DocumentBlock:
        if page_number < 1:
            raise ValueError("page_number deve ser positivo")
        if block_order < 0:
            raise ValueError("block_order não pode ser negativo")
        if not text:
            raise ValueError("bloco documental não pode ser vazio")
        return cls(
            page_number=page_number,
            block_order=block_order,
            text=text,
            sha256=block_sha256(text),
            bbox=bbox,
        )


@dataclass(frozen=True)
class GazetteDocumentDraft:
    first_block: int
    last_block: int
    page_start: int
    page_end: int
    literal_title: str
    full_text: str
    status: DocumentStatus
    document_type: str | None = None

    def __post_init__(self) -> None:
        if self.first_block < 0 or self.last_block < self.first_block:
            raise ValueError("intervalo de blocos inválido")
        if self.page_start < 1 or self.page_end < self.page_start:
            raise ValueError("intervalo de páginas inválido")
        if not self.full_text:
            raise ValueError("documento integral não pode ser vazio")
        if not self.literal_title or self.literal_title not in self.full_text:
            raise ValueError("título não é literal no documento")
        if self.status not in ("validated", "edition_fallback"):
            raise ValueError("status documental inválido")


def ordered_blocks(blocks: Iterable[DocumentBlock]) -> tuple[DocumentBlock, ...]:
    """Ordena blocos e rejeita posições ambíguas."""
    result = tuple(
        sorted(blocks, key=lambda block: (block.page_number, block.block_order))
    )
    positions = [(block.page_number, block.block_order) for block in result]
    if len(set(positions)) != len(positions):
        raise ValueError("posição duplicada de bloco documental")
    return result


def join_literal_blocks(blocks: Sequence[DocumentBlock]) -> str:
    """Une blocos completos sem recortar ou reescrever seu conteúdo."""
    return "\n\n".join(block.text for block in ordered_blocks(blocks))


def literal_title(text: str) -> str:
    """Retorna a primeira linha não vazia exatamente como publicada."""
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    raise ValueError("documento sem linha de título literal")
