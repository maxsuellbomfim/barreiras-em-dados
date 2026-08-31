from __future__ import annotations

import unittest

from barreiras_docproc.pdf_layout import PDF_LAYOUT_VERSION
from barreiras_docproc.processing import PageInput, ProcessingError, TextArtifact
from barreiras_docproc.tcm_ba_commitment_repository import (
    TcmBaCommitmentExtractionRepository,
)
from barreiras_docproc.tcm_ba_commitments import (
    EXTRACTOR_VERSION,
    JOB_TYPE,
    SCHEMA_VERSION,
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
        self.coverage_row = None
        self.breakdown_rows = []
        self.creditor_target_rows = []
        self.issue_date_target_rows = []
        self.job_row = {"id": "00000000-0000-0000-0000-000000000905"}

    def execute(self, query, params=None):
        normalized = " ".join(query.split())
        self.queries.append((normalized, params))
        if "commitment_missing_field_breakdown" in normalized:
            return Cursor(rows=self.breakdown_rows)
        if "commitment_creditor_layout_targets" in normalized:
            return Cursor(rows=self.creditor_target_rows)
        if "commitment_issue_date_layout_targets" in normalized:
            return Cursor(rows=self.issue_date_target_rows)
        if "commitment_coverage_eligible" in normalized:
            return Cursor(row=self.coverage_row)
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

    def test_coverage_reconciles_ready_artifacts_and_current_results(self) -> None:
        self.connection.coverage_row = {
            "eligible_artifacts": 10,
            "processed_artifacts": 10,
            "candidate_results": 2,
            "complete_candidates": 1,
            "incomplete_candidates": 1,
            "zero_candidate_artifacts": 8,
            "missing_artifacts": 0,
            "duplicate_results": 0,
            "invalid_results": 0,
            "open_failures": 0,
        }

        coverage = self.repository.commitment_coverage()

        self.assertTrue(coverage.complete)
        query = next(
            query
            for query, _params in self.connection.queries
            if "commitment_coverage_eligible" in query
        )
        self.assertIn("zero_candidate_artifacts", query)
        self.assertIn("jsonb_typeof", query)
        self.assertIn("coalesce(validation_status, '')", query)
        self.assertIn("schema_version", query)
        self.assertIn("is distinct from 'array'", query)

    def test_missing_field_breakdown_is_aggregate_and_version_scoped(self) -> None:
        self.connection.breakdown_rows = [
            {
                "missing_fields": [],
                "candidate_count": 4,
                "spatial_budget_count": 4,
                "spatial_issue_date_count": 1,
                "spatial_amount_count": 2,
                "spatial_creditor_count": 1,
                "invalid_spatial_count": 0,
            },
            {
                "missing_fields": ["issue_date"],
                "candidate_count": 5,
                "spatial_budget_count": 3,
                "spatial_issue_date_count": 0,
                "spatial_amount_count": 2,
                "spatial_creditor_count": 0,
                "invalid_spatial_count": 0,
            },
            {
                "missing_fields": ["budget_allocation"],
                "candidate_count": 80,
                "spatial_budget_count": 0,
                "spatial_issue_date_count": 20,
                "spatial_amount_count": 30,
                "spatial_creditor_count": 20,
                "invalid_spatial_count": 0,
            },
            {
                "missing_fields": ["creditor_name", "amount_text"],
                "candidate_count": 9,
                "spatial_budget_count": 6,
                "spatial_issue_date_count": 1,
                "spatial_amount_count": 0,
                "spatial_creditor_count": 1,
                "invalid_spatial_count": 0,
            },
        ]
        breakdown = self.repository.commitment_missing_field_breakdown()

        self.assertEqual(breakdown.total_candidates, 98)
        self.assertEqual(breakdown.complete_candidates, 4)
        self.assertEqual(breakdown.spatial_budget_allocations, 13)
        self.assertEqual(breakdown.spatial_issue_dates, 22)
        self.assertEqual(breakdown.spatial_amounts, 34)
        self.assertEqual(breakdown.spatial_creditor_names, 22)
        self.assertEqual(breakdown.invalid_spatial_evidence, 0)
        self.assertEqual(breakdown.missing_issue_date, 5)
        self.assertEqual(breakdown.missing_creditor_name, 9)
        self.assertEqual(breakdown.missing_amount_text, 9)
        self.assertEqual(breakdown.missing_budget_allocation, 80)
        self.assertEqual(
            breakdown.groups[0].missing_fields,
            ("budget_allocation",),
        )
        query, params = next(
            (query, params)
            for query, params in self.connection.queries
            if "commitment_missing_field_breakdown" in query
        )
        self.assertIn("result.extractor_version = %s", query)
        self.assertIn("result_payload ->> 'budget_allocation'", query)
        self.assertIn(
            "not in ('below', 'right', 'inline')",
            query,
        )
        self.assertEqual(
            params,
            (
                JOB_TYPE,
                EXTRACTOR_VERSION,
                EXTRACTOR_VERSION,
                PDF_LAYOUT_VERSION,
                PDF_LAYOUT_VERSION,
                PDF_LAYOUT_VERSION,
                PDF_LAYOUT_VERSION,
            ),
        )

    def test_creditor_layout_targets_are_version_scoped_and_bounded(self) -> None:
        self.connection.creditor_target_rows = [
            {
                "artifact_id": "00000000-0000-0000-0000-000000000902",
                "sha256": "b" * 64,
                "object_key": "private/a.pdf",
                "candidate_page_counts": [[1, 1], [3, 2]],
                "total_artifacts": 1,
            }
        ]

        targets = self.repository.creditor_layout_targets(limit=25)

        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0].candidate_page_counts, ((1, 1), (3, 2)))
        query, params = next(
            (query, params)
            for query, params in self.connection.queries
            if "commitment_creditor_layout_targets" in query
        )
        self.assertIn("missing_fields' ? 'creditor_name'", query)
        self.assertEqual(
            params,
            (JOB_TYPE, EXTRACTOR_VERSION, EXTRACTOR_VERSION, SCHEMA_VERSION, 25),
        )

    def test_issue_date_layout_targets_are_version_scoped_and_bounded(self) -> None:
        self.connection.issue_date_target_rows = [
            {
                "artifact_id": "00000000-0000-0000-0000-000000000902",
                "sha256": "b" * 64,
                "object_key": "private/a.pdf",
                "candidate_page_counts": [[1, 1], [3, 2]],
                "total_artifacts": 1,
            }
        ]

        targets = self.repository.issue_date_layout_targets(limit=25)

        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0].candidate_page_counts, ((1, 1), (3, 2)))
        query, params = next(
            (query, params)
            for query, params in self.connection.queries
            if "commitment_issue_date_layout_targets" in query
        )
        self.assertIn("missing_fields' ? 'issue_date'", query)
        self.assertEqual(
            params,
            (JOB_TYPE, EXTRACTOR_VERSION, EXTRACTOR_VERSION, SCHEMA_VERSION, 25),
        )
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
