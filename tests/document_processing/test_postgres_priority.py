from __future__ import annotations

import unittest

from barreiras_docproc.postgres import PostgresExtractionRepository


class EmptyResult:
    def fetchone(self):
        return None


class RecordingConnection:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.params: list[object] = []

    def execute(self, query, params=None):
        self.queries.append(" ".join(query.split()))
        self.params.append(params)
        return EmptyResult()

    def close(self):
        return None


class RecentDirectEditionPriorityTests(unittest.TestCase):
    def test_candidate_queue_prioritizes_recent_direct_editions(self) -> None:
        connection = RecordingConnection()
        repository = PostgresExtractionRepository(lambda: connection)  # type: ignore[arg-type]

        repository.pending_text_artifacts(30)

        query = connection.queries[0]
        self.assertIn(
            "case when artifact.metadata ->> 'schema_name' "
            "= 'gazette-direct-edition' then 0 else 1 end",
            query,
        )
        self.assertIn(
            "then (artifact.metadata ->> 'edition')::integer "
            "end desc nulls last",
            query,
        )

    def test_ocr_queue_prioritizes_recent_direct_editions(self) -> None:
        connection = RecordingConnection()
        repository = PostgresExtractionRepository(lambda: connection)  # type: ignore[arg-type]

        repository.pending_ocr_pages(30)

        query = connection.queries[0]
        self.assertIn(
            "case when artifact.metadata ->> 'schema_name' "
            "= 'gazette-direct-edition' then 0 else 1 end",
            query,
        )
        self.assertIn(
            "then (artifact.metadata ->> 'edition')::integer "
            "end desc nulls last",
            query,
        )

    def test_ocr_queue_is_scoped_to_the_requested_source(self) -> None:
        connection = RecordingConnection()
        repository = PostgresExtractionRepository(lambda: connection)  # type: ignore[arg-type]

        repository.pending_ocr_pages(30, source="tcm-ba")

        query = connection.queries[0]
        self.assertIn("source_scope.value = 'querido-diario'", query)
        self.assertIn("source_scope.value = 'tcm-ba'", query)
        self.assertIn("= 'tcm-ba-monthly-document'", query)
        self.assertEqual(connection.params[0], ("tcm-ba", 30))

    def test_ocr_queue_rejects_unknown_source_before_querying(self) -> None:
        connection = RecordingConnection()
        repository = PostgresExtractionRepository(lambda: connection)  # type: ignore[arg-type]

        with self.assertRaises(ValueError):
            repository.pending_ocr_pages(30, source="unknown")

        self.assertEqual(connection.queries, [])

    def test_tcm_ba_queue_selects_only_unprocessed_monthly_pdfs(self) -> None:
        connection = RecordingConnection()
        repository = PostgresExtractionRepository(lambda: connection)  # type: ignore[arg-type]

        repository.pending_tcm_ba_pdf_artifacts(5)

        query = connection.queries[0]
        self.assertIn(
            "artifact.metadata ->> 'schema_name' = 'tcm-ba-monthly-document'",
            query,
        )
        self.assertIn(
            "artifact.object_key like 'tcm-ba/monthly-documents/%%/pdf/%%'",
            query,
        )
        self.assertIn("from raw.document_pages as page", query)
        self.assertIn("page.parser_version =", query)
        self.assertIn("order by artifact.created_at, artifact.id", query)

    def test_tcm_ba_queue_can_target_one_exact_pdf_hash(self) -> None:
        connection = RecordingConnection()
        repository = PostgresExtractionRepository(lambda: connection)  # type: ignore[arg-type]
        artifact_sha256 = "a" * 64

        repository.pending_tcm_ba_pdf_artifacts(
            1,
            artifact_sha256=artifact_sha256,
        )

        query = connection.queries[0]
        self.assertIn("artifact.sha256 = %s", query)
        self.assertEqual(
            connection.params[0],
            (
                artifact_sha256,
                artifact_sha256,
                connection.params[0][2],
                1,
            ),
        )

    def test_tcm_ba_queue_rejects_invalid_exact_hash_before_querying(self) -> None:
        connection = RecordingConnection()
        repository = PostgresExtractionRepository(lambda: connection)  # type: ignore[arg-type]

        with self.assertRaisesRegex(ValueError, "artifact_sha256"):
            repository.pending_tcm_ba_pdf_artifacts(
                1,
                artifact_sha256="invalido",
            )

        self.assertEqual(connection.queries, [])
if __name__ == "__main__":
    unittest.main()
