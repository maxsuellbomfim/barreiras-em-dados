from __future__ import annotations

import hashlib
import unittest
from decimal import Decimal
from pathlib import Path

from barreiras_normalization.commands.publish_revenue_reports import (
    build_completion_event,
    completion_exit_code,
)
from barreiras_normalization.revenue_publisher import (
    ArtifactMismatchError,
    PostgresRevenuePublicationRepository,
    RevenueArtifact,
    RevenueReportPublisher,
)

FIXTURE_TEXT = (
    Path(__file__).parents[2]
    / "fixtures"
    / "documents"
    / "financial-revenue-report-sample.txt"
).read_text(encoding="utf-8")
PDF_BODY = b"%PDF-1.7 deterministic-fixture"
TCM_FIXTURE_TEXT = (
    Path(__file__).parents[2]
    / "fixtures"
    / "documents"
    / "tcm-ba-analytical-revenue-sample.txt"
).read_text(encoding="utf-8")


class FakeReader:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self, object_key: str) -> bytes:
        del object_key
        return self.body


class FakeRepository:
    def __init__(self) -> None:
        self.inserted_batches = []
        self.failures = []

    def persist_validated_report(self, artifact, batch) -> int:
        if self.inserted_batches:
            return 0
        self.inserted_batches.append((artifact, batch))
        return len(batch.rows)

    def record_failure(self, artifact, *, error_code, error_detail) -> None:
        self.failures.append((artifact, error_code, error_detail))


class FakeRows:
    def __init__(self, rows=()) -> None:
        self.rows = rows

    def fetchall(self):
        return self.rows


class CapturingConnection:
    def __init__(self) -> None:
        self.query = ""
        self.parameters = ()
        self.closed = False

    def execute(self, query, parameters=()):
        self.query = query
        self.parameters = parameters
        return FakeRows()

    def close(self):
        self.closed = True


def artifact_for(body: bytes = PDF_BODY) -> RevenueArtifact:
    return RevenueArtifact(
        id="00000000-0000-4000-8000-000000000901",
        sha256=hashlib.sha256(body).hexdigest(),
        object_key="municipal-transparency/documents/example.pdf",
        byte_size=len(body),
        parent_record_id="00000000-0000-4000-8000-000000000902",
        source_url="https://barreiras.mtransparente.com.br/example.pdf",
    )


def tcm_artifact_for(body: bytes = PDF_BODY) -> RevenueArtifact:
    return RevenueArtifact(
        id="00000000-0000-4000-8000-000000000903",
        sha256=hashlib.sha256(body).hexdigest(),
        object_key="tcm-ba/monthly/2021/01/revenue-example.pdf",
        byte_size=len(body),
        parent_record_id="00000000-0000-4000-8000-000000000904",
        source_url="https://e.tcm.ba.gov.br/epp/PdfReadOnly/downloadDocumento.seam",
        source_kind="tcm_ba",
    )


