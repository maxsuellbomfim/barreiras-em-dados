from __future__ import annotations

import unittest
from dataclasses import replace
from types import SimpleNamespace

from barreiras_collectors.connectors.tcm_ba import TcmBaPublicAccountsClient
from barreiras_collectors.persistence.models import ArtifactIntegrityError
from barreiras_collectors.persistence.tcm_ba import TcmBaCatalogPersistenceService

from tests.collectors.test_tcm_ba import (
    DETAIL_1,
    DETAIL_2,
    SEARCH,
    SequenceSessionTransport,
    _form,
    _partial,
    _state_only,
)


class FakeObjectStore:
    def __init__(self, *, tamper: bool = False) -> None:
        self.objects: dict[str, bytes] = {}
        self.content_types: dict[str, str] = {}
        self.tamper = tamper

    def put_if_absent(self, *, object_key, body, content_type, expected_sha256):
        created = object_key not in self.objects
        self.objects.setdefault(object_key, body)
        self.content_types.setdefault(object_key, content_type)
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
            collection_run_id=f"run-{len(self.batches)}",
            raw_artifact_id=f"artifact-{len(self.batches)}",
            inserted_records=len(batch.records),
            existing_records=0,
        )


def catalog():
    transport = SequenceSessionTransport(
        [
            _form(monthly=False, year=False, city=False),
            _state_only("period-preflight-state"),
            _partial(_form(monthly=True, year=False, city=False), "period-state"),
            _state_only("year-preflight-state"),
            _partial(_form(monthly=True, year=True, city=False), "year-state"),
            _state_only("city-preflight-state"),
            _partial(_form(monthly=True, year=True, city=True), "city-state"),
            _state_only("unit-preflight-state"),
            _partial(
                _form(monthly=True, year=True, city=False, unit=True),
                "unit-state",
            ),
            _partial(SEARCH, "search-state"),
            _partial(DETAIL_1, "detail-state-1"),
            _partial(
                DETAIL_2,
                "detail-state-2",
                update_id="consultaPublicaTabPanel:tabelaDocumentos",
            ),
        ]
    )
    return TcmBaPublicAccountsClient(
        transport=transport,
        requests_per_minute=600,
    ).fetch_monthly_catalog(year=2023, month=4)


class TcmBaCatalogPersistenceTests(unittest.TestCase):
    def test_preserves_every_response_and_emits_submission_and_documents(self) -> None:
        repository = FakeRepository()
        snapshot = catalog()

        result = TcmBaCatalogPersistenceService(
            object_store=FakeObjectStore(),
            repository=repository,
        ).persist(snapshot)

        self.assertEqual(result.artifacts, len(snapshot.interactions))
        self.assertEqual(result.inserted_records, 12)
        self.assertEqual(len(repository.batches), len(snapshot.interactions))
        self.assertTrue(
            all(
                batch.object_key.startswith("tcm-ba/monthly/2023/04/sha256/")
                for batch in repository.batches
            )
        )
        records = [record for batch in repository.batches for record in batch.records]
        self.assertEqual(records[0].record_type, "tcm_ba_monthly_submission")
        self.assertEqual(
            sum(record.record_type == "tcm_ba_monthly_document" for record in records),
            11,
        )

    def test_refuses_bytes_changed_after_storage_round_trip(self) -> None:
        with self.assertRaisesRegex(ArtifactIntegrityError, "restaurada"):
            TcmBaCatalogPersistenceService(
                object_store=FakeObjectStore(tamper=True),
                repository=FakeRepository(),
            ).persist(catalog())

    def test_normalizes_jsf_xml_mime_type_for_the_bucket(self) -> None:
        store = FakeObjectStore()
        snapshot = catalog()
        xml_interaction = replace(
            snapshot.interactions[1],
            response_headers={"Content-Type": "text/xml; charset=UTF-8"},
        )
        snapshot = replace(
            snapshot,
            interactions=(
                snapshot.interactions[0],
                xml_interaction,
                *snapshot.interactions[2:],
            ),
        )

        result = TcmBaCatalogPersistenceService(
            object_store=store,
            repository=FakeRepository(),
        ).persist(snapshot)

        self.assertIn("application/xml", store.content_types.values())
        self.assertNotIn("text/xml", store.content_types.values())
        for object_key, content_type in store.content_types.items():
            expected_suffix = ".xml" if content_type == "application/xml" else ".html"
            self.assertTrue(object_key.endswith(expected_suffix))
        self.assertEqual(len(result.object_keys), len(store.content_types))


if __name__ == "__main__":
    unittest.main()
