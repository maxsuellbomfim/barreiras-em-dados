from __future__ import annotations

import unittest
from dataclasses import replace
from types import SimpleNamespace

from barreiras_collectors.connectors.bahia_state_amendments import (
    fetch_state_amendment_archive,
    fetch_state_amendment_catalog,
    fetch_state_amendment_relationship_diagram,
)
from barreiras_collectors.persistence import service as persistence_service
from barreiras_collectors.persistence.models import ArtifactIntegrityError
from barreiras_collectors.persistence.service import (
    BahiaStateAmendmentArchivePersistenceService,
    BahiaStateAmendmentCatalogPersistenceService,
)
from barreiras_collectors.resilience import RetryPolicy

from tests.collectors.test_bahia_state_amendments import (
    RELATIONSHIP_DIAGRAM_PNG,
    RELATIONSHIP_DIAGRAM_URL,
    SequenceTransport,
    archive_bytes,
    catalog_body,
    catalog_body_with_relationship,
    response,
)

CATALOG_URL = (
    "https://dados.ba.gov.br/api/3/action/"
    "package_show?id=emendas-parlamentares"
)
DOWNLOAD_URL = (
    "https://dados.ba.gov.br/dataset/"
    "1436b3e7-6594-4683-bfa5-b2e3a6c69e07/resource/"
    "2d284f2e-79cc-4e3c-a45b-6fc903a6e2d0/download/"
    "emendasparlamentares.zip"
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


def snapshots():
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
    catalog = fetch_state_amendment_catalog(
        transport=transport,
        retry_policy=RetryPolicy(max_attempts=1),
        sleep=lambda _seconds: None,
    )
    collected_archive = fetch_state_amendment_archive(
        catalog=catalog,
        transport=transport,
        retry_policy=RetryPolicy(max_attempts=1),
        sleep=lambda _seconds: None,
    )
    return catalog, collected_archive


def relationship_snapshot():
    archive = archive_bytes()
    transport = SequenceTransport(
        [
            response(
                catalog_body_with_relationship(archive_size=len(archive)),
                final_url=CATALOG_URL,
                content_type="application/json",
            ),
            response(
                RELATIONSHIP_DIAGRAM_PNG,
                final_url=RELATIONSHIP_DIAGRAM_URL,
                content_type="image/png",
            ),
        ]
    )
    catalog = fetch_state_amendment_catalog(
        transport=transport,
        retry_policy=RetryPolicy(max_attempts=1),
        sleep=lambda _seconds: None,
    )
    return fetch_state_amendment_relationship_diagram(
        catalog=catalog,
        transport=transport,
        retry_policy=RetryPolicy(max_attempts=1),
        sleep=lambda _seconds: None,
    )


class BahiaStateAmendmentPersistenceTests(unittest.TestCase):
    def test_preserves_relationship_diagram_as_immutable_source_evidence(
        self,
    ) -> None:
        self.assertTrue(
            hasattr(
                persistence_service,
                "BahiaStateAmendmentRelationshipPersistenceService",
            ),
            "o serviço ainda não preserva o diagrama oficial",
        )
        snapshot = relationship_snapshot()
        repository = FakeRepository()
        service_class = (
            persistence_service.BahiaStateAmendmentRelationshipPersistenceService
        )

        result = service_class(
            object_store=FakeObjectStore(),
            repository=repository,
        ).persist(snapshot)

        self.assertTrue(result.object_key.endswith(f"/{snapshot.body_sha256}.png"))
        self.assertEqual(len(repository.batches), 1)
        record = repository.batches[0].records[0]
        self.assertEqual(
            record.record_type,
            "bahia_state_amendment_relationship_diagram",
        )
        self.assertEqual(record.payload["territorial_key"], "not_available")
        self.assertNotIn("image_bytes", record.payload)

    def test_preserves_catalog_and_archive_as_separate_immutable_artifacts(
        self,
    ) -> None:
        catalog, archive = snapshots()
        repository = FakeRepository()
        object_store = FakeObjectStore()

        catalog_result = BahiaStateAmendmentCatalogPersistenceService(
            object_store=object_store,
            repository=repository,
        ).persist(catalog)
        archive_result = BahiaStateAmendmentArchivePersistenceService(
            object_store=object_store,
            repository=repository,
        ).persist(archive)

        self.assertTrue(catalog_result.object_key.endswith(f"/{catalog.body_sha256}.json"))
        self.assertTrue(archive_result.object_key.endswith(f"/{archive.body_sha256}.zip"))
        self.assertEqual(len(repository.batches), 2)
        self.assertEqual(
            repository.batches[0].records[0].record_type,
            "bahia_state_amendment_catalog_resource",
        )
        archive_records = repository.batches[1].records
        self.assertEqual(len(archive_records), 5)
        self.assertTrue(
            all(
                record.record_type == "bahia_state_amendment_archive_member"
                for record in archive_records
            )
        )
        self.assertTrue(all("rows" not in record.payload for record in archive_records))

    def test_refuses_archive_manifest_that_no_longer_matches_the_zip(self) -> None:
        _catalog, archive = snapshots()
        with self.assertRaisesRegex(ArtifactIntegrityError, "ZIP estadual"):
            BahiaStateAmendmentArchivePersistenceService(
                object_store=FakeObjectStore(),
                repository=FakeRepository(),
            ).persist(replace(archive, items=()))

    def test_refuses_catalog_changed_during_storage_round_trip(self) -> None:
        catalog, _archive = snapshots()
        with self.assertRaisesRegex(ArtifactIntegrityError, "restaurado"):
            BahiaStateAmendmentCatalogPersistenceService(
                object_store=FakeObjectStore(tamper=True),
                repository=FakeRepository(),
            ).persist(catalog)


if __name__ == "__main__":
    unittest.main()
