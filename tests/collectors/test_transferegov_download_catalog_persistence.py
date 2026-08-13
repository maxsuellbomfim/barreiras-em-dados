from __future__ import annotations

import unittest
from dataclasses import replace
from types import SimpleNamespace

from barreiras_collectors.connectors.transferegov_download_catalog import (
    REQUIRED_HISTORICAL_FILES,
    fetch_download_catalog,
)
from barreiras_collectors.persistence.models import ArtifactIntegrityError
from barreiras_collectors.persistence.service import (
    TransferegovDownloadCatalogPersistenceService,
)
from barreiras_collectors.resilience import RetryPolicy

from tests.collectors.test_transferegov_download_catalog import (
    OneShotTransport,
    catalog_xml,
    response,
)


class FakeObjectStore:
    def __init__(self, *, tamper: bool = False) -> None:
        self.objects: dict[str, bytes] = {}
        self.tamper = tamper
        self.content_types: dict[str, str] = {}

    def put_if_absent(self, *, object_key, body, content_type, expected_sha256):
        created = object_key not in self.objects
        self.objects.setdefault(object_key, body)
        self.content_types[object_key] = content_type
        return SimpleNamespace(
            sha256=expected_sha256,
            byte_size=len(body),
            created=created,
        )

    def read(self, object_key):
        body = self.objects[object_key]
        return body + b"alterado" if self.tamper else body


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
    return fetch_download_catalog(
        transport=OneShotTransport(response(catalog_xml())),
        retry_policy=RetryPolicy(max_attempts=1),
        sleep=lambda _seconds: None,
    )


class TransferegovDownloadCatalogPersistenceTests(unittest.TestCase):
    def test_preserves_xml_and_emits_one_versioned_raw_record_per_required_file(
        self,
    ) -> None:
        store = FakeObjectStore()
        repository = FakeRepository()
        collected = snapshot()

        result = TransferegovDownloadCatalogPersistenceService(
            object_store=store,
            repository=repository,
        ).persist(collected)

        self.assertEqual(result.inserted_records, len(REQUIRED_HISTORICAL_FILES))
        self.assertTrue(result.object_key.endswith(f"/{collected.body_sha256}.xml"))
        self.assertEqual(store.content_types[result.object_key], "application/xml")
        records = repository.batches[0].records
        self.assertEqual(
            {record.source_record_key for record in records},
            {
                f"transferegov:download:{name}"
                for name in REQUIRED_HISTORICAL_FILES
            },
        )
        self.assertEqual(
            {record.record_type for record in records},
            {"transferegov_download_catalog_entry"},
        )
        self.assertEqual(
            {record.parser_version for record in records},
            {"transferegov-download-catalog/1.0.0"},
        )

    def test_refuses_items_that_do_not_match_the_preserved_xml(self) -> None:
        collected = snapshot()
        altered = replace(collected, items=collected.items[:-1])

        with self.assertRaisesRegex(ArtifactIntegrityError, "XML preservado"):
            TransferegovDownloadCatalogPersistenceService(
                object_store=FakeObjectStore(),
                repository=FakeRepository(),
            ).persist(altered)

    def test_refuses_object_changed_after_storage_round_trip(self) -> None:
        with self.assertRaisesRegex(ArtifactIntegrityError, "restaurado"):
            TransferegovDownloadCatalogPersistenceService(
                object_store=FakeObjectStore(tamper=True),
                repository=FakeRepository(),
            ).persist(snapshot())


if __name__ == "__main__":
    unittest.main()
