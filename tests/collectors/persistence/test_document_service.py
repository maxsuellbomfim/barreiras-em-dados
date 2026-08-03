from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

from barreiras_collectors.connectors.gazette_documents import CollectedDocument
from barreiras_collectors.connectors.querido_diario import QueridoDiarioClient
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.persistence.filesystem import (
    FilesystemCollectionRepository,
)
from barreiras_collectors.persistence.postgres import PostgresCollectionRepository
from barreiras_collectors.persistence.models import (
    ArtifactIntegrityError,
    DocumentBatch,
    PersistenceBatch,
    PersistenceContractError,
    RepositoryDocumentResult,
    RepositoryPersistResult,
)
from barreiras_collectors.persistence.service import (
    QueridoDiarioPersistenceService,
)
from barreiras_collectors.persistence.storage import (
    SupabaseStorageObjectStore,
)

ROOT = Path(__file__).parents[3]
FIXTURE_PATH = ROOT / "fixtures" / "sources" / "querido_diario" / "gazettes-page-1.json"


class StaticTransport:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout_seconds: float,
        max_body_bytes: int,
    ) -> HttpResponse:
        del headers, timeout_seconds, max_body_bytes
        return HttpResponse(
            status=200,
            headers={"Content-Type": "application/json; charset=utf-8"},
            body=self.body,
            final_url=url,
        )


class NoopRateLimiter:
    def acquire(self) -> None:
        return None


class FakeBucket:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.uploads = 0

    def upload(
        self,
        *,
        path: str,
        file: bytes,
        file_options: dict[str, str],
    ) -> object:
        self.uploads += 1
        if path in self.objects:
            raise RuntimeError("Duplicate")
        self.objects[path] = file
        return {"path": path}

    def download(self, path: str) -> bytes:
        return self.objects[path]


class FakeRepository:
    def __init__(self) -> None:
        self.batches: list[PersistenceBatch] = []
        self.record_keys: set[str] = set()
        self.documents: dict[str, DocumentBatch] = {}

    def persist(self, batch: PersistenceBatch) -> RepositoryPersistResult:
        self.batches.append(batch)
        inserted = 0
        existing = 0
        for record in batch.records:
            if record.idempotency_key in self.record_keys:
                existing += 1
            else:
                self.record_keys.add(record.idempotency_key)
                inserted += 1
        return RepositoryPersistResult(
            collection_run_id="00000000-0000-0000-0000-000000000201",
            raw_artifact_id="00000000-0000-0000-0000-000000000202",
            inserted_records=inserted,
            existing_records=existing,
        )

    def persist_document(self, batch: DocumentBatch) -> RepositoryDocumentResult:
        created = batch.idempotency_key not in self.documents
        self.documents.setdefault(batch.idempotency_key, batch)
        return RepositoryDocumentResult(
            raw_artifact_id="00000000-0000-0000-0000-000000000303",
            created=created,
        )


