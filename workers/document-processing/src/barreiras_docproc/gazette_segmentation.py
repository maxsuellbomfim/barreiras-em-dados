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

SEGMENTER_VERSION = "gazette-structural-segmenter/1.1.0"
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
    (
        "convocacao",
        re.compile(rf"^CONVOCACAO(?:\s+PUBLICA)?\s+{_NUMBER}", re.IGNORECASE),
    ),
    (
        "notificacao",
        re.compile(
            rf"^NOTIFICACAO(?:\s+DE\s+[A-Z][A-Z ]{{2,60}})?\s+{_NUMBER}",
            re.IGNORECASE,
        ),
    ),
    (
        "justificativa",
        re.compile(
            r"^(?:EXPOSICAO\s+DE\s+)?JUSTIFICATIVA(?:\s+DA|\s+DO|\s+DE)?",
            re.IGNORECASE,
        ),
    ),
)

_GENERIC_HEADING_PATTERNS = (
    ("portaria", re.compile(r"^PORTARIA\b.*\d", re.IGNORECASE)),
    ("decreto", re.compile(r"^DECRETO\b.*\d", re.IGNORECASE)),
    ("lei", re.compile(r"^LEI\b.*\d", re.IGNORECASE)),
    ("resolucao", re.compile(r"^RESOLUCAO\b.*\d", re.IGNORECASE)),
    ("edital", re.compile(r"^EDITAL\b.*\d", re.IGNORECASE)),
    ("aviso", re.compile(r"^AVISO\b.*\d", re.IGNORECASE)),
    ("convocacao", re.compile(r"^CONVOCACAO\b.*\d", re.IGNORECASE)),
    ("notificacao", re.compile(r"^NOTIFICACAO\b.*\d", re.IGNORECASE)),
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


def _heading_from_text(text: str) -> tuple[str, str] | None:
    """Encontra um título forte no início do bloco, sem interpretar o corpo.

    Os PDFs municipais repetem o cabeçalho institucional antes do título. O
    título pode, portanto, estar algumas linhas abaixo da primeira linha. A
    janela curta reduz falsos cortes em artigos que mencionam outro decreto.
    """
    for line_number, raw_line in enumerate(text.splitlines()):
        if line_number >= 24:
            break
        candidate = raw_line.strip()
        if not candidate:
            continue
        folded = _fold(candidate)
        for document_type, pattern in (*_HEADING_PATTERNS, *_GENERIC_HEADING_PATTERNS):
            # Algumas extrações conservam ``Nº``/``N°`` e outras entregam
            # variantes já decompostas. Testamos a linha literal e a forma
            # sem acentos; nenhuma normalização é aplicada ao texto salvo.
            if pattern.match(candidate) or pattern.match(folded):
                return candidate, document_type
    return None


def document_title(text: str) -> str:
    """Retorna o título da matéria quando houver, mantendo a linha literal."""
    heading = _heading_from_text(text)
    return heading[0] if heading else literal_title(text)


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
        heading = _heading_from_text(block.text)
        document_type = heading[1] if heading else None
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
        title = document_title(document_blocks[0].text)
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
