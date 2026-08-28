from __future__ import annotations

import hashlib
import unittest
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime

from barreiras_collectors.commands.audit_tcm_ba_document_batch import (
    TcmBaDocumentAuditError,
    audit_tcm_ba_document_batch,
)
from barreiras_collectors.persistence.models import (
    TcmBaDocumentAuditArtifact,
    TcmBaDocumentAuditSnapshot,
)
from barreiras_collectors.persistence.postgres import PostgresCollectionRepository

PREPARE_BODY = (
    b'<?xml version="1.0"?><partial-response>'
    b'<redirect url="downloadDocumento.seam"/></partial-response>'
)
PDF_BODY = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def artifact(
    *,
    artifact_id: str,
    parent_artifact_id: str,
    role: str,
    body: bytes,
) -> TcmBaDocumentAuditArtifact:
    digest = hashlib.sha256(body).hexdigest()
    schema_name, content_type, suffix = (
        (
            "tcm-ba-document-download-prepare",
            "application/xml",
            "xml",
        )
        if role == "prepare"
        else ("tcm-ba-monthly-document", "application/pdf", "pdf")
    )
    return TcmBaDocumentAuditArtifact(
        artifact_id=artifact_id,
        parent_artifact_id=parent_artifact_id,
        object_key=(
            f"tcm-ba/monthly-documents/2021/01/{role}/sha256/"
            f"{digest[:2]}/{digest}.{suffix}"
        ),
        sha256=digest,
        byte_size=len(body),
        content_type=content_type,
        http_status=200,
        schema_name=schema_name,
        source_record_key="tcm-ba:document:01/2021:one",
    )


def valid_snapshot() -> tuple[TcmBaDocumentAuditSnapshot, dict[str, bytes]]:
    prepare = artifact(
        artifact_id="prepare-1",
        parent_artifact_id="catalog-1",
        role="prepare",
        body=PREPARE_BODY,
    )
    pdf = artifact(
        artifact_id="pdf-1",
        parent_artifact_id="prepare-1",
        role="pdf",
        body=PDF_BODY,
    )
    snapshot = TcmBaDocumentAuditSnapshot(
        competence="01/2021",
        partition_status="partial",
        partition_completed_at=datetime(2026, 8, 28, tzinfo=UTC),
        observed_records=6,
        checkpoint={
            "expected_documents": 11,
            "preserved_documents": 6,
            "remaining_documents": 5,
        },
        run_status="partial",
        metrics={
            "collection_outcome": "partial",
            "documents_downloaded": 1,
            "documents_preserved_before": 5,
            "documents_preserved_after": 6,
            "documents_remaining": 5,
        },
        artifacts=(prepare, pdf),
        catalog_links=1,
        current_open_failures=0,
        historical_open_failures=2,
    )
    return snapshot, {
        prepare.object_key: PREPARE_BODY,
        pdf.object_key: PDF_BODY,
    }


class FakeRepository:
    def __init__(self, snapshot: TcmBaDocumentAuditSnapshot) -> None:
        self.snapshot = snapshot

    def tcm_ba_document_audit_snapshot(self, *, competence: str):
        if competence != self.snapshot.competence:
            raise AssertionError("competência inesperada")
        return self.snapshot


class FakeObjectStore:
    def __init__(self, bodies: dict[str, bytes]) -> None:
        self.bodies = bodies
        self.read_keys: list[str] = []

    def read(self, object_key: str) -> bytes:
        self.read_keys.append(object_key)
        return self.bodies[object_key]


