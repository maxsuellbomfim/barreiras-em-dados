from __future__ import annotations

import unittest

from barreiras_docproc.postgres import PostgresExtractionRepository
from barreiras_docproc.processing import PageInput, TextArtifact


class Cursor:
    def __init__(self, *, rows=(), row=None) -> None:
        self.rows = list(rows)
        self.row = row

    def fetchone(self):
        if self.rows:
            return self.rows.pop(0)
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
        self.page_row = {"id": "00000000-0000-0000-0000-000000000912"}
        self.existing_page_row = None
        self.job_row = {"id": "00000000-0000-0000-0000-000000000913"}
        self.coverage_row = {"municipal_docx_processed_total": 4}

    def execute(self, query, params=None):
        normalized = " ".join(query.split())
        self.queries.append((normalized, params))
        if "municipal_docx_processed_total" in normalized:
            return Cursor(row=self.coverage_row)
        if "from raw.raw_artifacts as artifact" in normalized:
            return Cursor(rows=self.pending_rows)
        if "insert into raw.document_pages" in normalized:
            return Cursor(row=self.page_row)
        if "from raw.document_pages" in normalized:
            return Cursor(row=self.existing_page_row)
        if "insert into raw.extraction_jobs" in normalized:
            return Cursor(row=self.job_row)
        return Cursor()

    def transaction(self):
        return Transaction()

    def close(self):
        return None


class MunicipalDocxRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = RecordingConnection()
        self.repository = PostgresExtractionRepository(
            lambda: self.connection  # type: ignore[arg-type]
        )

    def test_queue_selects_only_unprocessed_official_municipal_docx(self) -> None:
        self.connection.pending_rows = [
            {
                "id": "00000000-0000-0000-0000-000000000911",
                "sha256": "a" * 64,
                "object_key": (
                    "municipal-transparency/documents/sha256/aa/"
                    f"{'a' * 64}.docx"
                ),
            }
        ]

        artifacts = self.repository.pending_municipal_docx_artifacts(10)

        self.assertEqual(len(artifacts), 1)
        query, params = self.connection.queries[0]
        self.assertIn(
            "artifact.metadata ->> 'schema_name' = 'municipal-transparency-document'",
            query,
        )
        self.assertIn("artifact.metadata ->> 'document_role' = 'docx'", query)
        self.assertIn(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            query,
        )
        self.assertIn(
            "artifact.object_key like "
            "'municipal-transparency/documents/%%.docx'",
            query,
        )
        self.assertIn("page.parser_version = %s", query)
        self.assertIn("job.status = 'dead_lettered'", query)
        self.assertRegex(
            query,
            r"job\.idempotency_key = encode\( sha256\(",
        )
        self.assertEqual(params[-1], 10)

    def test_persists_text_and_completed_job_in_one_transaction(self) -> None:
        artifact = TextArtifact(
            "00000000-0000-0000-0000-000000000911",
            "a" * 64,
            f"municipal-transparency/documents/sha256/aa/{'a' * 64}.docx",
        )
        page = PageInput(
            1,
            "docx-wordprocessingml/1.0.0",
            "Lei municipal nº 1.234",
            "b" * 64,
        )

        created = self.repository.persist_municipal_docx_text(
            artifact,
            (page,),
            job_type="municipal_docx_text",
            job_idempotency_key="c" * 64,
        )

        self.assertTrue(created)
        queries = [query for query, _params in self.connection.queries]
        self.assertTrue(
            any("insert into raw.document_pages" in query for query in queries)
        )
        job_query = next(
            query
            for query in queries
            if "insert into raw.extraction_jobs" in query
        )
        self.assertIn("status = 'succeeded'", job_query)

    def test_coverage_counts_only_current_successful_docx_text(self) -> None:
        processed_total = self.repository.municipal_docx_processed_total()

        self.assertEqual(processed_total, 4)
        query, params = next(
            (query, params)
            for query, params in self.connection.queries
            if "municipal_docx_processed_total" in query
        )
        self.assertIn("page.parser_version = %s", query)
        self.assertIn("job.status = 'succeeded'", query)
        self.assertIn("job.job_type = %s", query)
        self.assertEqual(len(params), 2)


if __name__ == "__main__":
    unittest.main()
