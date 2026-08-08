"""Segmentação conservadora do Diário por fronteiras estruturais fortes."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from .gazette_documents import (
    DocumentBlock,
    GazetteDocumentDraft,
    join_literal_blocks,
    literal_title,
    ordered_blocks,
)

SEGMENTER_VERSION = "gazette-structural-segmenter/1.0.0"
BoundarySource = Literal["layout", "deterministic", "ai_assist"]

_NUMBER = r"(?:N(?:O|\.|º|°)?\s*)?\d"
_HEADING_PATTERNS = (
    ("portaria", re.compile(rf"^PORTARIA\s+{_NUMBER}", re.IGNORECASE)),
    ("decreto", re.compile(rf"^DECRETO\s+{_NUMBER}", re.IGNORECASE)),
    ("lei", re.compile(rf"^LEI\s+{_NUMBER}", re.IGNORECASE)),
    ("resolucao", re.compile(rf"^RESOLUCAO\s+{_NUMBER}", re.IGNORECASE)),
    (
        "edital",
        re.compile(
            rf"^EDITAL(?:\s+DE\s+[A-Z][A-Z ]{{2,60}})?\s+{_NUMBER}",
            re.IGNORECASE,
        ),
    ),
    (
        "contrato",
        re.compile(
            rf"^EXTRATO\s+(?:DO|DE)\s+(?:CONTRATO|TERMO).*?{_NUMBER}",
            re.IGNORECASE,
        ),
    ),
    (
        "aviso",
        re.compile(
            rf"^AVISO(?:\s+DE\s+[A-Z][A-Z ]{{2,60}})?\s+{_NUMBER}", re.IGNORECASE
        ),
    ),
)


@dataclass(frozen=True)
class BoundaryProposal:
    start_block: int
    evidence: tuple[str, ...]
    confidence: Decimal
    source: BoundarySource


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(
        character for character in normalized if not unicodedata.combining(character)
    )


def _document_type(title: str) -> str | None:
    folded = _fold(title)
    for document_type, pattern in _HEADING_PATTERNS:
        if pattern.search(folded):
            return document_type
    return None


def propose_boundaries(
    blocks: Sequence[DocumentBlock],
) -> tuple[BoundaryProposal, ...]:
    """Propõe somente fronteiras que combinam estrutura e título completo."""
    ordered = ordered_blocks(blocks)
    if not ordered:
        return ()
    proposals = [
        BoundaryProposal(
            start_block=0,
            evidence=("edition_start",),
            confidence=Decimal("1.000"),
            source="layout",
        )
    ]
    for index, block in enumerate(ordered[1:], start=1):
        title = literal_title(block.text)
        document_type = _document_type(title)
        if block.block_order != 0 or document_type is None:
            continue
        proposals.append(
            BoundaryProposal(
                start_block=index,
                evidence=("page_start", f"literal_{document_type}_heading"),
                confidence=Decimal("0.990"),
                source="deterministic",
            )
        )
    return tuple(proposals)


def build_document_drafts(
    blocks: Sequence[DocumentBlock],
    proposals: Sequence[BoundaryProposal],
) -> tuple[GazetteDocumentDraft, ...]:
    """Materializa documentos sem remover nem reescrever blocos."""
    ordered = ordered_blocks(blocks)
    if not ordered:
        return ()
    starts = [proposal.start_block for proposal in proposals]
    if not starts or starts[0] != 0 or starts != sorted(set(starts)):
        raise ValueError("fronteiras documentais inválidas")
    if starts[-1] >= len(ordered):
        raise ValueError("fronteira fora dos blocos da edição")

    documents: list[GazetteDocumentDraft] = []
    for document_order, start in enumerate(starts):
        end = (
            starts[document_order + 1] - 1
            if document_order + 1 < len(starts)
            else len(ordered) - 1
        )
        document_blocks = ordered[start : end + 1]
        text = join_literal_blocks(document_blocks)
        title = literal_title(document_blocks[0].text)
        documents.append(
            GazetteDocumentDraft(
                first_block=start,
                last_block=end,
                page_start=document_blocks[0].page_number,
                page_end=document_blocks[-1].page_number,
                literal_title=title,
                full_text=text,
                status="validated",
                document_type=_document_type(title),
            )
        )
    return tuple(documents)
