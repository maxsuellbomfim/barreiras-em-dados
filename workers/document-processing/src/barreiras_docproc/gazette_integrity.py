"""Validação determinística de cobertura dos documentos do Diário."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

from .gazette_documents import (
    DocumentBlock,
    GazetteDocumentDraft,
    join_literal_blocks,
    ordered_blocks,
)
from .gazette_segmentation import document_title

VALIDATOR_VERSION = "gazette-integrity/1.0.0"


@dataclass(frozen=True)
class IntegrityReport:
    valid: bool
    errors: tuple[str, ...]
    source_sha256: str
    documents_sha256: str
    blocks_expected: int
    blocks_observed: int


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _unique_errors(errors: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(errors))


def _fallback(blocks: tuple[DocumentBlock, ...]) -> GazetteDocumentDraft:
    text = join_literal_blocks(blocks)
    return GazetteDocumentDraft(
        first_block=0,
        last_block=len(blocks) - 1,
        page_start=blocks[0].page_number,
        page_end=blocks[-1].page_number,
        literal_title=document_title(blocks[0].text),
        full_text=text,
        status="edition_fallback",
    )


def validate_or_fallback(
    blocks: Sequence[DocumentBlock],
    drafts: Sequence[GazetteDocumentDraft],
) -> tuple[tuple[GazetteDocumentDraft, ...], IntegrityReport]:
    """Publica a segmentação só se cada bloco aparecer uma única vez."""
    ordered = ordered_blocks(blocks)
    if not ordered:
        raise ValueError("edição sem blocos não pode ser publicada")

    source_text = join_literal_blocks(ordered)
    documents_text = "\n\n".join(document.full_text for document in drafts)
    errors: list[str] = []
    observed = 0
    expected_start = 0

    if not drafts:
        errors.append("block_gap")
    for document in drafts:
        if document.first_block < expected_start:
            errors.append("block_overlap_or_order")
        elif document.first_block > expected_start:
            errors.append("block_gap")

        if (
            document.first_block < 0
            or document.last_block < document.first_block
            or document.last_block >= len(ordered)
        ):
            errors.append("block_range_invalid")
            continue

        selected = ordered[document.first_block : document.last_block + 1]
        observed += len(selected)
        if document.full_text != join_literal_blocks(selected):
            errors.append("text_changed")
        if document.literal_title not in document.full_text:
            errors.append("title_not_literal")
        expected_start = document.last_block + 1

    if expected_start < len(ordered):
        errors.append("block_gap")
    elif expected_start > len(ordered):
        errors.append("block_range_invalid")

    source_sha256 = _sha256(source_text)
    documents_sha256 = _sha256(documents_text)
    if source_sha256 != documents_sha256:
        errors.append("content_hash_mismatch")

    unique_errors = _unique_errors(errors)
    report = IntegrityReport(
        valid=not unique_errors,
        errors=unique_errors,
        source_sha256=source_sha256,
        documents_sha256=documents_sha256,
        blocks_expected=len(ordered),
        blocks_observed=observed,
    )
    if report.valid:
        return tuple(drafts), report
    return (_fallback(ordered),), report
