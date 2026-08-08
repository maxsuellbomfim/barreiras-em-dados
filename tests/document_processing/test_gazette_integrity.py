from __future__ import annotations

import unittest

from barreiras_docproc.gazette_documents import (
    DocumentBlock,
    GazetteDocumentDraft,
    join_literal_blocks,
)
from barreiras_docproc.gazette_integrity import validate_or_fallback
from barreiras_docproc.gazette_segmentation import (
    build_document_drafts,
    propose_boundaries,
)


def sample_blocks() -> tuple[DocumentBlock, ...]:
    return (
        DocumentBlock.create(
            page_number=1,
            block_order=0,
            text="PORTARIA Nº 10/2026\nArt. 1º Designar ANA SILVA.",
        ),
        DocumentBlock.create(
            page_number=1,
            block_order=1,
            text="Art. 2º Esta Portaria entra em vigor.",
        ),
        DocumentBlock.create(
            page_number=2,
            block_order=0,
            text="EDITAL Nº 20/2026\nConvoca os interessados.",
        ),
        DocumentBlock.create(
            page_number=2,
            block_order=1,
            text="O prazo termina em 30 de agosto de 2026.",
        ),
    )


def draft(
    blocks: tuple[DocumentBlock, ...],
    start: int,
    end: int,
) -> GazetteDocumentDraft:
    selected = blocks[start : end + 1]
    return GazetteDocumentDraft(
        first_block=start,
        last_block=end,
        page_start=selected[0].page_number,
        page_end=selected[-1].page_number,
        literal_title=selected[0].text.splitlines()[0],
        full_text=join_literal_blocks(selected),
        status="validated",
    )


class GazetteIntegrityTests(unittest.TestCase):
    def test_accepts_exactly_once_ordered_block_coverage(self) -> None:
        blocks = sample_blocks()
        documents = build_document_drafts(blocks, propose_boundaries(blocks))

        published, report = validate_or_fallback(blocks, documents)

        self.assertTrue(report.valid)
        self.assertEqual(report.errors, ())
        self.assertEqual(report.source_sha256, report.documents_sha256)
        self.assertEqual(report.blocks_expected, 4)
        self.assertEqual(report.blocks_observed, 4)
        self.assertEqual(published, documents)

    def test_missing_block_forces_one_complete_edition_fallback(self) -> None:
        blocks = sample_blocks()

        published, report = validate_or_fallback(blocks, (draft(blocks, 0, 2),))

        self.assertFalse(report.valid)
        self.assertIn("block_gap", report.errors)
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0].status, "edition_fallback")
        self.assertEqual(published[0].full_text, join_literal_blocks(blocks))
        self.assertEqual(published[0].first_block, 0)
        self.assertEqual(published[0].last_block, 3)

    def test_overlap_forces_fallback_instead_of_duplicate_text(self) -> None:
        blocks = sample_blocks()
        overlapping = (draft(blocks, 0, 1), draft(blocks, 1, 3))

        published, report = validate_or_fallback(blocks, overlapping)

        self.assertFalse(report.valid)
        self.assertIn("block_overlap_or_order", report.errors)
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0].full_text, join_literal_blocks(blocks))

    def test_changed_text_forces_fallback(self) -> None:
        blocks = sample_blocks()
        original = draft(blocks, 0, 3)
        changed = GazetteDocumentDraft(
            first_block=original.first_block,
            last_block=original.last_block,
            page_start=original.page_start,
            page_end=original.page_end,
            literal_title=original.literal_title,
            full_text=original.full_text.replace("ANA SILVA", "OUTRA PESSOA"),
            status="validated",
        )

        published, report = validate_or_fallback(blocks, (changed,))

        self.assertFalse(report.valid)
        self.assertIn("text_changed", report.errors)
        self.assertNotIn("OUTRA PESSOA", published[0].full_text)
        self.assertIn("ANA SILVA", published[0].full_text)

    def test_reordered_documents_force_fallback(self) -> None:
        blocks = sample_blocks()
        reordered = (draft(blocks, 2, 3), draft(blocks, 0, 1))

        published, report = validate_or_fallback(blocks, reordered)

        self.assertFalse(report.valid)
        self.assertIn("block_overlap_or_order", report.errors)
        self.assertEqual(published[0].full_text, join_literal_blocks(blocks))


if __name__ == "__main__":
    unittest.main()
