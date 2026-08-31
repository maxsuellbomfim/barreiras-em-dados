from __future__ import annotations

import json
import unittest

from barreiras_docproc.commands.benchmark_tcm_ba_commitment_budgets import (
    benchmark_exit_code,
)
from barreiras_docproc.gazette_documents import DocumentBlock
from barreiras_docproc.pdf_layout import PdfLayoutPage
from barreiras_docproc.processing import TextArtifact
from barreiras_docproc.tcm_ba_commitment_budget_diagnostic import (
    TcmBaBudgetLayoutTarget,
    benchmark_budget_layout,
    benchmark_payload,
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


class TcmBaCommitmentBudgetDiagnosticTests(unittest.TestCase):
    def test_accounts_for_every_missing_candidate_without_exposing_values(self) -> None:
        artifact = TextArtifact("artifact-id", "a" * 64, "private.pdf")
        target = TcmBaBudgetLayoutTarget(
            artifact=artifact,
            candidate_page_counts=((1, 1), (2, 1), (3, 2)),
        )
        layouts = (
            PdfLayoutPage(
                1,
                (
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
                "embedded_layout",
            ),
            PdfLayoutPage(
                2,
                (
                    DocumentBlock.create(
                        page_number=2,
                        block_order=0,
                        text="SEM RÓTULO 03.06.12.361.002.2002",
                        bbox=(90.0, 700.0, 300.0, 712.0),
                    ),
                ),
                "embedded_layout",
            ),
            PdfLayoutPage(3, (), "embedded_layout"),
        )

        benchmark = benchmark_budget_layout(
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
        self.assertNotIn("02.05.04.122.001.2001", serialized)
        self.assertNotIn("03.06.12.361.002.2002", serialized)
        self.assertNotIn(artifact.sha256, serialized)
        self.assertNotIn(artifact.object_key, serialized)
        self.assertEqual(benchmark_exit_code(benchmark, expected_candidates=4), 0)
        self.assertEqual(benchmark_exit_code(benchmark, expected_candidates=5), 1)

    def test_separates_ambiguous_values_from_missing_compatible_values(self) -> None:
        artifact = TextArtifact("artifact-id", "b" * 64, "private.pdf")
        target = TcmBaBudgetLayoutTarget(
            artifact=artifact,
            candidate_page_counts=((1, 1), (2, 1)),
        )
        layouts = (
            PdfLayoutPage(
                1,
                (
                    block(
                        "DOTAÇÃO",
                        order=0,
                        bbox=(90.0, 700.0, 180.0, 712.0),
                    ),
                    block(
                        "02.05.04.122.001.2001",
                        order=1,
                        bbox=(90.0, 680.0, 220.0, 692.0),
                    ),
                    block(
                        "03.06.12.361.002.2002",
                        order=2,
                        bbox=(92.0, 680.0, 222.0, 692.0),
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
                        text="CLASSIFICAÇÃO ORÇAMENTÁRIA",
                        bbox=(90.0, 700.0, 250.0, 712.0),
                    ),
                    DocumentBlock.create(
                        page_number=2,
                        block_order=1,
                        text="SEM CÓDIGO",
                        bbox=(90.0, 680.0, 180.0, 692.0),
                    ),
                ),
                "embedded_layout",
            ),
        )

        benchmark = benchmark_budget_layout(
            (target,),
            layout_loader=lambda _artifact: layouts,
        )

        self.assertEqual(benchmark.ambiguous_value_candidates, 1)
        self.assertEqual(benchmark.no_compatible_value_candidates, 1)
        self.assertEqual(
            dict(benchmark.label_kind_counts),
            {"budget_allocation": 1, "budget_classification": 1},
        )
        self.assertTrue(benchmark.complete)

    def test_aggregates_closed_budget_context_categories_without_raw_text(self) -> None:
        artifact = TextArtifact("artifact-id", "c" * 64, "private.pdf")
        target = TcmBaBudgetLayoutTarget(
            artifact=artifact,
            candidate_page_counts=((1, 1), (2, 1), (3, 1)),
        )
        layouts = (
            PdfLayoutPage(
                1,
                (
                    block(
                        "UNIDADE ORÇAMENTÁRIA: 02.05",
                        order=0,
                        bbox=(90.0, 700.0, 250.0, 712.0),
                    ),
                    block(
                        "PROJETO / ATIVIDADE: 04.122.001.2001",
                        order=1,
                        bbox=(90.0, 680.0, 300.0, 692.0),
                    ),
                    block(
                        "ELEMENTO DE DESPESA: 3.3.90.39",
                        order=2,
                        bbox=(90.0, 660.0, 280.0, 672.0),
                    ),
                    block(
                        "FONTE DE RECURSO: 15000000",
                        order=3,
                        bbox=(90.0, 640.0, 260.0, 652.0),
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
                        text=(
                            "CLASSIFICAÇÃO ORÇAMENTÁRIA: "
                            "05.02.04.122.001.2001"
                        ),
                        bbox=(90.0, 700.0, 340.0, 712.0),
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
                        text="CLASSIFICAÇÃO ORÇAMENTÁRIA: NÃO INFORMADA",
                        bbox=(90.0, 700.0, 340.0, 712.0),
                    ),
                ),
                "embedded_layout",
            ),
        )

        benchmark = benchmark_budget_layout(
            (target,),
            layout_loader=lambda _artifact: layouts,
        )
        payload = benchmark_payload(benchmark)
        serialized = json.dumps(payload)

        self.assertEqual(
            payload["safe_context_pattern_counts"],
            {
                "BUDGET_UNIT": 1,
                "CLASSIFICATION_AND_BUDGET": 2,
                "CLASSIFICATION_BUDGET_PREFIX_COMPATIBLE_SUFFIX": 1,
                "CLASSIFICATION_BUDGET_PREFIX_NONCOMPATIBLE_SUFFIX": 1,
                "CLASSIFICATION_BUDGET_SUFFIX_NO_DIGITS": 1,
                "EXPENSE_ELEMENT": 1,
                "FUNDING_SOURCE": 1,
                "PROJECT_ACTIVITY": 1,
            },
        )
        self.assertEqual(
            payload["no_label_compatible_value_count_buckets"],
            {"multiple": 1, "single": 1, "zero": 1},
        )
        self.assertNotIn("02.05", serialized)
        self.assertNotIn("04.122.001.2001", serialized)
        self.assertNotIn("3.3.90.39", serialized)
        self.assertNotIn("15000000", serialized)
        self.assertNotIn("05.02.04.122.001.2001", serialized)
        self.assertNotIn("NÃO INFORMADA", serialized)
        self.assertNotIn(artifact.sha256, serialized)
        self.assertNotIn(artifact.object_key, serialized)


if __name__ == "__main__":
    unittest.main()
