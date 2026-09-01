from __future__ import annotations

import unittest
from unittest.mock import patch

from barreiras_docproc.commands.report_tcm_ba_document_lineage import main
from barreiras_docproc.tcm_ba_document_families import TcmBaDocumentLineage


class Repository:
    def __init__(self, rows: tuple[TcmBaDocumentLineage, ...]) -> None:
        self.rows = rows
        self.requested_sha256: str | None = None

    def document_lineage_by_sha256(
        self, artifact_sha256: str
    ) -> tuple[TcmBaDocumentLineage, ...]:
        self.requested_sha256 = artifact_sha256
        return self.rows


class ReportTcmBaDocumentLineageCommandTests(unittest.TestCase):
    def test_emits_exact_official_lineage_without_document_content(self) -> None:
        artifact_sha256 = "f" * 64
        repository = Repository(
            (
                TcmBaDocumentLineage(
                    artifact_id="00000000-0000-0000-0000-000000000904",
                    artifact_sha256=artifact_sha256,
                    object_key="tcm-ba/monthly-documents/2023/04/f.pdf",
                    source_record_key="tcm-ba:document:04/2023:expense",
                    competence="04/2023",
                    official_category="PCMGE015 - Demonstrativo analítico",
                    official_category_code="PCMGE015",
                    family="analytical_budget_expense_statement",
                    document_name="Demonstrativo da despesa",
                ),
            )
        )

        with patch(
            "barreiras_docproc.commands.report_tcm_ba_document_lineage.log_event"
        ) as log_event:
            exit_code = main(
                ["--sha256", artifact_sha256],
                repository=repository,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(repository.requested_sha256, artifact_sha256)
        fields = log_event.call_args.kwargs
        self.assertEqual(fields["competence"], "04/2023")
        self.assertEqual(fields["official_category_code"], "PCMGE015")
        self.assertEqual(fields["matches"], 1)

    def test_missing_hash_is_a_blocking_result(self) -> None:
        repository = Repository(())

        with patch(
            "barreiras_docproc.commands.report_tcm_ba_document_lineage.log_event"
        ) as log_event:
            exit_code = main(["--sha256", "a" * 64], repository=repository)

        self.assertEqual(exit_code, 1)
        self.assertEqual(log_event.call_args.kwargs["gate"], "BLOCK")


if __name__ == "__main__":
    unittest.main()
