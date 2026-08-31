from __future__ import annotations

import json
import unittest

from barreiras_docproc.commands.benchmark_tcm_ba_commitment_dates import (
    benchmark_exit_code,
)
from barreiras_docproc.gazette_documents import DocumentBlock
from barreiras_docproc.pdf_layout import PdfLayoutPage
from barreiras_docproc.processing import TextArtifact
from barreiras_docproc.tcm_ba_commitment_date_diagnostic import (
    TcmBaIssueDateLayoutTarget,
    benchmark_issue_date_layout,
    benchmark_payload,
)
from barreiras_docproc.tcm_ba_commitment_layout import (
    diagnose_spatial_issue_date,
    diagnostic_issue_date_context_patterns,
    find_spatial_issue_date,
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


class TcmBaCommitmentDateDiagnosticTests(unittest.TestCase):
    def test_accounts_for_safe_labels_and_unlabelled_date_shapes(self) -> None:
        artifact = TextArtifact("artifact-id", "a" * 64, "private.pdf")
        target = TcmBaIssueDateLayoutTarget(
            artifact=artifact,
            candidate_page_counts=((1, 1), (2, 1), (3, 2)),
        )
        layouts = (
            PdfLayoutPage(
                1,
                (
                    block("DATA EMPENHO", order=0, bbox=(80, 700, 180, 712)),
                    block("31/01/2021", order=1, bbox=(82, 680, 165, 692)),
                ),
                "embedded_layout",
            ),
            PdfLayoutPage(
                2,
                (block("30/01/2021", order=0, bbox=(82, 680, 165, 692)),),
                "embedded_layout",
            ),
            PdfLayoutPage(3, (), "embedded_layout"),
        )

        result = benchmark_issue_date_layout(
            (target,),
            layout_loader=lambda _artifact: layouts,
        )
        payload = benchmark_payload(result)
        serialized = json.dumps(payload)

        self.assertEqual(result.missing_candidates, 4)
        self.assertEqual(result.matched_candidates, 1)
        self.assertEqual(result.sole_unlabelled_date_candidates, 1)
        self.assertEqual(result.multiple_candidate_page_candidates, 2)
        self.assertEqual(dict(result.label_kind_counts), {"commitment_date": 1})
        self.assertTrue(result.complete)
        self.assertEqual(benchmark_exit_code(result, expected_candidates=4), 0)
        self.assertEqual(benchmark_exit_code(result, expected_candidates=5), 1)
        self.assertNotIn("31/01/2021", serialized)
        self.assertNotIn(artifact.sha256, serialized)
        self.assertNotIn(artifact.object_key, serialized)

    def test_context_patterns_contain_only_safe_categories(self) -> None:
        blocks = (
            block("EMPENHO", order=0, bbox=(20, 700, 75, 712)),
            block("DATA", order=1, bbox=(80, 700, 130, 712)),
            block("31/01/2021", order=2, bbox=(82, 680, 165, 692)),
        )

        patterns = diagnostic_issue_date_context_patterns(blocks)

        self.assertEqual(patterns, ("COMMITMENT>DATA_LABEL>UNKNOWN_DATE",))
        self.assertNotIn("31/01/2021", json.dumps(patterns))
    def test_generic_data_label_is_diagnostic_only(self) -> None:
        blocks = (
            block("DATA", order=0, bbox=(80, 700, 130, 712)),
            block("31/01/2021", order=1, bbox=(82, 680, 165, 692)),
        )

        diagnosis = diagnose_spatial_issue_date(blocks)

        self.assertEqual(diagnosis.status, "matched")
        self.assertEqual(diagnosis.label_kind, "generic_date")
        self.assertIsNone(find_spatial_issue_date(blocks))
    def test_separates_missing_and_ambiguous_date_values(self) -> None:
        artifact = TextArtifact("artifact-id", "b" * 64, "private.pdf")
        target = TcmBaIssueDateLayoutTarget(
            artifact=artifact,
            candidate_page_counts=((1, 1), (2, 1)),
        )
        layouts = (
            PdfLayoutPage(1, (), "embedded_layout"),
            PdfLayoutPage(
                2,
                (
                    DocumentBlock.create(
                        page_number=2,
                        block_order=0,
                        text="01/01/2021",
                        bbox=(80, 700, 160, 712),
                    ),
                    DocumentBlock.create(
                        page_number=2,
                        block_order=1,
                        text="02/01/2021",
                        bbox=(80, 680, 160, 692),
                    ),
                ),
                "embedded_layout",
            ),
        )

        result = benchmark_issue_date_layout(
            (target,),
            layout_loader=lambda _artifact: layouts,
        )

        self.assertEqual(result.no_date_candidates, 1)
        self.assertEqual(result.multiple_unlabelled_date_candidates, 1)
        self.assertTrue(result.complete)

    def test_counts_inline_labels_and_embedded_formats(self) -> None:
        artifact = TextArtifact("artifact-id", "c" * 64, "private.pdf")
        target = TcmBaIssueDateLayoutTarget(
            artifact=artifact,
            candidate_page_counts=((1, 1), (2, 1), (3, 1)),
        )
        layouts = (
            PdfLayoutPage(
                1,
                (
                    DocumentBlock.create(
                        page_number=1,
                        block_order=0,
                        text="DATA EMPENHO: 31/01/2021",
                        bbox=(80, 700, 260, 712),
                    ),
                ),
                "embedded_layout",
            ),
            PdfLayoutPage(
                2,
                (
                    DocumentBlock.create(
                        page_number=2,
                        block_order=0,
                        text="DOCUMENTO EMITIDO EM 30-01-2021",
                        bbox=(80, 700, 300, 712),
                    ),
                ),
                "embedded_layout",
            ),
            PdfLayoutPage(
                3,
                (
                    DocumentBlock.create(
                        page_number=3,
                        block_order=0,
                        text="REFERÊNCIA 2021-01-29",
                        bbox=(80, 700, 260, 712),
                    ),
                ),
                "embedded_layout",
            ),
        )

        result = benchmark_issue_date_layout(
            (target,),
            layout_loader=lambda _artifact: layouts,
        )
        payload = benchmark_payload(result)
        serialized = json.dumps(payload)

        self.assertEqual(result.inline_labeled_date_candidates, 1)
        self.assertEqual(result.sole_unlabelled_date_candidates, 2)
        self.assertEqual(
            dict(result.date_format_counts),
            {"dmy_dash": 1, "dmy_slash": 1, "iso": 1},
        )
        self.assertEqual(dict(result.label_kind_counts), {"commitment_date": 1})
        self.assertEqual(
            dict(result.date_role_counts),
            {"commitment": 1, "emission": 1, "unknown": 1},
        )
        self.assertEqual(
            dict(result.direct_date_role_counts),
            {"commitment": 1, "emission": 1, "unknown": 1},
        )
        self.assertEqual(result.single_explicit_issue_date_candidates, 1)
        self.assertEqual(result.no_explicit_issue_date_candidates, 2)
        self.assertEqual(result.repeated_consensus_explicit_issue_date_candidates, 0)
        self.assertEqual(result.conflicting_explicit_issue_date_candidates, 0)
        self.assertNotIn("31/01/2021", serialized)
        self.assertNotIn("30-01-2021", serialized)
        self.assertNotIn("2021-01-29", serialized)

    def test_counts_repeated_consensus_and_conflicts_without_exposing_dates(
        self,
    ) -> None:
        artifact = TextArtifact("artifact-id", "d" * 64, "private.pdf")
        target = TcmBaIssueDateLayoutTarget(
            artifact=artifact,
            candidate_page_counts=((1, 1), (2, 1)),
        )
        layouts = (
            PdfLayoutPage(
                1,
                (
                    block("DATA EMPENHO: 31/01/2021", order=0, bbox=(1, 1, 2, 2)),
                    block("EMISSÃO: 31/01/2021", order=1, bbox=(1, 2, 2, 3)),
                ),
                "embedded_layout",
            ),
            PdfLayoutPage(
                2,
                (
                    DocumentBlock.create(
                        page_number=2,
                        block_order=0,
                        text="DATA EMPENHO: 30/01/2021",
                        bbox=(1, 1, 2, 2),
                    ),
                    DocumentBlock.create(
                        page_number=2,
                        block_order=1,
                        text="EMISSÃO: 29/01/2021",
                        bbox=(1, 2, 2, 3),
                    ),
                ),
                "embedded_layout",
            ),
        )

        result = benchmark_issue_date_layout(
            (target,),
            layout_loader=lambda _artifact: layouts,
        )
        serialized = json.dumps(benchmark_payload(result))

        self.assertEqual(result.repeated_consensus_explicit_issue_date_candidates, 1)
        self.assertEqual(result.conflicting_explicit_issue_date_candidates, 1)
        self.assertNotIn("31/01/2021", serialized)
        self.assertNotIn("30/01/2021", serialized)
        self.assertNotIn("29/01/2021", serialized)


if __name__ == "__main__":
    unittest.main()