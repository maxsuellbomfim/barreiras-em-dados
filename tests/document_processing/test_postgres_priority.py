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
    def test_ocr_retries_page_number_only_in_direct_diary_pdfs(self) -> None:
        connection = RecordingConnection()
        repository = PostgresExtractionRepository(lambda: connection)
        repository.pending_ocr_pages(30)
        query = connection.queries[0]
        self.assertIn("btrim(page.text_content) = page.page_number::text", query)
        self.assertIn("artifact.content_type = 'application/pdf'", query)
        self.assertIn("page.extraction_method <> 'ocr'", query)
        self.assertIn("supplemental.extraction_method = 'ocr'", query)
        self.assertIn(
            "btrim(supplemental.text_content) <> page.page_number::text", query
        )

    def test_candidate_queue_reopens_editions_after_ocr_text(self) -> None:
        connection = RecordingConnection()
        repository = PostgresExtractionRepository(lambda: connection)  # type: ignore[arg-type]

        repository.pending_text_artifacts(30)

        query = connection.queries[0]
        params = connection.params[0]
        # OCR mais novo que a última extração feita com texto de OCR reabre a
        # edição; a extração com a chave histórica usou só o texto embutido.
        self.assertIn(
            "select max(ocr.created_at) from raw.document_pages as ocr "
            "where ocr.raw_artifact_id = artifact.id "
            "and ocr.extraction_method = 'ocr' ) > coalesce((",
            query,
        )
        self.assertIn("and job.idempotency_key <> encode(", query)
        self.assertEqual(len(params), 3)
        self.assertEqual(params[0], params[1])

    def test_candidate_queue_waits_ocr_for_page_number_only_text(self) -> None:
        connection = RecordingConnection()
        repository = PostgresExtractionRepository(lambda: connection)  # type: ignore[arg-type]

        repository.pending_text_artifacts(30)

        query = connection.queries[0]
        self.assertIn(
            "and page.extraction_method <> 'ocr' "
            "and btrim(page.text_content) = page.page_number::text",
            query,
        )
        # Página em branco com OCR não pode travar a edição para sempre.
        self.assertIn(
            "supplemental.extraction_method = 'ocr' "
            "or btrim(supplemental.text_content) "
            "<> supplemental.page_number::text",
            query,
        )

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
        self.assertIn(
            "%s::text is not null or not exists",
            query,
        )
        self.assertEqual(
            connection.params[0],
            (
                artifact_sha256,
                artifact_sha256,
                artifact_sha256,
                connection.params[0][3],
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


class PendingActsIndexContractTests(unittest.TestCase):
    def test_pending_acts_query_matches_partial_index_predicates(self) -> None:
        # Sem o mesmo predicado, o planejador ignora os índices parciais e a
        # consulta volta a passar do statement_timeout de 15 s do coletor.
        from pathlib import Path

        migration = " ".join(
            (
                Path(__file__).resolve().parents[2]
                / "supabase/migrations/20260924124222_gazette_pending_acts_indexes.sql"
            )
            .read_text(encoding="utf-8")
            .split()
        )
        connection = RecordingConnection()
        PostgresExtractionRepository(lambda: connection).pending_text_artifacts(20)
        query = connection.queries[0]

        self.assertIn(
            "where artifact_kind = 'document' and ("
            " metadata ->> 'document_role' = 'txt'"
            " or metadata ->> 'schema_name' = 'gazette-direct-edition' );",
            migration,
        )
        self.assertIn(
            "where artifact.artifact_kind = 'document' and ("
            " artifact.metadata ->> 'document_role' = 'txt'"
            " or artifact.metadata ->> 'schema_name' = 'gazette-direct-edition' )",
            query,
        )
        self.assertIn("where extraction_method = 'ocr';", migration)
        self.assertIn(
            "where ocr.raw_artifact_id = artifact.id"
            " and ocr.extraction_method = 'ocr'",
            query,
        )


class MisattributedDirectCopyTests(unittest.TestCase):
    def test_ocr_segmentation_and_acts_skip_catalog_copies(self) -> None:
        # 4309 e 4263 de 2024 são cópias de 4310 e 4264 servidas pelo
        # catálogo; reorganizá-las falha no conflito de hash a cada OCR novo
        # e extrair atos delas os atribuiria à edição errada.
        from barreiras_docproc.gazette_repository import GazetteDocumentRepository

        connection = RecordingConnection()
        extraction = PostgresExtractionRepository(lambda: connection)
        extraction.pending_ocr_pages(30)
        extraction.pending_text_artifacts(20)
        GazetteDocumentRepository(lambda: connection).pending_artifacts(50)

        self.assertEqual(len(connection.queries), 3)
        for query in connection.queries:
            self.assertIn("other_edition.sha256 = artifact.sha256", query)
            self.assertIn(
                "other_edition.metadata ->> 'edition' = substring("
                " artifact.metadata ->> 'final_url'",
                query,
            )


class SegmenterPageStatsIndexTests(unittest.TestCase):
    def test_page_stats_never_read_page_text_rows(self) -> None:
        # Agregar numeração e texto na mesma varredura lia as páginas inteiras
        # e passava do statement_timeout de 15 s do coletor (dreno #16).
        from pathlib import Path

        from barreiras_docproc.gazette_repository import GazetteDocumentRepository

        migration = " ".join(
            (
                Path(__file__).resolve().parents[2]
                / "supabase/migrations"
                / "20260924185152_gazette_segmenter_page_indexes.sql"
            )
            .read_text(encoding="utf-8")
            .split()
        )
        connection = RecordingConnection()
        GazetteDocumentRepository(lambda: connection).pending_artifacts(50)
        query = connection.queries[0]

        self.assertNotIn("filter (where page.text_content is not null)", query)
        self.assertIn("and page.text_content is not null group by", query)
        self.assertIn(
            "on raw.document_pages (raw_artifact_id, page_number, created_at);",
            migration,
        )
        self.assertIn(
            "on raw.document_pages (raw_artifact_id, page_number)"
            " where text_content is not null;",
            migration,
        )
