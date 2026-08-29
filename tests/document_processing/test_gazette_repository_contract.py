from __future__ import annotations

import hashlib
import unittest

from barreiras_docproc.gazette_documents import DocumentBlock, GazetteDocumentDraft
from barreiras_docproc.gazette_repository import (
    GazetteArtifact,
    GazetteDocumentBatch,
    GazetteDocumentRepository,
)
from barreiras_docproc.processing import PageInput


class Cursor:
    def __init__(self, rows=(), row=None) -> None:
        self._rows = list(rows)
        self._row = row

    def fetchone(self):
        if self._rows:
            return self._rows.pop(0)
        return self._row


class Transaction:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class RecordingConnection:
    def __init__(self) -> None:
        self.queries: list[tuple[str, object]] = []
        self.pending_rows = []
        self.page_rows = []
        self.inserted_version = {"id": "00000000-0000-0000-0000-000000000901"}
        self.persisted_batches: set[str] = set()

    def execute(self, query, params=None):
        normalized = " ".join(query.split())
        self.queries.append((normalized, params))
        if "insert into raw.document_blocks" in normalized:
            return Cursor(row={"id": "00000000-0000-0000-0000-000000000801"})
        if "from raw.raw_artifacts" in normalized:
            return Cursor(rows=self.pending_rows)
        if "from editorial.gazette_document_versions" in normalized and (
            "batch_idempotency_key" in normalized
        ):
            key = params[-1]
            return Cursor(row={"ok": True} if key in self.persisted_batches else None)
        if "from raw.document_pages" in normalized:
            return Cursor(rows=self.page_rows)
        if "insert into editorial.gazette_document_versions" in normalized:
            return Cursor(row=self.inserted_version)
        return Cursor()

    def transaction(self):
        return Transaction()

    def close(self):
        return None


class GazetteRepositoryContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = RecordingConnection()
        self.repository = GazetteDocumentRepository(lambda: self.connection)  # type: ignore[arg-type]

    def test_pending_artifacts_requires_complete_pages_and_orders_newest_first(
        self,
    ) -> None:
        self.connection.pending_rows = [
            {
                "id": "00000000-0000-0000-0000-000000000707",
                "sha256": "a" * 64,
                "edition": 4707,
                "edition_year": 2026,
                "edition_date": "2026-08-08",
                "created_at": "2026-08-08T12:00:00+00:00",
            }
        ]

        artifacts = self.repository.pending_artifacts(1)

        self.assertEqual(artifacts[0].edition, 4707)
        query = self.connection.queries[0][0]
        self.assertIn(
            "min(page.page_number) = 1",
            query,
        )
        self.assertIn(
            "count(distinct page.page_number) "
            "filter (where page.text_content is not null) "
            "= max(page.page_number)",
            query,
        )
        self.assertIn(
            "order by edition.edition_year desc, edition.edition desc,",
            query,
        )
        self.assertIn(
            "edition.edition_date, edition.source_priority, "
            "edition.created_at::text as created_at",
            query,
        )
        self.assertIn(
            "where (%s::integer is null or edition.edition = %s::integer)",
            query,
        )
        self.assertIn(
            "and (%s::integer is null or edition.edition_year = %s::integer)",
            query,
        )

    def test_pending_artifacts_bounds_automatic_scan_and_skips_versioned_artifacts(
        self,
    ) -> None:
        self.repository.pending_artifacts(7)

        query, params = self.connection.queries[0]
        self.assertIn(
            "not exists ( select 1 from editorial.gazette_document_versions",
            query,
        )
        self.assertIn("where version.raw_artifact_id = edition.id", query)
        self.assertIn("limit %s ) select", query)
        self.assertEqual(params, (None, None, None, None, None, None, 7))

    def test_pending_artifacts_keeps_explicit_edition_replay_available(self) -> None:
        self.repository.pending_artifacts(2, edition=4706, edition_year=2026)

        query, params = self.connection.queries[0]
        self.assertIn(
            "(%s::integer is not null and %s::integer is not null) or not exists",
            query,
        )
        self.assertEqual(params, (4706, 4706, 2026, 2026, 4706, 2026, 2))

    def test_pending_artifacts_includes_querido_diario_record_metadata(self) -> None:
        self.connection.pending_rows = [
            {
                "id": "00000000-0000-0000-0000-000000000706",
                "sha256": "a" * 64,
                "edition": 4706,
                "edition_year": 2026,
                "edition_date": "2026-08-08",
                "created_at": "2026-08-08T12:00:00+00:00",
            }
        ]

        artifacts = self.repository.pending_artifacts(1)

        self.assertEqual(artifacts[0].edition, 4706)
        query = self.connection.queries[0][0]
        self.assertIn("join raw.raw_records as record", query)
        self.assertIn("record.record_type = 'querido_diario_gazette'", query)
        self.assertIn("record.payload ->> 'edition'", query)
        self.assertIn("from ( select distinct on (artifact.id)", query)
        self.assertIn(") as querido", query)

    def test_pending_direct_artifacts_enriches_date_from_matching_publication(
        self,
    ) -> None:
        self.connection.pending_rows = [
            {
                "id": "00000000-0000-0000-0000-000000000705",
                "sha256": "a" * 64,
                "edition": 4705,
                "edition_year": 2026,
                "edition_date": "2026-08-07",
                "created_at": "2026-08-08T12:00:00+00:00",
            }
        ]

        artifacts = self.repository.pending_artifacts(1)

        self.assertEqual(artifacts[0].edition_date, "2026-08-07")
        query = self.connection.queries[0][0]
        self.assertIn("left join lateral", query)
        self.assertIn("record.record_type = 'barreiras_diario_publication'", query)
        self.assertIn(
            "record.payload ->> 'edition' = edition.edition::text",
            query,
        )
        self.assertIn(
            "extract(year from (record.payload ->> 'date')::date)::integer",
            query,
        )
        self.assertLess(
            query.index("limit %s ) select"),
            query.index("left join lateral"),
        )

    def test_batch_exists_checks_the_exact_idempotency_key(self) -> None:
        self.connection.persisted_batches.add("z" * 64)

        exists = self.repository.batch_exists(
            "00000000-0000-0000-0000-000000000707", "z" * 64
        )

        self.assertTrue(exists)

    def test_page_inputs_choose_latest_text_or_ocr_per_page(self) -> None:
        self.connection.page_rows = [
            {
                "page_number": 1,
                "parser_version": "ocr/1",
                "text_content": "texto",
                "text_sha256": "b" * 64,
                "extraction_method": "ocr",
            }
        ]

        pages = self.repository.page_inputs("00000000-0000-0000-0000-000000000707")

        self.assertEqual(pages, (PageInput(1, "ocr/1", "texto", "b" * 64, "ocr"),))

    def test_persist_version_is_append_only_and_idempotent(self) -> None:
        artifact = GazetteArtifact(
            "00000000-0000-0000-0000-000000000707",
            "a" * 64,
            4707,
            2026,
            "2026-08-08",
            "2026-08-08T12:00:00+00:00",
        )
        document = GazetteDocumentDraft(
            0, 0, 1, 1, "PORTARIA N 2", "PORTARIA N 2\nTexto", "validated"
        )
        batch = GazetteDocumentBatch(
            artifact=artifact,
            pages=(PageInput(1, "parser/1", "PORTARIA N 2\nTexto", "b" * 64),),
            blocks=(
                DocumentBlock.create(
                    page_number=1, block_order=0, text="PORTARIA N 2\nTexto"
                ),
            ),
            documents=(document,),
            idempotency_key=hashlib.sha256(b"version").hexdigest(),
            segmenter_version="segmenter/1",
            validator_version="validator/1",
        )

        result = self.repository.persist_version(batch)

        self.assertTrue(result.created)
        inserts = [
            query
            for query, _params in self.connection.queries
            if "insert into editorial.gazette_document_versions" in query
        ]
        self.assertEqual(len(inserts), 1)
        self.assertIn("on conflict (idempotency_key) do nothing", inserts[0])
        self.assertFalse(any(" update " in f" {query.lower()} " for query in inserts))
        block_insert_params = next(
            params
            for query, params in self.connection.queries
            if "insert into raw.document_blocks" in query
        )
        assert block_insert_params is not None
        self.assertEqual(block_insert_params[-1], "parser/1")
        association_inserts = [
            query
            for query, _params in self.connection.queries
            if "insert into editorial.gazette_document_version_blocks" in query
        ]
        self.assertEqual(len(association_inserts), 1)


if __name__ == "__main__":
    unittest.main()
