from __future__ import annotations

import unittest
from types import SimpleNamespace

from barreiras_collectors.connectors.bahia_special_transfers import (
    CATALOG_URL,
    DOWNLOAD_URL,
    fetch_special_transfer_archive,
    fetch_special_transfer_catalog,
)
from barreiras_collectors.persistence.service import (
    BahiaSpecialTransferArchivePersistenceService,
    BahiaSpecialTransferCatalogPersistenceService,
)
from barreiras_collectors.resilience import RetryPolicy

from tests.collectors.test_bahia_special_transfers import (
    SequenceTransport,
    archive_bytes,
    catalog_body,
    response,
)


class FakeObjectStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

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
        return self.objects[object_key]


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


class BahiaSpecialTransferPersistenceTests(unittest.TestCase):
    def test_preserves_private_archive_and_only_member_manifests(self) -> None:
        archive = archive_bytes()
        transport = SequenceTransport(
            [
                response(
                    catalog_body(size=len(archive)),
                    final_url=CATALOG_URL,
                    content_type="application/json",
                ),
                response(
                    archive,
                    final_url=DOWNLOAD_URL,
                    content_type="application/zip",
                ),
            ]
        )
        catalog = fetch_special_transfer_catalog(
            transport=transport,
            retry_policy=RetryPolicy(max_attempts=1),
            sleep=lambda _seconds: None,
        )
        snapshot = fetch_special_transfer_archive(
            catalog=catalog,
            transport=transport,
            retry_policy=RetryPolicy(max_attempts=1),
            sleep=lambda _seconds: None,
        )
        repository = FakeRepository()
        object_store = FakeObjectStore()

        catalog_result = BahiaSpecialTransferCatalogPersistenceService(
            object_store=object_store,
            repository=repository,
        ).persist(catalog)
        archive_result = BahiaSpecialTransferArchivePersistenceService(
            object_store=object_store,
            repository=repository,
        ).persist(snapshot)

        self.assertIn("transferencias-especiais", catalog_result.object_key)
        self.assertIn("transferencias-especiais", archive_result.object_key)
        self.assertEqual(len(repository.batches), 2)
        records = repository.batches[1].records
        self.assertEqual(len(records), 5)
        self.assertTrue(all("rows" not in record.payload for record in records))
        payment = next(
            record for record in records if record.payload["restricted_columns"]
        )
        self.assertEqual(
            payment.payload["public_row_projection"],
            "forbidden",
        )


if __name__ == "__main__":
    unittest.main()
