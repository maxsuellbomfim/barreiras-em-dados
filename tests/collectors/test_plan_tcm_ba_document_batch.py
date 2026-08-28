from __future__ import annotations

import io
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

    def test_refuses_missing_database_url(self) -> None:
        with patch.dict(os.environ, {"DATABASE_URL": ""}):
            with self.assertRaisesRegex(RuntimeError, "exige DATABASE_URL"):
                plan_tcm_ba_document_batch.main([])


if __name__ == "__main__":
    unittest.main()
