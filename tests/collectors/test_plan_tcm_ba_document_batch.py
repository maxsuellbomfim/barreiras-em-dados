from __future__ import annotations

import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from barreiras_collectors.commands import plan_tcm_ba_document_batch


class PlanTcmBaDocumentBatchCommandTests(unittest.TestCase):
    def test_prints_only_the_validated_competence(self) -> None:
        repository = Mock()
        repository.next_tcm_ba_document_competence.return_value = "01/2021"
        with (
            patch.dict(os.environ, {"DATABASE_URL": "postgresql://db.example.invalid/test"}),
            patch.object(
                plan_tcm_ba_document_batch.PostgresCollectionRepository,
                "from_dsn",
                return_value=repository,
            ) as from_dsn,
            redirect_stdout(io.StringIO()) as output,
        ):
            result = plan_tcm_ba_document_batch.main(["--year-from", "2021"])

        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(), "01/2021\n")
        from_dsn.assert_called_once_with("postgresql://db.example.invalid/test")
        repository.next_tcm_ba_document_competence.assert_called_once_with(
            year_from=2021
        )

    def test_no_eligible_competence_has_empty_stdout(self) -> None:
        repository = Mock()
        repository.next_tcm_ba_document_competence.return_value = None
        with (
            patch.dict(os.environ, {"DATABASE_URL": "postgresql://db.example.invalid/test"}),
            patch.object(
                plan_tcm_ba_document_batch.PostgresCollectionRepository,
                "from_dsn",
                return_value=repository,
            ),
            redirect_stdout(io.StringIO()) as output,
        ):
            result = plan_tcm_ba_document_batch.main([])

        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(), "")

    def test_report_exposes_progress_and_keeps_competence_line(self) -> None:
        repository = Mock()
        repository.next_tcm_ba_document_competence.return_value = "01/2021"
        repository.tcm_ba_document_references.return_value = Mock(
            competence="01/2021",
            expected_total_documents=1441,
            preserved_documents=17,
            pending_documents=1424,
        )
        with (
            patch.dict(os.environ, {"DATABASE_URL": "postgresql://db.example.invalid/test"}),
            patch.object(
                plan_tcm_ba_document_batch.PostgresCollectionRepository,
                "from_dsn",
                return_value=repository,
            ),
            redirect_stdout(io.StringIO()) as output,
        ):
            result = plan_tcm_ba_document_batch.main(
                ["--year-from", "2021", "--report"]
            )

        self.assertEqual(result, 0)
        lines = output.getvalue().splitlines()
        self.assertEqual(lines[-1], "01/2021")
        self.assertEqual(
            json.loads(lines[0]),
            {
                "event": "tcm_ba_document_plan",
                "competence": "01/2021",
                "expected_documents": 1441,
                "preserved_documents": 17,
                "remaining_documents": 1424,
                "coverage_status": "partial",
            },
        )
        repository.tcm_ba_document_references.assert_called_once_with(
            competence="01/2021", limit=1
        )

    def test_report_marks_complete_without_inventing_competence(self) -> None:
        repository = Mock()
        repository.next_tcm_ba_document_competence.return_value = None
        with (
            patch.dict(os.environ, {"DATABASE_URL": "postgresql://db.example.invalid/test"}),
            patch.object(
                plan_tcm_ba_document_batch.PostgresCollectionRepository,
                "from_dsn",
                return_value=repository,
            ),
            redirect_stdout(io.StringIO()) as output,
        ):
            result = plan_tcm_ba_document_batch.main(["--report"])

        self.assertEqual(result, 0)
        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "event": "tcm_ba_document_plan",
                "competence": None,
                "coverage_status": "complete",
            },
        )
        repository.tcm_ba_document_references.assert_not_called()

    def test_refuses_missing_database_url(self) -> None:
        with patch.dict(os.environ, {"DATABASE_URL": ""}):
            with self.assertRaisesRegex(RuntimeError, "exige DATABASE_URL"):
                plan_tcm_ba_document_batch.main([])


if __name__ == "__main__":
    unittest.main()
