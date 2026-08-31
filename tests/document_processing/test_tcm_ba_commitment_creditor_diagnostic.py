from __future__ import annotations

import json
import logging
import unittest

from barreiras_docproc.commands.benchmark_tcm_ba_commitment_creditors import (
    benchmark_exit_code,
)
from barreiras_docproc.gazette_documents import DocumentBlock
from barreiras_docproc.pdf_layout import PdfLayoutPage
from barreiras_docproc.private_logging import configure_private_logging
from barreiras_docproc.processing import TextArtifact
from barreiras_docproc.tcm_ba_commitment_creditor_diagnostic import (
    TcmBaCreditorLayoutTarget,
    benchmark_creditor_layout,
    benchmark_payload,
)
from barreiras_docproc.tcm_ba_commitment_layout import (
    diagnose_spatial_creditor,
)
from barreiras_docproc.tcm_ba_commitments import (
    TcmBaCommitmentCandidate,
    apply_spatial_creditor_names,
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


def page(*blocks: DocumentBlock) -> PdfLayoutPage:
    return PdfLayoutPage(
        page_number=1,
        blocks=blocks,
        extraction_method="embedded_layout",
    )


class TcmBaCommitmentCreditorDiagnosticTests(unittest.TestCase):
    def test_private_logging_suppresses_http_object_paths(self) -> None:
        configure_private_logging("INFO")

        self.assertGreaterEqual(logging.getLogger("httpx").level, logging.WARNING)

    def test_matches_unique_creditor_without_exposing_document_suffix(self) -> None:
        diagnosis = diagnose_spatial_creditor(
            (
                block("CREDOR", order=0, bbox=(80.0, 700.0, 145.0, 712.0)),
                block(
                    "EMPRESA EXEMPLO LTDA - CNPJ 12.345.678/0001-90",
                    order=1,
                    bbox=(82.0, 680.0, 390.0, 692.0),
                ),
            )
        )

        self.assertEqual(diagnosis.status, "matched")
        self.assertEqual(diagnosis.label_kind, "creditor")
        self.assertIsNotNone(diagnosis.match)
        assert diagnosis.match is not None
        self.assertEqual(diagnosis.match.value, "EMPRESA EXEMPLO LTDA")

    def test_rejects_multiple_labels_and_ambiguous_values(self) -> None:
        multiple = diagnose_spatial_creditor(
            (
                block("CREDOR", order=0, bbox=(80.0, 700.0, 145.0, 712.0)),
                block(
                    "FAVORECIDO",
                    order=1,
                    bbox=(300.0, 700.0, 390.0, 712.0),
                ),
            )
        )
        ambiguous = diagnose_spatial_creditor(
            (
                block("BENEFICIÁRIO", order=0, bbox=(80.0, 700.0, 170.0, 712.0)),
                block("PESSOA UM", order=1, bbox=(82.0, 680.0, 170.0, 692.0)),
                block("PESSOA DOIS", order=2, bbox=(82.0, 676.0, 180.0, 688.0)),
            )
        )

        self.assertEqual(multiple.status, "multiple_labels")
        self.assertEqual(ambiguous.status, "ambiguous_values")
        self.assertIsNone(multiple.match)
        self.assertIsNone(ambiguous.match)

    def test_benchmark_reconciles_candidates_and_payload_is_aggregate(self) -> None:
        artifact = TextArtifact(
            raw_artifact_id="00000000-0000-0000-0000-000000000001",
            sha256="a" * 64,
            object_key="private/commitment.pdf",
        )
        target = TcmBaCreditorLayoutTarget(
            artifact=artifact,
            candidate_page_counts=((1, 1), (2, 2), (3, 1)),
        )
        layouts = (
            page(
                block("CREDOR", order=0, bbox=(80.0, 700.0, 145.0, 712.0)),
                block(
                    "EMPRESA EXEMPLO LTDA",
                    order=1,
                    bbox=(82.0, 680.0, 240.0, 692.0),
                ),
            ),
            PdfLayoutPage(2, (), "pending_ocr"),
            PdfLayoutPage(3, (), "embedded_layout"),
        )

        result = benchmark_creditor_layout(
            (target,),
            layout_loader=lambda _artifact: layouts,
        )
        payload = benchmark_payload(result)
        serialized = json.dumps(payload)

        self.assertEqual(result.missing_candidates, 4)
        self.assertEqual(result.matched_candidates, 1)
        self.assertEqual(result.multiple_candidate_page_candidates, 2)
        self.assertEqual(result.no_label_candidates, 1)
        self.assertTrue(result.complete)
        self.assertNotIn("EMPRESA EXEMPLO", serialized)
        self.assertNotIn(artifact.sha256, serialized)
        self.assertNotIn(artifact.object_key, serialized)
        self.assertEqual(benchmark_exit_code(result, expected_candidates=4), 0)
        self.assertEqual(benchmark_exit_code(result, expected_candidates=5), 1)

    def test_applies_matched_creditor_and_records_spatial_evidence(self) -> None:
        candidate = TcmBaCommitmentCandidate(
            page_number=1,
            commitment_number="45/2021",
            issue_date="2021-01-31",
            creditor_name=None,
            amount_text="1.234,56",
            budget_allocation="02.05.04.122.001.2001",
            missing_fields=("creditor_name",),
            evidence_excerpt="NOTA DE EMPENHO Nº 45/2021",
        )
        enriched = apply_spatial_creditor_names(
            (candidate,),
            (
                page(
                    block("CREDOR", order=0, bbox=(80.0, 700.0, 145.0, 712.0)),
                    block(
                        "EMPRESA EXEMPLO LTDA",
                        order=1,
                        bbox=(82.0, 680.0, 250.0, 692.0),
                    ),
                ),
            ),
        )[0]

        self.assertEqual(enriched.creditor_name, "EMPRESA EXEMPLO LTDA")
        self.assertEqual(enriched.missing_fields, ())
        payload = commitment_candidate_payload(
            enriched,
            TextArtifact("artifact-id", "b" * 64, "private.pdf"),
        )
        self.assertEqual(payload["schema_version"], "1.5.0")
        self.assertEqual(payload["creditor_name_evidence"]["value_block_order"], 1)


if __name__ == "__main__":
    unittest.main()
