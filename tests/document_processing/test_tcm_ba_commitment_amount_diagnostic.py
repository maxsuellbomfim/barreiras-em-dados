from __future__ import annotations

import json
import unittest

from barreiras_docproc.commands.benchmark_tcm_ba_commitment_amounts import (
    benchmark_exit_code,
)
from barreiras_docproc.gazette_documents import DocumentBlock
from barreiras_docproc.pdf_layout import PdfLayoutPage
from barreiras_docproc.processing import TextArtifact
from barreiras_docproc.tcm_ba_commitment_amount_diagnostic import (
    TcmBaAmountLayoutTarget,
    benchmark_amount_layout,
    benchmark_payload,
)


def block(
    text: str,
    *,
    page: int,
    order: int,
    bbox: tuple[float, float, float, float],
) -> DocumentBlock:
    return DocumentBlock.create(
        page_number=page,
        block_order=order,
        text=text,
        bbox=bbox,
    )


class TcmBaCommitmentAmountDiagnosticTests(unittest.TestCase):
    def test_accounts_for_every_candidate_without_exposing_values(self) -> None:
        artifact = TextArtifact("artifact-id", "a" * 64, "private.pdf")
        target = TcmBaAmountLayoutTarget(
            artifact=artifact,
            candidate_page_counts=((1, 1), (2, 1), (3, 2)),
        )
        layouts = (
            PdfLayoutPage(
                1,
                (
                    block(
                        "VALOR BRUTO",
                        page=1,
                        order=0,
                        bbox=(90.0, 700.0, 180.0, 712.0),
                    ),
                    block(
                        "R$ 1.234,56",
                        page=1,
                        order=1,
                        bbox=(190.0, 700.0, 270.0, 712.0),
                    ),
                ),
                "embedded_layout",
            ),
            PdfLayoutPage(
                2,
                (
                    block(
                        "SEM RÓTULO 9.876,54",
                        page=2,
                        order=0,
                        bbox=(90.0, 700.0, 260.0, 712.0),
                    ),
                ),
                "embedded_layout",
            ),
            PdfLayoutPage(3, (), "embedded_layout"),
        )

        benchmark = benchmark_amount_layout(
            (target,),
            layout_loader=lambda _artifact: layouts,
        )
        serialized = json.dumps(benchmark_payload(benchmark))

        self.assertEqual(benchmark.missing_candidates, 4)
        self.assertEqual(benchmark.accounted_candidates, 4)
        self.assertEqual(benchmark.matched_candidates, 1)
        self.assertEqual(benchmark.no_label_candidates, 1)
        self.assertEqual(benchmark.multiple_candidate_page_candidates, 2)
        self.assertTrue(benchmark.complete)
        self.assertNotIn("1.234,56", serialized)
        self.assertNotIn("9.876,54", serialized)
        self.assertNotIn(artifact.sha256, serialized)
        self.assertNotIn(artifact.object_key, serialized)
        self.assertEqual(benchmark_exit_code(benchmark, expected_candidates=4), 0)
        self.assertEqual(benchmark_exit_code(benchmark, expected_candidates=5), 1)

    def test_separates_uninformed_and_ambiguous_values(self) -> None:
        artifact = TextArtifact("artifact-id", "b" * 64, "private.pdf")
        target = TcmBaAmountLayoutTarget(
            artifact=artifact,
            candidate_page_counts=((1, 1), (2, 1)),
        )
        layouts = (
            PdfLayoutPage(
                1,
                (
                    block(
                        "VALOR DO EMPENHO",
                        page=1,
                        order=0,
                        bbox=(90.0, 700.0, 220.0, 712.0),
                    ),
                    block(
                        "NÃO INFORMADO",
                        page=1,
                        order=1,
                        bbox=(230.0, 700.0, 330.0, 712.0),
                    ),
                ),
                "embedded_layout",
            ),
            PdfLayoutPage(
                2,
                (
                    block(
                        "VALOR BRUTO",
                        page=2,
                        order=0,
                        bbox=(200.0, 700.0, 300.0, 712.0),
                    ),
                    block(
                        "1.234,56",
                        page=2,
                        order=1,
                        bbox=(202.0, 680.0, 270.0, 692.0),
                    ),
                    block(
                        "9.876,54",
                        page=2,
                        order=2,
                        bbox=(202.0, 676.0, 270.0, 688.0),
                    ),
                ),
                "embedded_layout",
            ),
        )

        benchmark = benchmark_amount_layout(
            (target,),
            layout_loader=lambda _artifact: layouts,
        )

        self.assertEqual(benchmark.no_compatible_value_candidates, 1)
        self.assertEqual(benchmark.ambiguous_value_candidates, 1)
        self.assertEqual(
            dict(benchmark.label_kind_counts),
            {"commitment_amount": 1, "gross_amount": 1},
        )
        self.assertTrue(benchmark.complete)


if __name__ == "__main__":
    unittest.main()