def make_page():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    body = json.dumps(
        fixture["response"],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    client = QueridoDiarioClient(
        transport=StaticTransport(body),
        rate_limiter=NoopRateLimiter(),  # type: ignore[arg-type]
    )
    return next(client.iter_gazette_pages(page_size=100))


def make_document(body: bytes = b"%PDF-1.7 diario", role: str = "pdf"):
    now = datetime(2026, 7, 31, 12, 0, tzinfo=UTC).isoformat()
    return CollectedDocument(
        role=role,
        source_url=(
            "https://data.queridodiario.ok.org.br/2903201/2026-07-01/exemplo-001.pdf"
        ),
        final_url=(
            "https://data.queridodiario.ok.org.br/2903201/2026-07-01/exemplo-001.pdf"
        ),
        requested_at=now,
        received_at=now,
        attempts=1,
        http_status=200,
        body_sha256=hashlib.sha256(body).hexdigest(),
        body_size_bytes=len(body),
        media_type="application/pdf",
        response_headers={"content-type": "application/pdf"},
        raw_body=body,
    )


class GazetteDocumentPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bucket = FakeBucket()
        self.repository = FakeRepository()
        self.service = QueridoDiarioPersistenceService(
            object_store=SupabaseStorageObjectStore(self.bucket),
            repository=self.repository,
        )
        self.page = make_page()
        self.page_result = self.service.persist(self.page)
        self.record = self.service.gazette_records(self.page)[0]

    def persist(self, document):
        return self.service.persist_document(
            page_result=self.page_result,
            record=self.record,
            document=document,
            source_code=self.page.source_code,
            endpoint_code=self.page.endpoint_code,
        )

    def test_document_becomes_child_artifact_inside_allowed_prefix(self) -> None:
        document = make_document()

        result = self.persist(document)

        self.assertTrue(result.object_created)
        self.assertTrue(result.artifact_created)
        self.assertTrue(
            result.object_key.startswith(
                "querido-diario/gazettes/documents/sha256/"
            )
        )
        self.assertTrue(result.object_key.endswith(".pdf"))
        self.assertIn(document.body_sha256, result.object_key)
        batch = self.repository.documents[
            next(iter(self.repository.documents))
        ]
        self.assertEqual(
            batch.parent_artifact_id,
            self.page_result.raw_artifact_id,
        )
        self.assertEqual(
            batch.collection_run_id,
            self.page_result.collection_run_id,
        )
        self.assertEqual(batch.source_record_key, self.record.source_record_key)

    def test_replay_is_idempotent(self) -> None:
        document = make_document()

        first = self.persist(document)
        second = self.persist(document)

        self.assertTrue(first.object_created)
        self.assertFalse(second.object_created)
        self.assertFalse(second.artifact_created)
        self.assertEqual(len(self.bucket.objects), 2)  # página + documento

    def test_tampered_storage_is_detected_on_replay(self) -> None:
        document = make_document()
        first = self.persist(document)
        self.bucket.objects[first.object_key] = b"conteudo adulterado"

        with self.assertRaises(ArtifactIntegrityError):
            self.persist(document)

    def test_rejects_document_with_wrong_hash_before_upload(self) -> None:
        document = replace(make_document(), body_sha256="0" * 64)
        uploads_before = self.bucket.uploads

        with self.assertRaises(ArtifactIntegrityError):
            self.persist(document)

        self.assertEqual(self.bucket.uploads, uploads_before)
        self.assertEqual(self.repository.documents, {})

    def test_rejects_unknown_document_role(self) -> None:
        document = replace(make_document(), role="html")

        with self.assertRaises(PersistenceContractError):
            self.persist(document)


class FilesystemDocumentRepositoryTests(unittest.TestCase):
    def make_batch(self, body: bytes = b"%PDF-1.7 diario") -> DocumentBatch:
        document = make_document(body)
        return DocumentBatch(
            source_code="querido-diario",
            endpoint_code="gazettes-api",
            collection_run_id="00000000-0000-0000-0000-000000000201",
            parent_artifact_id="00000000-0000-0000-0000-000000000202",
            source_record_key="querido-diario:gazette:" + "a" * 64,
            document=document,
            object_key=(
                "querido-diario/gazettes/documents/sha256/"
                f"{document.body_sha256[:2]}/{document.body_sha256}.pdf"
            ),
            idempotency_key=hashlib.sha256(b"doc-idem").hexdigest(),
            collector_version="querido-diario-collector/0.1.0",
        )

    def test_replay_keeps_single_manifest_and_stable_identity(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as raw_root:
            repository = FilesystemCollectionRepository(Path(raw_root))
            batch = self.make_batch()

            first = repository.persist_document(batch)
            second = repository.persist_document(batch)

            self.assertTrue(first.created)
            self.assertFalse(second.created)
            self.assertEqual(first.raw_artifact_id, second.raw_artifact_id)

    def test_divergent_identity_under_same_key_is_rejected(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as raw_root:
            repository = FilesystemCollectionRepository(Path(raw_root))
            batch = self.make_batch()
            repository.persist_document(batch)

            divergent = replace(
                batch,
                object_key=batch.object_key.replace(".pdf", ".txt"),
            )
            with self.assertRaises(PersistenceContractError):
                repository.persist_document(divergent)

    def test_replay_with_new_parent_artifact_keeps_content_identity(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as raw_root:
            repository = FilesystemCollectionRepository(Path(raw_root))
            batch = self.make_batch()
            repository.persist_document(batch)

            recollection = replace(
                batch,
                parent_artifact_id="00000000-0000-0000-0000-000000000999",
            )
            result = repository.persist_document(recollection)

            self.assertFalse(result.created)


class PostgresDocumentRepositoryTests(unittest.TestCase):
    def test_same_pdf_with_new_parent_artifact_is_idempotent(self) -> None:
        batch = FilesystemDocumentRepositoryTests().make_batch()
        connection = Mock()
        connection.execute.side_effect = [
            Mock(fetchone=Mock(return_value=None)),
            Mock(
                fetchone=Mock(
                    return_value={
                        "id": "00000000-0000-0000-0000-000000000707",
                        "parent_artifact_id": "00000000-0000-0000-0000-000000000202",
                        "sha256": batch.document.body_sha256,
                        "byte_size": batch.document.body_size_bytes,
                        "object_key": batch.object_key,
                    }
                )
            ),
        ]
        recollection = replace(
            batch,
            parent_artifact_id="00000000-0000-0000-0000-000000000999",
        )

        result = PostgresCollectionRepository._document_artifact(
            connection,
            recollection,
            "00000000-0000-0000-0000-000000000606",
        )

        self.assertFalse(result.created)
        self.assertEqual(result.raw_artifact_id, "00000000-0000-0000-0000-000000000707")


if __name__ == "__main__":
    unittest.main()
