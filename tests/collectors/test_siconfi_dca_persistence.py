from __future__ import annotations

import unittest
from dataclasses import replace
from types import SimpleNamespace

from barreiras_collectors.connectors.siconfi import fetch_siconfi_dca
from barreiras_collectors.persistence.models import ArtifactIntegrityError
from barreiras_collectors.persistence.service import SiconfiDcaPersistenceService
from barreiras_collectors.resilience import RetryPolicy

from tests.collectors.test_siconfi_dca import (
    CountingLimiter,
    SequenceTransport,
    dca_item,
    page_body,
    response,
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
        return body + b"tampered" if self.tamper else body


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
    body = page_body([dca_item()])
    return fetch_siconfi_dca(
        year=2021,
        transport=SequenceTransport(
            [
                response(
                    body,
                    final_url=(
                        "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca"
                        "?an_exercicio=2021&id_ente=2903201&limit=5000&offset=0"
                    ),
                )
            ]
        ),
        rate_limiter=CountingLimiter(),
        retry_policy=RetryPolicy(max_attempts=1),
        sleep=lambda _seconds: None,
    )[0]


class SiconfiDcaPersistenceTests(unittest.TestCase):
    def test_preserves_raw_page_and_emits_versioned_source_rows(self) -> None:
        repository = FakeRepository()
        page = snapshot()

        result = SiconfiDcaPersistenceService(
            object_store=FakeObjectStore(),
            repository=repository,
        ).persist(page)

        self.assertEqual(
            result.object_key,
            (
                "siconfi/dca/2021/sha256/"
                f"{page.body_sha256[:2]}/{page.body_sha256}.json"
            ),
        )
        record = repository.batches[0].records[0]
        self.assertEqual(record.record_type, "siconfi_dca_line")
        self.assertEqual(record.parser_version, "siconfi-dca-page/1.0.0")
        self.assertTrue(record.source_record_key.startswith("siconfi:dca:2021:"))
        self.assertEqual(record.payload["valor"], "163212630.95")

    def test_refuses_rows_that_no_longer_match_the_preserved_json(self) -> None:
        page = snapshot()
        with self.assertRaisesRegex(ArtifactIntegrityError, "bruto preservado"):
            SiconfiDcaPersistenceService(
                object_store=FakeObjectStore(),
                repository=FakeRepository(),
            ).persist(replace(page, items=()))

    def test_refuses_page_changed_after_storage_round_trip(self) -> None:
        with self.assertRaisesRegex(ArtifactIntegrityError, "restaurada"):
            SiconfiDcaPersistenceService(
                object_store=FakeObjectStore(tamper=True),
                repository=FakeRepository(),
            ).persist(snapshot())


if __name__ == "__main__":
    unittest.main()
