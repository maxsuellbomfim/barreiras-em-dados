from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from barreiras_docproc.gazette_documents import (
    DocumentBlock,
    GazetteDocumentDraft,
    block_sha256,
    join_literal_blocks,
    literal_title,
    ordered_blocks,
)

FIXTURE = (
    Path(__file__).parents[2]
    / "fixtures"
    / "sources"
    / "querido_diario"
    / "edition-4706-pages.json"
)


def fixture_blocks() -> tuple[DocumentBlock, ...]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    blocks: list[DocumentBlock] = []
    for page in payload["pages"]:
        for raw in page["blocks"]:
            blocks.append(
                DocumentBlock.create(
                    page_number=page["page_number"],
                    block_order=raw["block_order"],
                    text=raw["text"],
                )
            )
    return tuple(blocks)


class DocumentBlockTests(unittest.TestCase):
    def test_create_hashes_literal_utf8_text(self) -> None:
        text = "PORTARIA Nº 261 — acompanhamento e fiscalização."

        block = DocumentBlock.create(
            page_number=3,
            block_order=0,
            text=text,
        )

        self.assertEqual(block.text, text)
        self.assertEqual(
            block.sha256,
            hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(block.sha256, block_sha256(text))

    def test_orders_blocks_by_page_then_position(self) -> None:
        blocks = fixture_blocks()
        shuffled = (blocks[3], blocks[0], blocks[2], blocks[1])

        self.assertEqual(
            [
                (block.page_number, block.block_order)
                for block in ordered_blocks(shuffled)
            ],
            [(3, 0), (3, 1), (4, 0), (4, 1)],
        )

    def test_rejects_duplicate_page_position(self) -> None:
        block = DocumentBlock.create(page_number=1, block_order=0, text="Ato")

        with self.assertRaisesRegex(ValueError, "posição duplicada"):
            ordered_blocks((block, block))


class LiteralDocumentTests(unittest.TestCase):
    def test_joins_complete_blocks_without_truncating_words(self) -> None:
        first, second, *_ = fixture_blocks()
        joined = join_literal_blocks((first, second))

        self.assertIn("acompanhamento e fiscalização", joined)
        self.assertIn("Art. 2º Esta Portaria entra em vigor", joined)
        self.assertTrue(joined.endswith("data de sua publicação."))

    def test_title_is_an_exact_line_from_the_document(self) -> None:
        first = fixture_blocks()[0]

        title = literal_title(first.text)

        self.assertEqual(title, "PORTARIA Nº 261, DE 29 DE JULHO DE 2026.")
        self.assertIn(title, first.text)

    def test_document_draft_rejects_non_literal_title(self) -> None:
        first, second, *_ = fixture_blocks()
        text = join_literal_blocks((first, second))

        with self.assertRaisesRegex(ValueError, "título não é literal"):
            GazetteDocumentDraft(
                first_block=0,
                last_block=1,
                page_start=3,
                page_end=3,
                literal_title="Resumo inventado da Portaria",
                full_text=text,
                status="validated",
            )


if __name__ == "__main__":
    unittest.main()
