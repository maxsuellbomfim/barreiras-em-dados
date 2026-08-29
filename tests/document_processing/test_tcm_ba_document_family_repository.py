from __future__ import annotations

import unittest

from barreiras_docproc.processing import TextArtifact
from barreiras_docproc.tcm_ba_document_families import (
    TcmBaCatalogDocument,
    TcmBaDocumentFamilyService,
)
from barreiras_docproc.tcm_ba_document_family_repository import (
    TcmBaDocumentFamilyExtractionRepository,
)


class Cursor:
    def __init__(self, *, rows=(), row=None) -> None:
        self.rows = list(rows)
        self.row = row

    def fetchall(self):
        return list(self.rows)

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
        if "with preserved_documents as" in normalized:
            return Cursor(rows=self.pending_rows)
        if "with preserved as" in normalized:
            return Cursor(row=self.coverage_row)
        if "insert into raw.extraction_jobs" in normalized:
            return Cursor(row=self.job_row)
        return Cursor()

    def transaction(self):
        return Transaction()

    def close(self):
        return None


def document(category: str) -> TcmBaCatalogDocument:
    return TcmBaCatalogDocument(
        artifact=TextArtifact(
            raw_artifact_id="00000000-0000-0000-0000-000000000902",
            sha256="b" * 64,
            object_key="tcm-ba/monthly-documents/2021/01/a.pdf",
        ),
        source_record_key="tcm-ba:document:01/2021:abc",
        official_category=category,
    )


class TcmBaDocumentFamilyRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = RecordingConnection()
        self.repository = TcmBaDocumentFamilyExtractionRepository(
            lambda: self.connection  # type: ignore[arg-type]
        )

    def test_pending_documents_use_exact_catalog_lineage(self) -> None:
        self.connection.pending_rows = [
            {
                "artifact_id": "00000000-0000-0000-0000-000000000902",
                "sha256": "b" * 64,
                "object_key": "tcm-ba/monthly-documents/2021/01/a.pdf",
                "source_record_key": "tcm-ba:document:01/2021:abc",
                "official_category": "PCMGE009 - Contratos e aditivos",
            }
        ]

        pending = self.repository.pending_documents(5)

        self.assertEqual(len(pending), 1)
        self.assertEqual(
            pending[0].official_category,
            "PCMGE009 - Contratos e aditivos",
        )
        query = self.connection.queries[0][0]
        self.assertIn("catalog.id = prepare.parent_artifact_id", query)
        self.assertIn(
            "record.source_record_key = pdf.metadata ->> 'source_record_key'",
            query,
        )
        self.assertIn("job.status in ('succeeded', 'dead_lettered')", query)

    def test_classified_family_is_private_valid_result_without_document_name(
        self,
    ) -> None:
        result = TcmBaDocumentFamilyService(repository=self.repository).process(
            document("PCMGE009 - Contratos e aditivos")
        )

        self.assertTrue(result.job_created)
        self.assertEqual(result.family, "contracts_and_amendments")
        query, params = next(
            (query, params)
            for query, params in self.connection.queries
            if "insert into raw.extraction_results" in query
        )
        self.assertIn("'valid'", query)
        self.assertNotIn("public.", query)
        self.assertNotIn("finance.", query)
        self.assertNotIn("Contratos e aditivos", str(params))

    def test_unknown_family_is_preserved_for_review_not_forced(self) -> None:
        result = TcmBaDocumentFamilyService(repository=self.repository).process(
            document("PCMGE999 - Categoria futura")
        )

        self.assertEqual(result.family, "unknown")
        query, params = next(
            (query, params)
            for query, params in self.connection.queries
            if "insert into raw.extraction_results" in query
        )
        self.assertIn("case when %s = 'unknown' then 'needs_review'", query)
        self.assertIn("unrecognized_official_category", str(params))

    def test_existing_success_does_not_duplicate_inventory(self) -> None:
        self.connection.job_row = None

        result = TcmBaDocumentFamilyService(repository=self.repository).process(
            document("Documentos Adicionais")
        )

        self.assertFalse(result.job_created)
        self.assertEqual(result.results_inserted, 0)
        self.assertFalse(
            any(
                "insert into raw.extraction_results" in query
                for query, _params in self.connection.queries
            )
        )


    def test_coverage_reconciles_preserved_pdfs_with_current_results(self) -> None:
        self.connection.coverage_row = {
            "preserved_documents": 68,
            "classified_documents": 68,
            "unknown_documents": 0,
            "missing_documents": 0,
            "duplicate_results": 0,
            "invalid_results": 0,
            "open_failures": 0,
        }

        coverage = self.repository.document_family_coverage()

        self.assertEqual(coverage.preserved_documents, 68)
        self.assertEqual(coverage.classified_documents, 68)
        self.assertEqual(coverage.missing_documents, 0)
        query = self.connection.queries[0][0]
        self.assertIn("count(distinct pdf.id)", query)
        self.assertIn("result.extractor_version = %s", query)
        self.assertIn("from current_jobs as job", query)
        self.assertIn("'failed'", query)
        self.assertIn("'retry_scheduled'", query)
        self.assertIn("'dead_lettered'", query)


if __name__ == "__main__":
    unittest.main()
