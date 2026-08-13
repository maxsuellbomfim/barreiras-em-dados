from __future__ import annotations

import json
import unittest
from dataclasses import replace
from types import SimpleNamespace

from barreiras_collectors.connectors.transferegov_historical_proposals import (
    fetch_historical_proposals,
)
from barreiras_collectors.persistence.models import (
    ArtifactIntegrityError,
    PersistenceBatch,
)
from barreiras_collectors.persistence.postgres import PostgresCollectionRepository
from barreiras_collectors.persistence.service import (
    TransferegovHistoricalProposalPersistenceService,
)
from barreiras_collectors.resilience import RetryPolicy

from tests.collectors.test_transferegov_historical_proposals import (
    DownloadTransport,
    archive_bytes,
    catalog_entry,
    download_response,
    proposal_row,
)


class FakeObjectStore:
    def __init__(self, *, tamper: bool = False) -> None:
        self.objects: dict[str, bytes] = {}
        self.content_types: dict[str, str] = {}
        self.tamper = tamper

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
    body = archive_bytes([proposal_row()])
    return fetch_historical_proposals(
        catalog_entry=catalog_entry(body),
        year_from=2021,
        year_to=2026,
        transport=DownloadTransport(download_response(body)),
        retry_policy=RetryPolicy(max_attempts=1),
        sleep=lambda _seconds: None,
    )


class HistoricalProposalPersistenceTests(unittest.TestCase):
    def test_preserves_zip_and_emits_safe_versioned_municipal_records(self) -> None:
        store = FakeObjectStore()
        repository = FakeRepository()
        collected = snapshot()

        result = TransferegovHistoricalProposalPersistenceService(
            object_store=store,
            repository=repository,
        ).persist(collected)

        self.assertTrue(result.object_key.endswith(f"/{collected.body_sha256}.zip"))
        self.assertEqual(
            store.content_types[result.object_key], "application/octet-stream"
        )
        records = repository.batches[0].records
        self.assertEqual(len(records), 1)
        self.assertEqual(
            records[0].source_record_key,
            "transferegov:historical-proposal:9001",
        )
        self.assertEqual(
            records[0].record_type,
            "transferegov_historical_proposal",
        )
        self.assertEqual(
            records[0].parser_version,
            "transferegov-historical-proposals/1.0.0",
        )
        self.assertNotIn("CD_AGENCIA", records[0].payload)
        self.assertNotIn("CD_CONTA", records[0].payload)
        self.assertNotIn("agencia", records[0].payload)
        self.assertNotIn("conta", records[0].payload)

    def test_refuses_items_that_do_not_match_the_preserved_zip(self) -> None:
        collected = snapshot()

        with self.assertRaisesRegex(ArtifactIntegrityError, "ZIP preservado"):
            TransferegovHistoricalProposalPersistenceService(
                object_store=FakeObjectStore(),
                repository=FakeRepository(),
            ).persist(replace(collected, items=()))

    def test_refuses_archive_changed_after_storage_round_trip(self) -> None:
        with self.assertRaisesRegex(ArtifactIntegrityError, "restaurado"):
            TransferegovHistoricalProposalPersistenceService(
                object_store=FakeObjectStore(tamper=True),
                repository=FakeRepository(),
            ).persist(snapshot())

    def test_postgres_records_the_raw_artifact_as_archive(self) -> None:
        class Result:
            @staticmethod
            def fetchone():
                return {"id": "artifact"}

        class Connection:
            def __init__(self) -> None:
                self.parameters = ()

            def execute(self, _query, parameters):
                self.parameters = parameters
                return Result()

        collected = snapshot()
        connection = Connection()
        batch = PersistenceBatch(
            page=collected,  # type: ignore[arg-type]
            object_key="transferegov/parcerias/historical/propostas/file.zip",
            artifact_idempotency_key="artifact-key",
            collector_version="collector/1.0.0",
            parser_version="parser/1.0.0",
            records=(),
        )

        PostgresCollectionRepository._artifact_id(
            connection,  # type: ignore[arg-type]
            batch,
            "endpoint",
            "run",
        )

        self.assertIn("archive", connection.parameters)
        metadata = json.loads(connection.parameters[-1])
        self.assertEqual(
            metadata["catalog_blob_url"],
            (
                "https://trsfgovprodstrgaccpublic.blob.core.windows.net/"
                "trsfgov-prod-public-data/siconv_proposta.zip"
            ),
        )
        self.assertEqual(metadata["catalog_etag"], "0x8DEF8636FB12944")


if __name__ == "__main__":
    unittest.main()
