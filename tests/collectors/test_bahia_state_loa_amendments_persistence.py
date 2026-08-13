from __future__ import annotations

import json
import unittest
from dataclasses import replace
from types import SimpleNamespace

from barreiras_collectors.connectors.bahia_state_loa_amendments import (
    YEARLY_ANNEXES,
    fetch_state_loa_amendment_annex,
)
from barreiras_collectors.persistence.models import (
    ArtifactIntegrityError,
    PersistenceBatch,
)
from barreiras_collectors.persistence.postgres import PostgresCollectionRepository
from barreiras_collectors.persistence.service import (
    BahiaStateLoaAmendmentAnnexPersistenceService,
)
from barreiras_collectors.resilience import RetryPolicy

from tests.collectors.test_bahia_state_loa_amendments import (
    SequenceTransport,
    pdf_bytes,
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


def snapshot(year: int = 2025):
    contract = YEARLY_ANNEXES[year]
    body = pdf_bytes(f"loa-{year}")
    return fetch_state_loa_amendment_annex(
        year,
        transport=SequenceTransport([response(body, final_url=contract.url)]),
        retry_policy=RetryPolicy(max_attempts=1),
        sleep=lambda _seconds: None,
    )


class BahiaStateLoaAmendmentPersistenceTests(unittest.TestCase):
    def test_preserves_one_immutable_pdf_and_one_manifest_record(self) -> None:
        collected = snapshot()
        repository = FakeRepository()

        result = BahiaStateLoaAmendmentAnnexPersistenceService(
            object_store=FakeObjectStore(),
            repository=repository,
        ).persist(collected)

        self.assertEqual(
            result.object_key,
            (
                "bahia/loa-emendas-estaduais/2025/sha256/"
                f"{collected.body_sha256[:2]}/{collected.body_sha256}.pdf"
            ),
        )
        self.assertEqual(len(repository.batches), 1)
        record = repository.batches[0].records[0]
        self.assertEqual(record.record_type, "bahia_state_loa_amendment_annex")
        self.assertEqual(record.payload["fiscal_year"], 2025)
        self.assertEqual(record.payload["budget_stage"], "authorized")
        self.assertNotIn("amount", record.payload)

    def test_refuses_manifest_or_restored_bytes_that_do_not_match(self) -> None:
        collected = snapshot()
        with self.assertRaisesRegex(ArtifactIntegrityError, "manifesto"):
            BahiaStateLoaAmendmentAnnexPersistenceService(
                object_store=FakeObjectStore(),
                repository=FakeRepository(),
            ).persist(replace(collected, items=()))
        with self.assertRaisesRegex(ArtifactIntegrityError, "restaurado"):
            BahiaStateLoaAmendmentAnnexPersistenceService(
                object_store=FakeObjectStore(tamper=True),
                repository=FakeRepository(),
            ).persist(collected)

    def test_postgres_records_the_pdf_as_document_with_source_metadata(self) -> None:
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
            object_key="bahia/loa-emendas-estaduais/2025/file.pdf",
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

        self.assertIn("document", connection.parameters)
        metadata = json.loads(connection.parameters[-1])
        self.assertEqual(metadata["fiscal_year"], 2025)
        self.assertEqual(metadata["annex_code"], "III")
        self.assertEqual(metadata["budget_stage"], "authorized")


if __name__ == "__main__":
    unittest.main()
