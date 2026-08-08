from __future__ import annotations

import json
import unittest
from pathlib import Path

from barreiras_docproc.gazette_documents import DocumentBlock
from barreiras_docproc.gazette_segmentation import (
    build_document_drafts,
    propose_boundaries,
)

FIXTURE = (
    Path(__file__).parents[2]
    / "fixtures"
    / "sources"
    / "querido_diario"
    / "edition-4706-pages.json"
)


def load_blocks() -> tuple[DocumentBlock, ...]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return tuple(
        DocumentBlock.create(
            page_number=page["page_number"],
            block_order=raw["block_order"],
            text=raw["text"],
        )
        for page in payload["pages"]
        for raw in page["blocks"]
    )


class GazetteSegmentationTests(unittest.TestCase):
    def test_separates_only_complete_headings_at_structural_page_starts(self) -> None:
        blocks = load_blocks()

        proposals = propose_boundaries(blocks)
        documents = build_document_drafts(blocks, proposals)

        self.assertEqual(
            [proposal.start_block for proposal in proposals],
            [0, 2, 4],
        )
        self.assertEqual(len(documents), 3)
        self.assertEqual(
            documents[0].literal_title,
            "PORTARIA Nº 261, DE 29 DE JULHO DE 2026.",
        )
        self.assertIn("acompanhamento e fiscalização", documents[0].full_text)
        self.assertTrue(documents[0].full_text.endswith("data de sua publicação."))
        self.assertEqual(documents[0].document_type, "portaria")
        self.assertEqual(documents[2].document_type, "edital")

    def test_keeps_page_continuation_inside_previous_document(self) -> None:
        blocks = (
            DocumentBlock.create(
                page_number=1,
                block_order=0,
                text=(
                    "DECRETO Nº 123, DE 1º DE AGOSTO DE 2026.\n"
                    "Art. 1º Institui comissão."
                ),
            ),
            DocumentBlock.create(
                page_number=2,
                block_order=0,
                text=(
                    "Art. 2º A comissão terá cinco integrantes.\n"
                    "Art. 3º Este Decreto entra em vigor."
                ),
            ),
        )

        documents = build_document_drafts(blocks, propose_boundaries(blocks))

        self.assertEqual(len(documents), 1)
        self.assertIn("Art. 3º Este Decreto entra em vigor.", documents[0].full_text)

    def test_does_not_split_uppercase_text_without_complete_heading(self) -> None:
        blocks = (
            DocumentBlock.create(
                page_number=1,
                block_order=0,
                text="EDITAL Nº 20/2026\nConvoca os interessados.",
            ),
            DocumentBlock.create(
                page_number=2,
                block_order=0,
                text="RELAÇÃO DE DOCUMENTOS\nDocumento de identidade.\nComprovante.",
            ),
        )

        proposals = propose_boundaries(blocks)

        self.assertEqual([proposal.start_block for proposal in proposals], [0])

    def test_keeps_multiple_people_in_the_same_official_act(self) -> None:
        blocks = (
            DocumentBlock.create(
                page_number=1,
                block_order=0,
                text=(
                    "PORTARIA Nº 80/2026\nArt. 1º Designar ANA SILVA e "
                    "BRUNO SOUZA para compor a comissão."
                ),
            ),
        )

        documents = build_document_drafts(blocks, propose_boundaries(blocks))

        self.assertEqual(len(documents), 1)
        self.assertIn("ANA SILVA e BRUNO SOUZA", documents[0].full_text)


if __name__ == "__main__":
    unittest.main()