class RevenuePublisherTests(unittest.TestCase):
    def test_pending_documents_retries_failed_until_dead_letter(self) -> None:
        connection = CapturingConnection()
        repository = PostgresRevenuePublicationRepository(lambda: connection)

        self.assertEqual(
            repository.pending_documents(
                limit=12,
                fiscal_year_from=2022,
                fiscal_year_to=2022,
            ),
            (),
        )

        query = " ".join(connection.query.lower().split())
        self.assertIn("job.status = 'dead_lettered'", query)
        self.assertNotIn("job.status = 'failed'", query)
        self.assertEqual(
            connection.parameters,
            (
                2022,
                2022,
                2022,
                2022,
                None,
                None,
                None,
                "financial_revenue_publication/1.2.0",
                12,
            ),
        )
        self.assertTrue(connection.closed)

    def test_pending_documents_can_target_exact_tcm_revenue_artifact(self) -> None:
        connection = CapturingConnection()
        repository = PostgresRevenuePublicationRepository(lambda: connection)

        self.assertEqual(
            repository.pending_documents(
                limit=1,
                fiscal_year_from=2021,
                fiscal_year_to=2021,
                artifact_sha256="a" * 64,
            ),
            (),
        )

        query = " ".join(connection.query.lower().split())
        self.assertNotIn("document.id::text", query)
        self.assertIn(
            "revenue.source_document_artifact_id = candidates.id",
            query,
        )
        self.assertIn("job.raw_artifact_id = candidates.id", query)
        self.assertIn("tcm_ba_candidates as", query)
        self.assertIn("tcm-ba-monthly-document", query)
        self.assertIn("tcm-ba-document-download-prepare", query)
        self.assertIn(
            "left(record.payload ->> 'category', 8) = 'pcmge016'",
            query,
        )
        self.assertIn("'tcm_ba'::text as source_kind", query)
        self.assertIn(
            "(%s::text is null or candidates.sha256 = %s::text)",
            query,
        )
        self.assertIn("%s::text is not null", query)
        self.assertIn("job.status = 'dead_lettered'", query)
        self.assertNotIn("job.status = 'failed'", query)

    def test_failure_is_retryable_until_dead_letter(self) -> None:
        connection = CapturingConnection()
        repository = PostgresRevenuePublicationRepository(lambda: connection)

        repository.record_failure(
            artifact_for(),
            error_code="RevenuePdfContractError",
            error_detail="layout histórico não reconhecido",
        )

        query = " ".join(connection.query.lower().split())
        self.assertIn("attempt_count + 1 >= raw.extraction_jobs.max_attempts", query)
        self.assertIn("then 'dead_lettered'", query)
        self.assertIn("else 'failed'", query)

    def test_command_fails_when_any_artifact_needs_review(self) -> None:
        self.assertEqual(completion_exit_code(needs_review=0), 0)
        self.assertEqual(completion_exit_code(needs_review=1), 1)

    def test_completion_event_proves_exact_revenue_artifact(self) -> None:
        event = build_completion_event(
            artifact_sha256="b" * 64,
            artifacts=1,
            published_rows=248,
            already_published=0,
            needs_review=0,
        )

        self.assertEqual(event["event"], "revenue_publication_completed")
        self.assertEqual(event["artifact_sha256"], "b" * 64)
        self.assertEqual(event["artifacts"], 1)
        self.assertEqual(event["published_rows"], 248)

    def test_publisher_rejects_tampered_pdf_before_insert(self) -> None:
        repository = FakeRepository()
        publisher = RevenueReportPublisher(
            object_reader=FakeReader(b"tampered"),
            repository=repository,
            text_extractor=lambda _body: FIXTURE_TEXT,
        )
        with self.assertRaises(ArtifactMismatchError):
            publisher.publish(artifact_for())
        self.assertEqual(repository.inserted_batches, [])

    def test_publisher_replays_without_duplicate_rows(self) -> None:
        repository = FakeRepository()
        publisher = RevenueReportPublisher(
            object_reader=FakeReader(PDF_BODY),
            repository=repository,
            text_extractor=lambda _body: FIXTURE_TEXT,
        )

        first = publisher.publish(artifact_for())
        second = publisher.publish(artifact_for())

        self.assertEqual(first.status, "published")
        self.assertEqual(first.published_rows, 3)
        self.assertEqual(second.status, "already_published")
        self.assertEqual(second.published_rows, 0)
        self.assertEqual(len(repository.inserted_batches), 1)

    def test_publisher_uses_tcm_parser_and_methodology(self) -> None:
        repository = FakeRepository()
        publisher = RevenueReportPublisher(
            object_reader=FakeReader(PDF_BODY),
            repository=repository,
            text_extractor=lambda _body: TCM_FIXTURE_TEXT,
        )

        result = publisher.publish(tcm_artifact_for())

        self.assertEqual(result.status, "published")
        self.assertEqual(result.published_rows, 2)
        batch = repository.inserted_batches[0][1]
        self.assertEqual(
            batch.methodology_version,
            "tcm-ba-analytical-revenue/1.1.0",
        )
        self.assertEqual(batch.total_period_amount, Decimal("45849799.31"))


if __name__ == "__main__":
    unittest.main()
