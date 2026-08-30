from __future__ import annotations

import unittest

from barreiras_docproc.gazette_documents import DocumentBlock
from barreiras_docproc.pdf_layout import PdfLayoutPage
from barreiras_docproc.processing import TextArtifact
from barreiras_docproc.tcm_ba_commitment_layout import (
    find_spatial_amount_text,
    find_spatial_issue_date,
)
from barreiras_docproc.tcm_ba_commitments import (
    TcmBaCommitmentCandidate,
    apply_spatial_scalar_fields,
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


def layout(*blocks: DocumentBlock) -> PdfLayoutPage:
    return PdfLayoutPage(
        page_number=1,
        blocks=blocks,
        extraction_method="embedded_layout",
    )


def incomplete_candidate() -> TcmBaCommitmentCandidate:
    return TcmBaCommitmentCandidate(
        page_number=1,
        commitment_number="45/2021",
        issue_date=None,
        creditor_name="EMPRESA EXEMPLO LTDA",
        amount_text=None,
        budget_allocation="02.05.04.122.001.2001",
        missing_fields=("issue_date", "amount_text"),
        evidence_excerpt="NOTA DE EMPENHO Nº 45/2021",
    )


class TcmBaCommitmentScalarLayoutTests(unittest.TestCase):
    def test_finds_valid_date_below_unique_official_label(self) -> None:
        match = find_spatial_issue_date(
            (
                block(
                    "DATA DO EMPENHO",
                    order=0,
                    bbox=(90.0, 700.0, 210.0, 712.0),
                ),
                block(
                    "31/01/2021",
                    order=1,
                    bbox=(92.0, 680.0, 175.0, 692.0),
                ),
            )
        )

        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.value, "2021-01-31")
        self.assertEqual(match.relation, "below")

    def test_rejects_invalid_calendar_date(self) -> None:
        self.assertIsNone(
            find_spatial_issue_date(
                (
                    block(
                        "DATA DE EMISSÃO",
                        order=0,
                        bbox=(90.0, 700.0, 210.0, 712.0),
                    ),
                    block(
                        "31/02/2021",
                        order=1,
                        bbox=(92.0, 680.0, 175.0, 692.0),
                    ),
                )
            )
        )

    def test_finds_signed_amount_to_the_right_and_removes_currency_prefix(self) -> None:
        match = find_spatial_amount_text(
            (
                block(
                    "VALOR BRUTO",
                    order=0,
                    bbox=(80.0, 700.0, 165.0, 712.0),
                ),
                block(
                    "R$ -1.234,56",
                    order=1,
                    bbox=(175.0, 700.0, 260.0, 712.0),
                ),
            )
        )

        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.value, "-1.234,56")
        self.assertEqual(match.relation, "right")

    def test_rejects_two_amount_labels_on_same_page(self) -> None:
        self.assertIsNone(
            find_spatial_amount_text(
                (
                    block(
                        "VALOR BRUTO",
                        order=0,
                        bbox=(80.0, 700.0, 165.0, 712.0),
                    ),
                    block(
                        "1.234,56",
                        order=1,
                        bbox=(82.0, 680.0, 145.0, 692.0),
                    ),
                    block(
                        "VALOR DO EMPENHO",
                        order=2,
                        bbox=(300.0, 700.0, 430.0, 712.0),
                    ),
                )
            )
        )

    def test_rejects_amount_without_clear_geometric_winner(self) -> None:
        self.assertIsNone(
            find_spatial_amount_text(
                (
                    block(
                        "VALOR BRUTO",
                        order=0,
                        bbox=(200.0, 700.0, 300.0, 712.0),
                    ),
                    block(
                        "1.234,56",
                        order=1,
                        bbox=(202.0, 680.0, 270.0, 692.0),
                    ),
                    block(
                        "9.876,54",
                        order=2,
                        bbox=(202.0, 676.0, 270.0, 688.0),
                    ),
                )
            )
        )

    def test_enriches_single_candidate_and_records_field_evidence(self) -> None:
        enriched = apply_spatial_scalar_fields(
            (incomplete_candidate(),),
            (
                layout(
                    block(
                        "DATA DO EMPENHO",
                        order=0,
                        bbox=(90.0, 700.0, 210.0, 712.0),
                    ),
                    block(
                        "31/01/2021",
                        order=1,
                        bbox=(92.0, 680.0, 175.0, 692.0),
                    ),
                    block(
                        "VALOR BRUTO",
                        order=2,
                        bbox=(300.0, 700.0, 385.0, 712.0),
                    ),
                    block(
                        "1.234,56",
                        order=3,
                        bbox=(302.0, 680.0, 370.0, 692.0),
                    ),
                ),
            ),
        )

        candidate = enriched[0]
        self.assertEqual(candidate.issue_date, "2021-01-31")
        self.assertEqual(candidate.amount_text, "1.234,56")
        self.assertEqual(candidate.missing_fields, ())
        payload = commitment_candidate_payload(
            candidate,
            TextArtifact("artifact-id", "b" * 64, "private.pdf"),
        )
        self.assertEqual(payload["schema_version"], "1.2.0")
        self.assertEqual(
            payload["issue_date_evidence"]["value_block_order"],
            1,
        )
        self.assertEqual(
            payload["amount_text_evidence"]["value_block_order"],
            3,
        )

    def test_does_not_enrich_two_candidates_on_same_page(self) -> None:
        first = incomplete_candidate()
        second = TcmBaCommitmentCandidate(
            **(first.__dict__ | {"commitment_number": "46/2021"}),
        )
        page_layout = layout(
            block(
                "DATA DO EMPENHO",
                order=0,
                bbox=(90.0, 700.0, 210.0, 712.0),
            ),
            block(
                "31/01/2021",
                order=1,
                bbox=(92.0, 680.0, 175.0, 692.0),
            ),
        )

        self.assertEqual(
            apply_spatial_scalar_fields((first, second), (page_layout,)),
            (first, second),
        )


if __name__ == "__main__":
    unittest.main()
