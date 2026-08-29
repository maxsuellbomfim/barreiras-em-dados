from __future__ import annotations

import unittest

from barreiras_docproc.processing import PageInput, ProcessingError, TextArtifact
from barreiras_docproc.tcm_ba_contract_document_repository import (
    TcmBaContractDocumentExtractionRepository,
)
from barreiras_docproc.tcm_ba_contract_documents import (
    EXTRACTOR_VERSION,
    TcmBaContractDocumentExtractionService,
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
        self.job_row = {"id": "00000000-0000-0000-0000-000000000905"}

    def execute(self, query, params=None):
        normalized = " ".join(query.split())
        self.queries.append((normalized, params))
        if "with contract_family as" in normalized:
            return Cursor(rows=self.pending_rows)
        if "with eligible as" in normalized:
            return Cursor(row=self.coverage_row)
        if "insert into raw.extraction_jobs" in normalized:
            return Cursor(row=self.job_row)
        return Cursor()

    def transaction(self):
        return Transaction()

    def close(self):
        return None


def artifact() -> TextArtifact:
    return TextArtifact(
        raw_artifact_id="00000000-0000-0000-0000-000000000902",
        sha256="b" * 64,
        object_key="tcm-ba/monthly-documents/2021/01/a.pdf",
    )


def pages() -> tuple[PageInput, ...]:
    return (
        PageInput(
            page_number=1,
            parser_version="pypdf/fixture",
            extraction_method="embedded_text",
            text="CONTRATO Nº 1/2021\nObjeto.\n",
            sha256="c" * 64,
        ),
    )


class TcmBaContractDocumentRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = RecordingConnection()
        self.repository = TcmBaContractDocumentExtractionRepository(
            lambda: self.connection  # type: ignore[arg-type]
        )

    def test_pending_sets_require_family_and_verified_pages(self) -> None:
        self.connection.pending_rows = [
            {
                "artifact_id": artifact().raw_artifact_id,
                "sha256": artifact().sha256,
                "object_key": artifact().object_key,
                "page_number": 1,
                "parser_version": "pypdf/6.14.2",
                "extraction_method": "embedded_text",
                "text_content": "CONTRATO Nº 1/2021",
                "text_sha256": "c" * 64,
            }
        ]

        page_sets = self.repository.pending_page_sets(5)

        self.assertEqual(len(page_sets), 1)
        self.assertEqual(page_sets[0].artifact.sha256, "b" * 64)
        query = self.connection.queries[0][0]
        self.assertIn("result_payload ->> 'family' = 'contracts_and_amendments'", query)
        self.assertIn("result.extractor_version = %s", query)
        self.assertIn("bool_and(page.text_sha256 is not null)", query)

    def test_page_without_verified_hash_is_rejected(self) -> None:
        self.connection.pending_rows = [
            {
                "artifact_id": artifact().raw_artifact_id,
                "sha256": artifact().sha256,
                "object_key": artifact().object_key,
                "page_number": 1,
                "parser_version": "pypdf/6.14.2",
                "extraction_method": "embedded_text",
                "text_content": "CONTRATO Nº 1/2021",
                "text_sha256": None,
            }
        ]

        with self.assertRaisesRegex(ProcessingError, "hash"):
            self.repository.pending_page_sets(5)

    def test_segments_are_private_review_results_without_raw_text(self) -> None:
        result = TcmBaContractDocumentExtractionService(
            repository=self.repository
        ).process(artifact(), pages())

        self.assertTrue(result.job_created)
        self.assertEqual(result.results_inserted, 1)
        result_query, params = next(
            (query, params)
            for query, params in self.connection.queries
            if "insert into raw.extraction_results" in query
        )
        self.assertIn("'tcm_ba_contract_document_segment'", result_query)
        self.assertIn("'needs_review'", result_query)
        self.assertNotIn("public.", result_query)
        self.assertNotIn("finance.", result_query)
        assert params is not None
        self.assertEqual(params[1], EXTRACTOR_VERSION)
        self.assertNotIn("Objeto", str(params))

    def test_existing_succeeded_job_does_not_duplicate_segments(self) -> None:
        self.connection.job_row = None

        result = TcmBaContractDocumentExtractionService(
            repository=self.repository
        ).process(artifact(), pages())

        self.assertFalse(result.job_created)
        self.assertEqual(result.results_inserted, 0)
        self.assertFalse(
            any(
                "insert into raw.extraction_results" in query
                for query, _params in self.connection.queries
            )
        )

    def test_coverage_reconciles_every_eligible_artifact(self) -> None:
        self.connection.coverage_row = {
            "eligible_artifacts": 34,
            "processed_artifacts": 34,
            "identified_segments": 700,
            "unknown_segments": 0,
            "missing_artifacts": 0,
            "unknown_only_artifacts": 0,
            "duplicate_results": 0,
            "invalid_results": 0,
            "open_failures": 0,
        }

        coverage = self.repository.contract_document_coverage()

        self.assertTrue(coverage.complete)
        query = self.connection.queries[0][0]
        self.assertIn("count(distinct eligible.raw_artifact_id)", query)
        self.assertIn("result.extractor_version = %s", query)
        self.assertIn("unknown_only_artifacts", query)
        self.assertIn("'dead_lettered'", query)
        self.assertIn("result_payload ->> 'segment_ordinal' is null", query)
        self.assertIn("result_payload ->> 'segment_text_sha256' is null", query)
        self.assertIn("result_payload ->> 'source_artifact_sha256'", query)


if __name__ == "__main__":
    unittest.main()
