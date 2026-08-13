from __future__ import annotations

import unittest
from dataclasses import replace
from types import SimpleNamespace

from barreiras_collectors.connectors.transferegov_historical_amendments import (
    fetch_historical_amendments,
)
from barreiras_collectors.persistence.models import ArtifactIntegrityError
from barreiras_collectors.persistence.service import (
    TransferegovHistoricalAmendmentPersistenceService,
)
from barreiras_collectors.resilience import RetryPolicy

from tests.collectors.test_transferegov_historical_amendments import (
    DownloadTransport,
    amendment_row,
    archive_bytes,
    catalog_entry,
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
    body = archive_bytes(
        [
            amendment_row(),
            amendment_row(ID_PROPOSTA="9999", NR_EMENDA="other"),
        ]
    )
    return fetch_historical_amendments(
        catalog_entry=catalog_entry(body),
        proposal_ids=frozenset({"9001"}),
        transport=DownloadTransport(download_response(body)),
        retry_policy=RetryPolicy(max_attempts=1),
        sleep=lambda _seconds: None,
    )


class HistoricalAmendmentPersistenceTests(unittest.TestCase):
    def test_preserves_zip_and_emits_versioned_minimized_records(self) -> None:
        repository = FakeRepository()
        collected = snapshot()

        result = TransferegovHistoricalAmendmentPersistenceService(
            object_store=FakeObjectStore(),
            repository=repository,
        ).persist(collected)

        self.assertTrue(result.object_key.endswith(f"/{collected.body_sha256}.zip"))
        records = repository.batches[0].records
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].record_type, "transferegov_historical_amendment")
        self.assertEqual(
            records[0].parser_version,
            "transferegov-historical-amendments/1.0.0",
        )
        self.assertTrue(
            records[0].source_record_key.startswith(
                "transferegov:historical-amendment:9001:"
            )
        )
        self.assertNotIn("beneficiario_identificador", records[0].payload)

    def test_refuses_items_that_do_not_match_preserved_archive_and_scope(self) -> None:
        collected = snapshot()
        with self.assertRaisesRegex(ArtifactIntegrityError, "ZIP preservado"):
            TransferegovHistoricalAmendmentPersistenceService(
                object_store=FakeObjectStore(),
                repository=FakeRepository(),
            ).persist(replace(collected, items=()))

    def test_refuses_archive_changed_after_storage_round_trip(self) -> None:
        with self.assertRaisesRegex(ArtifactIntegrityError, "restaurado"):
            TransferegovHistoricalAmendmentPersistenceService(
                object_store=FakeObjectStore(tamper=True),
                repository=FakeRepository(),
            ).persist(snapshot())


if __name__ == "__main__":
    unittest.main()
