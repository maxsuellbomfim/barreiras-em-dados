from __future__ import annotations

import hashlib
import json
import unittest
from datetime import date
from types import SimpleNamespace

from barreiras_collectors.connectors.gazette_documents import CollectedDocument
from barreiras_collectors.connectors.municipal_transparency import (
    iter_resource_pages,
)
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.persistence.models import (
    ArtifactIntegrityError,
    OfficialDocumentSearchInput,
)
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
        self.document_batches = []
        self.search_batches = []

    def persist(self, batch):
        self.batches.append(batch)
        return SimpleNamespace(
            collection_run_id="run",
            raw_artifact_id="artifact",
            inserted_records=len(batch.records),
            existing_records=0,
        )

    def persist_document(self, batch):
        self.document_batches.append(batch)
        return SimpleNamespace(raw_artifact_id="document-artifact", created=True)

    def persist_official_document_searches(self, batch):
        self.search_batches.append(batch)
        return SimpleNamespace(
            inserted_searches=len(batch.searches),
            existing_searches=0,
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
    def test_persists_monthly_search_with_preserved_response_lineage(self) -> None:
        repository = FakeRepository()
        service = MunicipalTransparencyPersistenceService(
            object_store=FakeObjectStore(),
            repository=repository,
        )
        page = page_fixture()
        page_result = service.persist(page)

        result = service.persist_official_document_searches(
            source_code="prefeitura-barreiras-transparencia",
            endpoint_code="dados-abertos-api",
            resource="balancetes",
            searches=(
                OfficialDocumentSearchInput(
                    fiscal_year=2022,
                    reference_month=3,
                    period_start=date(2022, 3, 1),
                    period_end=date(2022, 3, 31),
                    search_status="not_found",
                    match_count=0,
                ),
            ),
            page_evidence=((page_result, page),),
        )

        self.assertEqual(result.inserted_searches, 1)
        batch = repository.search_batches[0]
        self.assertEqual(batch.evidence_artifacts[0].raw_artifact_id, "artifact")
        self.assertEqual(batch.evidence_artifacts[0].sha256, page.body_sha256)
        self.assertEqual(batch.methodology_version, "official-document-search/1.0.0")

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

    def test_persists_pdf_as_child_artifact_with_municipal_schema(self) -> None:
        repository = FakeRepository()
        store = FakeObjectStore()
        service = MunicipalTransparencyPersistenceService(
            object_store=store,
            repository=repository,
        )
        page = page_fixture()
        page_result = service.persist(page)
        body = b"%PDF-1.7 documento financeiro"
        document = CollectedDocument(
            role="pdf",
            source_url="https://barreiras.mtransparente.com.br/arquivo.pdf",
            final_url="https://barreiras.mtransparente.com.br/arquivo.pdf",
            requested_at="2026-08-02T12:00:00+00:00",
            received_at="2026-08-02T12:00:01+00:00",
            attempts=1,
            http_status=200,
            body_sha256=hashlib.sha256(body).hexdigest(),
            body_size_bytes=len(body),
            media_type="application/pdf",
            response_headers={"content-type": "application/pdf"},
            raw_body=body,
        )

        result = service.persist_document(
            page_result=page_result,
            record=service.record_input(page, index=0, item=page.items[0]),
            document=document,
            source_code="prefeitura-barreiras-transparencia",
            endpoint_code="dados-abertos-api",
        )

        self.assertTrue(result.artifact_created)
        self.assertTrue(result.object_key.startswith("municipal-transparency/documents/"))
        self.assertEqual(
            repository.document_batches[0].document_schema_name,
            "municipal-transparency-document",
        )
        self.assertEqual(
            repository.document_batches[0].parent_artifact_id,
            page_result.raw_artifact_id,
        )


if __name__ == "__main__":
    unittest.main()
