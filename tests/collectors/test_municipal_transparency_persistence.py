from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from barreiras_collectors.connectors.municipal_transparency import (
    iter_resource_pages,
)
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.persistence.models import ArtifactIntegrityError
from barreiras_collectors.persistence.service import (
    MunicipalTransparencyPersistenceService,
)


class OneShotTransport:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds, max_body_bytes
        return HttpResponse(
            status=200,
            headers={"Content-Type": "application/json"},
            body=self.body,
            final_url=url,
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


def page_fixture():
    body = json.dumps(
        {
            "resource": "pdc-resumo-execucao-da-receita",
            "count": 1,
            "data": [
                {
                    "id": "sanitized-revenue-1",
                    "ano": "2026",
                    "valor_arrecadado": "0,00",
                }
            ],
        }
    ).encode()
    return next(
        iter_resource_pages(
            base_url="https://portaldatransparencia.barreiras.ba.gov.br/api",
            source_code="prefeitura-barreiras-transparencia",
            resource="pdc-resumo-execucao-da-receita",
            limit=50,
            transport=OneShotTransport(body),
            requests_per_minute=600,
            sleep=lambda _seconds: None,
        )
    )


class MunicipalTransparencyPersistenceTests(unittest.TestCase):
    def test_persists_raw_page_and_records_idempotently(self) -> None:
        repository = FakeRepository()
        service = MunicipalTransparencyPersistenceService(
            object_store=FakeObjectStore(),
            repository=repository,
        )

        result = service.persist(page_fixture())

        self.assertEqual(result.inserted_records, 1)
        batch = repository.batches[0]
        self.assertEqual(
            batch.records[0].record_type,
            "municipal_transparency_pdc-resumo-execucao-da-receita",
        )
        self.assertEqual(batch.records[0].payload["id"], "sanitized-revenue-1")
        self.assertTrue(
            batch.object_key.startswith(
                "municipal-transparency/prefeitura-barreiras-transparencia/"
            )
        )

    def test_detects_tampered_storage_before_database_write(self) -> None:
        repository = FakeRepository()
        service = MunicipalTransparencyPersistenceService(
            object_store=FakeObjectStore(tamper=True),
            repository=repository,
        )

        with self.assertRaises(ArtifactIntegrityError):
            service.persist(page_fixture())
        self.assertEqual(repository.batches, [])


if __name__ == "__main__":
    unittest.main()
