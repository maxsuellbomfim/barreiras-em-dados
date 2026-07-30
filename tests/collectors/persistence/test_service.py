from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path

from barreiras_collectors.connectors.querido_diario import QueridoDiarioClient
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.persistence.models import (
    ArtifactIntegrityError,
    PersistenceBatch,
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
        del headers, timeout_seconds
        if len(self.body) > max_body_bytes:
            raise AssertionError("Fixture excede o limite.")
        return HttpResponse(
            status=200,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "ETag": '"fixture-etag"',
            },
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
        self.downloads = 0

    def upload(
        self,
        *,
        path: str,
        file: bytes,
        file_options: dict[str, str],
    ) -> object:
        self.uploads += 1
        if file_options["upsert"] != "false":
            raise AssertionError("O teste exige upload sem sobrescrita.")
        if path in self.objects:
            raise RuntimeError("Duplicate")
        self.objects[path] = file
        return {"path": path}

    def download(self, path: str) -> bytes:
        self.downloads += 1
        return self.objects[path]


class FakeRepository:
    def __init__(self) -> None:
        self.batches: list[PersistenceBatch] = []
        self.record_keys: set[str] = set()
        self.run_ids: dict[str, str] = {}
        self.artifact_ids: dict[str, str] = {}

    def persist(self, batch: PersistenceBatch) -> RepositoryPersistResult:
        self.batches.append(batch)
        run_id = self.run_ids.setdefault(
            batch.page.idempotency_key,
            "00000000-0000-0000-0000-000000000201",
        )
        artifact_id = self.artifact_ids.setdefault(
            batch.artifact_idempotency_key,
            "00000000-0000-0000-0000-000000000202",
        )
        inserted = 0
        existing = 0
        for record in batch.records:
            if record.idempotency_key in self.record_keys:
                existing += 1
            else:
                self.record_keys.add(record.idempotency_key)
                inserted += 1
        return RepositoryPersistResult(
            collection_run_id=run_id,
            raw_artifact_id=artifact_id,
            inserted_records=inserted,
            existing_records=existing,
        )


class FailingRepository:
    def persist(self, batch: PersistenceBatch) -> RepositoryPersistResult:
        del batch
        raise RuntimeError("Banco indisponível")


def make_page(payload: dict[str, object] | None = None):
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    response = payload or fixture["response"]
    body = json.dumps(
        response,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    client = QueridoDiarioClient(
        transport=StaticTransport(body),
        rate_limiter=NoopRateLimiter(),  # type: ignore[arg-type]
    )
    return next(client.iter_gazette_pages(page_size=100))


class QueridoDiarioPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bucket = FakeBucket()
        self.store = SupabaseStorageObjectStore(self.bucket)
        self.repository = FakeRepository()
        self.service = QueridoDiarioPersistenceService(
            object_store=self.store,
            repository=self.repository,
        )

    def test_replay_reuses_object_and_does_not_duplicate_records(self) -> None:
        page = make_page()

        first = self.service.persist(page)
        second = self.service.persist(page)

        self.assertTrue(first.object_created)
        self.assertFalse(second.object_created)
        self.assertEqual(first.raw_artifact_id, second.raw_artifact_id)
        self.assertEqual(first.inserted_records, 2)
        self.assertEqual(second.inserted_records, 0)
        self.assertEqual(second.existing_records, 2)
        self.assertEqual(len(self.bucket.objects), 1)

    def test_restoration_detects_bytes_changed_under_same_key(self) -> None:
        page = make_page()
        first = self.service.persist(page)
        self.bucket.objects[first.object_key] = b'{"tampered":true}'

        with self.assertRaises(ArtifactIntegrityError):
            self.service.persist(page)

        self.assertEqual(len(self.repository.batches), 1)

    def test_storage_survives_database_failure_and_retry_reuses_it(self) -> None:
        page = make_page()
        failing_service = QueridoDiarioPersistenceService(
            object_store=self.store,
            repository=FailingRepository(),
        )

        with self.assertRaisesRegex(RuntimeError, "Banco indisponível"):
            failing_service.persist(page)

        self.assertEqual(len(self.bucket.objects), 1)
        retried = self.service.persist(page)
        self.assertFalse(retried.object_created)
        self.assertEqual(retried.inserted_records, 2)

    def test_raw_record_keeps_additive_source_fields_exactly(self) -> None:
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        payload = fixture["response"]
        payload["gazettes"][0]["future_source_field"] = {
            "nested": ["kept", 1],
        }
        page = make_page(payload)

        self.service.persist(page)

        persisted_payload = self.repository.batches[0].records[0].payload
        self.assertEqual(
            persisted_payload["future_source_field"],
            {"nested": ["kept", 1]},
        )

    def test_rejects_page_whose_hash_was_changed_before_storage(self) -> None:
        page = make_page()
        invalid = replace(page, body_sha256="0" * 64)

        with self.assertRaises(ArtifactIntegrityError):
            self.service.persist(invalid)

        self.assertEqual(self.bucket.uploads, 0)
        self.assertEqual(self.repository.batches, [])


if __name__ == "__main__":
    unittest.main()
