from __future__ import annotations

import unittest

from barreiras_docproc.processing import PageInput, ProcessingError, TextArtifact
from barreiras_docproc.tcm_ba_commitment_repository import (
    TcmBaCommitmentExtractionRepository,
)
from barreiras_docproc.tcm_ba_commitments import (
    EXTRACTOR_VERSION,
    TcmBaCommitmentBatch,
    TcmBaCommitmentExtractionService,
)


class Cursor:
    def __init__(self, *, rows=(), row=None) -> None:
        self.rows = list(rows)
        self.row = row

    def fetchall(self):
        rows = list(self.rows)
        self.rows.clear()
        return rows

    def fetchone(self):
        return self.row


class Transaction:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class RecordingConnection:
    def __init__(self) -> None:
        self.queries: list[tuple[str, object]] = []
        self.pending_rows = []
        self.job_row = {"id": "00000000-0000-0000-0000-000000000905"}

    def execute(self, query, params=None):
        normalized = " ".join(query.split())
        self.queries.append((normalized, params))
        if "with tcm_artifacts as" in normalized:
            return Cursor(rows=self.pending_rows)
        if "insert into raw.extraction_jobs" in normalized:
            return Cursor(row=self.job_row)
        return Cursor()

    def transaction(self):
        return Transaction()

    def close(self):
        return None


def batch() -> TcmBaCommitmentBatch:
    source = TextArtifact(
        raw_artifact_id="00000000-0000-0000-0000-000000000902",
        sha256="b" * 64,
        object_key=(f"tcm-ba/monthly-documents/2021/01/pdf/sha256/bb/{'b' * 64}.pdf"),
    )
    page = PageInput(
        page_number=3,
        parser_version="pypdf/fixture",
        text=(
            "NOTA DE EMPENHO Nº 45/2021\n"
            "Emissão: 20/01/2021\n"
            "Credor: PESSOA EXEMPLO - CPF 123.456.789-09\n"
            "Valor: R$ 2.000,00\n"
            "Dotação: 02.05.123.456\n"
        ),
        sha256="c" * 64,
    )
    repository = _BatchCaptureRepository()
    TcmBaCommitmentExtractionService(repository=repository).process(
        source,
        (page,),
    )
    return repository.batch


class _BatchCaptureRepository:
    def persist_tcm_ba_commitment_candidates(self, candidate_batch):
        self.batch = candidate_batch
        from barreiras_docproc.tcm_ba_commitments import (
            TcmBaCommitmentPersistResult,
        )

        return TcmBaCommitmentPersistResult(True, 1)


class TcmBaCommitmentRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = RecordingConnection()
        self.repository = TcmBaCommitmentExtractionRepository(
            lambda: self.connection  # type: ignore[arg-type]
        )

    def test_pending_page_sets_group_canonical_pages_by_artifact(self) -> None:
        self.connection.pending_rows = [
            {
                "artifact_id": "00000000-0000-0000-0000-000000000902",
                "sha256": "b" * 64,
                "object_key": "tcm-ba/monthly-documents/2021/01/a.pdf",
                "page_number": 1,
                "parser_version": "pypdf/6.14.2",
                "extraction_method": "embedded_text",
                "text_content": "CONTRATO 1/2021",
                "text_sha256": "c" * 64,
            },
            {
                "artifact_id": "00000000-0000-0000-0000-000000000902",
                "sha256": "b" * 64,
                "object_key": "tcm-ba/monthly-documents/2021/01/a.pdf",
                "page_number": 2,
                "parser_version": "tcm-ba-ocr/1.0.0",
                "extraction_method": "ocr",
                "text_content": "NOTA DE EMPENHO Nº 1/2021",
                "text_sha256": "d" * 64,
            },
        ]

        page_sets = self.repository.pending_page_sets(5)

        self.assertEqual(len(page_sets), 1)
        self.assertEqual(page_sets[0].artifact.sha256, "b" * 64)
        self.assertEqual([page.page_number for page in page_sets[0].pages], [1, 2])
        self.assertEqual(page_sets[0].pages[1].extraction_method, "ocr")

    def test_persists_candidates_only_as_private_review_results(self) -> None:
        result = self.repository.persist_tcm_ba_commitment_candidates(batch())

        self.assertTrue(result.job_created)
        self.assertEqual(result.results_inserted, 1)
        result_query, params = next(
            (query, params)
            for query, params in self.connection.queries
            if "insert into raw.extraction_results" in query
        )
        self.assertIn("'needs_review'", result_query)
        self.assertNotIn("finance.commitments", result_query)
        assert params is not None
        self.assertEqual(params[1], EXTRACTOR_VERSION)
        self.assertNotIn("123.456.789-09", str(params))

    def test_rejects_page_without_verified_text_hash(self) -> None:
        self.connection.pending_rows = [
            {
                "artifact_id": "00000000-0000-0000-0000-000000000902",
                "sha256": "b" * 64,
                "object_key": "tcm-ba/monthly-documents/2021/01/a.pdf",
                "page_number": 1,
                "parser_version": "pypdf/6.14.2",
                "extraction_method": "embedded_text",
                "text_content": "NOTA DE EMPENHO Nº 1/2021",
                "text_sha256": None,
            }
        ]

        with self.assertRaisesRegex(ProcessingError, "hash"):
            self.repository.pending_page_sets(5)

    def test_existing_succeeded_job_does_not_duplicate_candidates(self) -> None:
        self.connection.job_row = None

        result = self.repository.persist_tcm_ba_commitment_candidates(batch())

        self.assertFalse(result.job_created)
        self.assertEqual(result.results_inserted, 0)
        self.assertFalse(
            any(
                "insert into raw.extraction_results" in query
                for query, _params in self.connection.queries
            )
        )

    def test_failures_are_bounded_and_move_to_dead_letter(self) -> None:
        self.repository.persist_failure(
            batch().artifact,
            idempotency_key="e" * 64,
            error_code="processing_error",
            error_detail="RuntimeError: processing failure",
        )

        query = next(
            query
            for query, _params in self.connection.queries
            if "insert into raw.extraction_jobs" in query
        )
        self.assertIn("then 'dead_lettered'", query)
        self.assertIn(
            "attempt_count + 1 >= raw.extraction_jobs.max_attempts",
            query,
        )


if __name__ == "__main__":
    unittest.main()
