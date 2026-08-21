from __future__ import annotations

import unittest
from types import SimpleNamespace

from barreiras_collectors.connectors.cgu_federal_amendment_documents import (
    fetch_cgu_federal_amendment_documents,
)
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.persistence.service import (
    CGUFederalAmendmentDocumentPersistenceService,
)
from barreiras_collectors.resilience import RetryPolicy

from tests.collectors.test_cgu_federal_amendment_documents import (
    DownloadTransport,
    archive_bytes,
    document_row,
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


def snapshot():
    body = archive_bytes(2025, [document_row()])
    response = HttpResponse(
        status=200,
        headers={
            "Content-Type": "application/x-zip-compressed",
            "Content-Length": str(len(body)),
            "ETag": '"official-etag"',
            "Last-Modified": "Wed, 05 Aug 2026 17:47:20 GMT",
        },
        body=body,
        final_url=(
            "https://dadosabertos-download.cgu.gov.br/PortalDaTransparencia/"
            "saida/emendas-parlamentares-documentos/"
            "2025_EmendasParlamentaresPorDocumento.zip"
        ),
    )
    return fetch_cgu_federal_amendment_documents(
        2025,
        transport=DownloadTransport(response),
        retry_policy=RetryPolicy(max_attempts=1),
        sleep=lambda _seconds: None,
    )


class CGUFederalAmendmentDocumentPersistenceTests(unittest.TestCase):
    def test_preserves_annual_zip_and_emits_document_records(self) -> None:
        repository = FakeRepository()
        collected = snapshot()

        result = CGUFederalAmendmentDocumentPersistenceService(
            object_store=FakeObjectStore(),
            repository=repository,
        ).persist(collected)

        self.assertEqual(
            result.object_key,
            (
                "cgu/emendas-federais/documentos/2025/sha256/"
                f"{collected.body_sha256[:2]}/{collected.body_sha256}.zip"
            ),
        )
        record = repository.batches[0].records[0]
        self.assertEqual(record.record_type, "cgu_federal_amendment_document")
        self.assertEqual(
            record.parser_version,
            "cgu-federal-amendment-documents/1.0.0",
        )
        self.assertTrue(
            record.source_record_key.startswith(
                "cgu:federal-amendment-document:2025:202544600002:"
            )
        )
        self.assertEqual(record.payload["expense_stage"], "commitment")


if __name__ == "__main__":
    unittest.main()
