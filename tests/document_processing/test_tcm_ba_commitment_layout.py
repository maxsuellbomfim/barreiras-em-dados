from __future__ import annotations

import unittest

from barreiras_docproc.gazette_documents import DocumentBlock
from barreiras_docproc.pdf_layout import PdfLayoutPage
from barreiras_docproc.processing import TextArtifact
from barreiras_docproc.tcm_ba_commitment_layout import (
    find_spatial_budget_allocation,
)
from barreiras_docproc.tcm_ba_commitments import (
    TcmBaCommitmentCandidate,
    apply_spatial_budget_allocations,
    commitment_candidate_payload,
)


def block(
    text: str,
    *,
    order: int,
    bbox: tuple[float, float, float, float],
) -> DocumentBlock:
    return DocumentBlock.create(
        page_number=1,
        block_order=order,
        text=text,
        bbox=bbox,
    )


class TcmBaCommitmentLayoutTests(unittest.TestCase):
    def test_finds_unique_value_directly_below_budget_label(self) -> None:
        blocks = (
            block(
                "DOTAÇÃO ORÇAMENTÁRIA",
                order=0,
                bbox=(90.0, 700.0, 230.0, 712.0),
            ),
            block(
                "02.05.04.122.001.2001",
                order=1,
                bbox=(92.0, 680.0, 225.0, 692.0),
            ),
        )

        match = find_spatial_budget_allocation(blocks)

        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.value, "02.05.04.122.001.2001")
        self.assertEqual(match.label_block_order, 0)
        self.assertEqual(match.value_block_order, 1)
        self.assertEqual(match.relation, "below")

    def test_ignores_nearby_value_outside_budget_column(self) -> None:
        blocks = (
            block(
                "DOTAÇÃO ORÇAMENTÁRIA",
                order=0,
                bbox=(300.0, 700.0, 440.0, 712.0),
            ),
            block(
                "1.234,56",
                order=1,
                bbox=(80.0, 680.0, 140.0, 692.0),
            ),
            block(
                "02.05.04.122.001.2001",
                order=2,
                bbox=(302.0, 680.0, 435.0, 692.0),
            ),
        )

        match = find_spatial_budget_allocation(blocks)

        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.value_block_order, 2)

    def test_returns_none_when_two_cells_are_equally_plausible(self) -> None:
        blocks = (
            block(
                "DOTAÇÃO ORÇAMENTÁRIA",
                order=0,
                bbox=(200.0, 700.0, 340.0, 712.0),
            ),
            block(
                "02.05.04.122.001.2001",
                order=1,
                bbox=(190.0, 680.0, 325.0, 692.0),
            ),
            block(
                "02.06.04.122.001.2002",
                order=2,
                bbox=(215.0, 680.0, 350.0, 692.0),
            ),
        )

        self.assertIsNone(find_spatial_budget_allocation(blocks))

    def test_rejects_page_with_multiple_budget_labels(self) -> None:
        blocks = (
            block(
                "DOTAÇÃO ORÇAMENTÁRIA",
                order=0,
                bbox=(90.0, 700.0, 230.0, 712.0),
            ),
            block(
                "02.05.04.122.001.2001",
                order=1,
                bbox=(92.0, 680.0, 225.0, 692.0),
            ),
            block(
                "CLASSIFICAÇÃO ORÇAMENTÁRIA",
                order=2,
                bbox=(300.0, 650.0, 470.0, 662.0),
            ),
        )

        self.assertIsNone(find_spatial_budget_allocation(blocks))

    def test_rejects_unique_value_that_is_too_far_from_label(self) -> None:
        blocks = (
            block(
                "DOTAÇÃO ORÇAMENTÁRIA",
                order=0,
                bbox=(90.0, 700.0, 230.0, 712.0),
            ),
            block(
                "02.05.04.122.001.2001",
                order=1,
                bbox=(92.0, 650.0, 225.0, 662.0),
            ),
        )

        self.assertIsNone(find_spatial_budget_allocation(blocks))

    def test_rejects_first_cell_without_clear_separation_from_second(self) -> None:
        blocks = (
            block(
                "DOTAÇÃO ORÇAMENTÁRIA",
                order=0,
                bbox=(200.0, 700.0, 340.0, 712.0),
            ),
            block(
                "02.05.04.122.001.2001",
                order=1,
                bbox=(202.0, 680.0, 337.0, 692.0),
            ),
            block(
                "02.06.04.122.001.2002",
                order=2,
                bbox=(202.0, 676.0, 337.0, 688.0),
            ),
        )

        self.assertIsNone(find_spatial_budget_allocation(blocks))

    def test_accepts_unique_value_on_same_row_to_the_right(self) -> None:
        blocks = (
            block(
                "DOTAÇÃO ORÇAMENTÁRIA:",
                order=0,
                bbox=(80.0, 700.0, 220.0, 712.0),
            ),
            block(
                "02.05.04.122.001.2001",
                order=1,
                bbox=(230.0, 700.0, 365.0, 712.0),
            ),
        )

        match = find_spatial_budget_allocation(blocks)

        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.relation, "right")

    def test_rejects_money_date_and_identifier_values(self) -> None:
        invalid_values = (
            "1.234,56",
            "15/01/2021",
            "12.345.678/0001-90",
        )
        for value in invalid_values:
            with self.subTest(value=value):
                blocks = (
                    block(
                        "DOTAÇÃO ORÇAMENTÁRIA",
                        order=0,
                        bbox=(90.0, 700.0, 230.0, 712.0),
                    ),
                    block(
                        value,
                        order=1,
                        bbox=(92.0, 680.0, 225.0, 692.0),
                    ),
                )

                self.assertIsNone(find_spatial_budget_allocation(blocks))

    def test_rejects_blocks_without_coordinates(self) -> None:
        blocks = (
            DocumentBlock.create(
                page_number=1,
                block_order=0,
                text="DOTAÇÃO ORÇAMENTÁRIA",
            ),
            block(
                "02.05.04.122.001.2001",
                order=1,
                bbox=(92.0, 680.0, 225.0, 692.0),
            ),
        )

        self.assertIsNone(find_spatial_budget_allocation(blocks))

    def test_enriches_only_single_incomplete_candidate_on_page(self) -> None:
        candidate = TcmBaCommitmentCandidate(
            page_number=1,
            commitment_number="45/2021",
            issue_date="2021-01-20",
            creditor_name="EMPRESA EXEMPLO LTDA",
            amount_text="2.000,00",
            budget_allocation=None,
            missing_fields=("budget_allocation",),
            evidence_excerpt="NOTA DE EMPENHO Nº 45/2021",
        )
        layout = PdfLayoutPage(
            page_number=1,
            blocks=(
                block(
                    "DOTAÇÃO ORÇAMENTÁRIA",
                    order=0,
                    bbox=(90.0, 700.0, 230.0, 712.0),
                ),
                block(
                    "02.05.04.122.001.2001",
                    order=1,
                    bbox=(92.0, 680.0, 225.0, 692.0),
                ),
            ),
            extraction_method="embedded_layout",
        )

        enriched = apply_spatial_budget_allocations((candidate,), (layout,))

        self.assertEqual(enriched[0].budget_allocation, "02.05.04.122.001.2001")
        self.assertEqual(enriched[0].missing_fields, ())
        self.assertIsNotNone(enriched[0].budget_allocation_evidence)
        payload = commitment_candidate_payload(
            enriched[0],
            TextArtifact("artifact-id", "b" * 64, "private.pdf"),
        )
        self.assertEqual(
            payload["budget_allocation_evidence"],
            {
                "parser_version": "gazette-pdf-layout/1.0.0",
                "page_number": 1,
                "label_block_order": 0,
                "value_block_order": 1,
                "relation": "below",
            },
        )

    def test_does_not_assign_one_cell_to_two_notes_on_same_page(self) -> None:
        candidate = TcmBaCommitmentCandidate(
            page_number=1,
            commitment_number="45/2021",
            issue_date="2021-01-20",
            creditor_name="EMPRESA EXEMPLO LTDA",
            amount_text="2.000,00",
            budget_allocation=None,
            missing_fields=("budget_allocation",),
            evidence_excerpt="NOTA DE EMPENHO Nº 45/2021",
        )
        second = TcmBaCommitmentCandidate(
            page_number=1,
            commitment_number="46/2021",
            issue_date="2021-01-20",
            creditor_name="OUTRA EMPRESA LTDA",
            amount_text="3.000,00",
            budget_allocation=None,
            missing_fields=("budget_allocation",),
            evidence_excerpt="NOTA DE EMPENHO Nº 46/2021",
        )
        layout = PdfLayoutPage(
            page_number=1,
            blocks=(
                block(
                    "DOTAÇÃO ORÇAMENTÁRIA",
                    order=0,
                    bbox=(90.0, 700.0, 230.0, 712.0),
                ),
                block(
                    "02.05.04.122.001.2001",
                    order=1,
                    bbox=(92.0, 680.0, 225.0, 692.0),
                ),
            ),
            extraction_method="embedded_layout",
        )

        enriched = apply_spatial_budget_allocations((candidate, second), (layout,))

        self.assertEqual(enriched, (candidate, second))


if __name__ == "__main__":
    unittest.main()
