from __future__ import annotations

import unittest
from dataclasses import replace
from types import SimpleNamespace

from barreiras_collectors.connectors.cgu_federal_amendments import (
    fetch_cgu_federal_amendments,
)
from barreiras_collectors.persistence.models import ArtifactIntegrityError
from barreiras_collectors.persistence.service import (
    CGUFederalAmendmentPersistenceService,
)
from barreiras_collectors.resilience import RetryPolicy

from tests.collectors.test_cgu_federal_amendments import (
    DownloadTransport,
    amendment_row,
    archive_bytes,
    download_response,
)


class FakeObjectStore:
    def __init__(self, *, tamper: bool = False) -> None:
        self.objects: dict[str, bytes] = {}
        self.tamper = tamper

    def put_if_absent(self, *, object_key, body, content_type, expected_sha256):
        del content_type
        created = object_key not in self.objects
        self.objects.setdefault(object_key, body)
        return SimpleNamespace(
            sha256=expected_sha256,
            byte_size=len(body),
            created=created,
        )

    def read(self, object_key):
        body = self.objects[object_key]
        return body + b"changed" if self.tamper else body


class FakeRepository:
    def __init__(self) -> None:
        self.batches = []

    def persist(self, batch):
        self.batches.append(batch)
        return SimpleNamespace(
            collection_run_id="run",
            raw_artifact_id="artifact",
            inserted_records=len(batch.records),
            existing_records=0,
        )


def snapshot():
    body = archive_bytes([amendment_row()])
    return fetch_cgu_federal_amendments(
        transport=DownloadTransport(download_response(body)),
        retry_policy=RetryPolicy(max_attempts=1),
        sleep=lambda _seconds: None,
    )


class CGUFederalAmendmentPersistenceTests(unittest.TestCase):
    def test_preserves_zip_and_emits_versioned_records(self) -> None:
        repository = FakeRepository()
        collected = snapshot()

        result = CGUFederalAmendmentPersistenceService(
            object_store=FakeObjectStore(),
            repository=repository,
        ).persist(collected)

        self.assertEqual(
            result.object_key,
            (
                "cgu/emendas-federais/sha256/"
                f"{collected.body_sha256[:2]}/{collected.body_sha256}.zip"
            ),
        )
        record = repository.batches[0].records[0]
        self.assertEqual(record.record_type, "cgu_federal_amendment_execution")
        self.assertEqual(record.parser_version, "cgu-federal-amendments/1.0.0")
        self.assertTrue(
            record.source_record_key.startswith(
                "cgu:federal-amendment:2023:202340720005:"
            )
        )
        self.assertNotIn("total_paid_amount", record.payload)

    def test_refuses_items_that_do_not_match_preserved_archive(self) -> None:
        collected = snapshot()
        with self.assertRaisesRegex(ArtifactIntegrityError, "ZIP preservado"):
            CGUFederalAmendmentPersistenceService(
                object_store=FakeObjectStore(),
                repository=FakeRepository(),
            ).persist(replace(collected, items=()))

    def test_refuses_archive_changed_after_storage_round_trip(self) -> None:
        with self.assertRaisesRegex(ArtifactIntegrityError, "restaurado"):
            CGUFederalAmendmentPersistenceService(
                object_store=FakeObjectStore(tamper=True),
                repository=FakeRepository(),
            ).persist(snapshot())


if __name__ == "__main__":
    unittest.main()
