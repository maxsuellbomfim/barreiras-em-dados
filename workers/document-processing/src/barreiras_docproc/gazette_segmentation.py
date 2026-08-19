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

SEGMENTER_VERSION = "gazette-structural-segmenter/2.0.0"
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
            r"^(?:EXPOSICAO\s+DE\s+)?JUSTIFICATIVA\b.*\d",
            re.IGNORECASE,
        ),
    ),
    # Títulos sem número existem nestes dois formatos e sempre em caixa
    # alta; sem IGNORECASE, frases correntes nunca casam.
    ("retificacao", re.compile(r"^RETIFICACAO\s*$")),
    ("aviso", re.compile(r"^AVISO\s+DE\s+[A-Z][A-Z ]{2,60}$")),
)

_GENERIC_HEADING_PATTERNS = (
    ("portaria", re.compile(r"^PORTARIA\b.*\d", re.IGNORECASE)),
    ("decreto", re.compile(r"^DECRETO\b.*\d", re.IGNORECASE)),
    ("lei", re.compile(r"^LEI\b.*\d", re.IGNORECASE)),
    ("resolucao", re.compile(r"^RESOLUCAO\b.*\d", re.IGNORECASE)),
    ("edital", re.compile(r"^EDITAL\b.*\d", re.IGNORECASE)),
    ("aviso", re.compile(r"^AVISO\b.*\d", re.IGNORECASE)),
    ("convocacao", re.compile(r"^(?:ATO\s+DE\s+)?CONVOCACAO\b.*\d", re.IGNORECASE)),
    ("notificacao", re.compile(r"^NOTIFICACAO\b.*\d", re.IGNORECASE)),
)

# O Diário publica atos do próprio município; "Lei Federal nº …" e
# "Decreto Estadual nº …" em início de linha são sempre citações no corpo.
_SPHERE_CITATION = re.compile(
    r"^(?:LEI|DECRETO)\s+(?:FEDERAL|ESTADUAL)\b", re.IGNORECASE
)
# Linha que termina em conectivo minúsculo ou pontuação de continuação está
# no meio de uma frase; título oficial nunca termina assim.
_DANGLING_END = re.compile(
    r"(?:[,;(]|\b(?:de|da|do|das|dos|no|na|nos|nas|em|e|ao|aos|para|com|que|o|a|os|as))$"
)
# Fragmento curto em caixa alta seguido do resto da palavra na linha
# seguinte (ex.: "DECR" + "ETO Nº 140…") é quebra de linha do OCR.
_BROKEN_PREFIX = re.compile(r"^[A-Z]{1,8}$")
# Linhas do cabeçalho institucional repetido em toda página do Diário.
_MASTHEAD_MARKERS = re.compile(
    r"PREFEITURA|MUNICIP(?:IO|AL)\s+DE\s+BARREIRAS|CAMARA\s+MUNICIPAL"
    r"|ESTADO\s+DA\s+BAHIA|DIARIO\s+OFICIAL|\bEDICAO\s+\d|\bCNPJ\b|\bCEP\b"
    r"|\bFONE\b|\bSITE\b|WWW\.",
    re.IGNORECASE,
)
# Linhas de timbre e bandeiras de seção observadas ficam abaixo de 60
# caracteres; parágrafos de corpo reais medem 70+ neste acervo.
_MASTHEAD_MAX_LENGTH = 60
_FALLBACK_TITLE_MIN_LENGTH = 12
_HEADING_SCAN_WINDOW = 24


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


def _acceptable_title(candidate: str, folded: str) -> bool:
    """Rejeita linhas que casam padrão mas são citações no meio do corpo."""
    return (
        candidate[:1].isupper()
        and not _SPHERE_CITATION.match(folded)
        and not _DANGLING_END.search(candidate)
    )


def _masthead_like(candidate: str, folded: str) -> bool:
    return (
        len(candidate) <= _MASTHEAD_MAX_LENGTH
        or _MASTHEAD_MARKERS.search(folded) is not None
    )


def _match_heading(candidate: str, folded: str) -> str | None:
    for document_type, pattern in (*_HEADING_PATTERNS, *_GENERIC_HEADING_PATTERNS):
        # Algumas extrações conservam ``Nº``/``N°`` e outras entregam
        # variantes já decompostas. Testamos a linha literal e a forma
        # sem acentos; nenhuma normalização é aplicada ao texto salvo.
        if pattern.match(candidate) or pattern.match(folded):
            return document_type
    return None


def _heading_from_text(text: str) -> tuple[str, str] | None:
    """Encontra um título forte no início do bloco, sem interpretar o corpo.

    Os PDFs municipais repetem o cabeçalho institucional antes do título; o
    título pode estar algumas linhas abaixo da primeira. A varredura só
    atravessa linhas com cara de cabeçalho (curtas ou institucionais) e para
    na primeira linha de corpo: citações a outras leis dentro de um artigo
    nunca viram fronteira de documento.
    """
    raw_lines = text.splitlines(keepends=True)
    stripped = [line.strip() for line in raw_lines]
    for index, candidate in enumerate(stripped):
        if index >= _HEADING_SCAN_WINDOW:
            break
        if not candidate:
            continue
        folded = _fold(candidate)
        document_type = _match_heading(candidate, folded)
        if document_type is not None and _acceptable_title(candidate, folded):
            return candidate, document_type
        if document_type is None and _BROKEN_PREFIX.match(folded):
            # OCR quebra palavras do título ("DECR" + "ETO Nº 140…"); o
            # título literal preserva as duas linhas exatamente como salvas.
            next_index = index + 1
            next_candidate = (
                stripped[next_index] if next_index < len(stripped) else ""
            )
            if next_candidate:
                next_folded = _fold(next_candidate)
                joined_type = _match_heading(
                    folded + next_folded, folded + next_folded
                )
                if (
                    joined_type is not None
                    and not _SPHERE_CITATION.match(folded + next_folded)
                    and not _DANGLING_END.search(next_candidate)
                ):
                    title = (raw_lines[index] + raw_lines[next_index]).strip()
                    return title, joined_type
        if _masthead_like(candidate, folded):
            continue
        return None
    return None


def _fallback_title(text: str) -> str:
    """Primeira linha com cara de conteúdo, pulando fragmentos do cabeçalho."""
    for line in text.splitlines():
        candidate = line.strip()
        if not candidate or len(candidate) < _FALLBACK_TITLE_MIN_LENGTH:
            continue
        if _MASTHEAD_MARKERS.search(_fold(candidate)):
            continue
        return candidate
    return literal_title(text)


def document_heading(text: str) -> tuple[str, str | None]:
    """Retorna título literal e tipo detectado; sem título forte, usa fallback."""
    heading = _heading_from_text(text)
    if heading:
        return heading
    return _fallback_title(text), None


def document_title(text: str) -> str:
    """Retorna o título da matéria quando houver, mantendo a linha literal."""
    return document_heading(text)[0]


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
        title, heading_type = document_heading(document_blocks[0].text)
        documents.append(
            GazetteDocumentDraft(
                first_block=start,
                last_block=end,
                page_start=document_blocks[0].page_number,
                page_end=document_blocks[-1].page_number,
                literal_title=title,
                full_text=text,
                status="validated",
                document_type=heading_type or _document_type(title),
            )
        )
    return tuple(documents)