class TcmBaDocumentBatchAuditTests(unittest.TestCase):
    def test_approves_partial_batch_after_reading_every_private_object(self) -> None:
        snapshot, bodies = valid_snapshot()
        store = FakeObjectStore(bodies)

        summary = audit_tcm_ba_document_batch(
            competence="01/2021",
            repository=FakeRepository(snapshot),
            object_store=store,
        )

        self.assertEqual(summary.coverage_status, "partial")
        self.assertEqual(summary.preserved_documents, 6)
        self.assertEqual(summary.remaining_documents, 5)
        self.assertEqual(summary.physical_objects_verified, 2)
        self.assertEqual(
            summary.physical_bytes_verified, sum(map(len, bodies.values()))
        )
        self.assertEqual(set(store.read_keys), set(bodies))
        self.assertEqual(summary.historical_open_failures, 2)

    def test_approves_batch_that_closes_the_month(self) -> None:
        snapshot, bodies = valid_snapshot()
        snapshot = replace(
            snapshot,
            partition_status="complete",
            checkpoint={
                "expected_documents": 6,
                "preserved_documents": 6,
                "remaining_documents": 0,
            },
            run_status="succeeded",
            metrics={
                **snapshot.metrics,
                "collection_outcome": "complete",
                "documents_remaining": 0,
            },
        )

        summary = audit_tcm_ba_document_batch(
            competence="01/2021",
            repository=FakeRepository(snapshot),
            object_store=FakeObjectStore(bodies),
        )

        self.assertEqual(summary.coverage_status, "complete")
        self.assertEqual(summary.remaining_documents, 0)

    def test_rejects_tampered_physical_bytes(self) -> None:
        snapshot, bodies = valid_snapshot()
        first_key = next(iter(bodies))
        bodies[first_key] = b"x" * len(bodies[first_key])

        with self.assertRaisesRegex(TcmBaDocumentAuditError, "SHA-256"):
            audit_tcm_ba_document_batch(
                competence="01/2021",
                repository=FakeRepository(snapshot),
                object_store=FakeObjectStore(bodies),
            )

    def test_rejects_divergent_counters_and_boolean_metrics(self) -> None:
        snapshot, bodies = valid_snapshot()
        for broken in (
            replace(snapshot, observed_records=7),
            replace(
                snapshot,
                metrics={**snapshot.metrics, "documents_downloaded": True},
            ),
        ):
            with self.subTest(snapshot=broken):
                with self.assertRaises(TcmBaDocumentAuditError):
                    audit_tcm_ba_document_batch(
                        competence="01/2021",
                        repository=FakeRepository(broken),
                        object_store=FakeObjectStore(bodies),
                    )

    def test_rejects_open_failure_or_broken_lineage(self) -> None:
        snapshot, bodies = valid_snapshot()
        pdf = replace(snapshot.artifacts[1], parent_artifact_id="other")
        for broken in (
            replace(snapshot, current_open_failures=1),
            replace(snapshot, artifacts=(snapshot.artifacts[0], pdf)),
        ):
            with self.subTest(snapshot=broken):
                with self.assertRaises(TcmBaDocumentAuditError):
                    audit_tcm_ba_document_batch(
                        competence="01/2021",
                        repository=FakeRepository(broken),
                        object_store=FakeObjectStore(bodies),
                    )

    def test_rejects_non_content_addressed_key_and_wrong_schema(self) -> None:
        snapshot, bodies = valid_snapshot()
        prepare = snapshot.artifacts[0]
        for broken_prepare in (
            replace(prepare, object_key="tcm-ba/monthly-documents/bad.xml"),
            replace(prepare, schema_name="unknown"),
        ):
            broken = replace(
                snapshot,
                artifacts=(broken_prepare, snapshot.artifacts[1]),
            )
            with self.subTest(artifact=broken_prepare):
                with self.assertRaises(TcmBaDocumentAuditError):
                    audit_tcm_ba_document_batch(
                        competence="01/2021",
                        repository=FakeRepository(broken),
                        object_store=FakeObjectStore(bodies),
                    )


class QueryResult:
    def __init__(self, *, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class SequenceConnection:
    def __init__(self, results) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, object]] = []
        self.closed = False

    def transaction(self):
        return nullcontext()

    def execute(self, query, params=None):
        self.calls.append((query, params))
        if query.strip().lower().startswith("set "):
            return QueryResult()
        return self.results.pop(0)

    def close(self):
        self.closed = True


class TcmBaDocumentAuditRepositoryTests(unittest.TestCase):
    def test_reads_snapshot_inside_read_only_transaction(self) -> None:
        snapshot, _ = valid_snapshot()
        connection = SequenceConnection(
            [
                QueryResult(
                    row={
                        "status": snapshot.partition_status,
                        "completed_at": snapshot.partition_completed_at,
                        "observed_records": snapshot.observed_records,
                        "checkpoint": snapshot.checkpoint,
                        "run_id": "11111111-1111-1111-1111-111111111111",
                        "run_status": snapshot.run_status,
                        "metrics": snapshot.metrics,
                    }
                ),
                QueryResult(
                    rows=[
                        {
                            "artifact_id": item.artifact_id,
                            "parent_artifact_id": item.parent_artifact_id,
                            "object_key": item.object_key,
                            "sha256": item.sha256,
                            "byte_size": item.byte_size,
                            "content_type": item.content_type,
                            "http_status": item.http_status,
                            "schema_name": item.schema_name,
                            "source_record_key": item.source_record_key,
                        }
                        for item in snapshot.artifacts
                    ]
                ),
                QueryResult(row={"total": 1}),
                QueryResult(row={"total": 0}),
                QueryResult(row={"total": 2}),
            ]
        )

        result = PostgresCollectionRepository(
            lambda: connection
        ).tcm_ba_document_audit_snapshot(competence="01/2021")

        self.assertEqual(result, snapshot)
        self.assertEqual(connection.calls[0][0], "set transaction read only")
        self.assertIn("schema_name", connection.calls[3][0])
        self.assertIn("parent_artifact_id", connection.calls[3][0])
        self.assertTrue(connection.closed)


if __name__ == "__main__":
    unittest.main()
