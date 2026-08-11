from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

from barreiras_normalization.public_obligation_publisher import (
    PUBLIC_OBLIGATION_JOB_TYPE,
    PostgresPublicObligationPublicationRepository,
    PublicObligationArtifact,
    PublicObligationPublisher,
)
from barreiras_normalization.revenue_publisher import ArtifactMismatchError

FIXTURE_TEXT = (
    Path(__file__).parents[2]
    / "fixtures"
    / "documents"
    / "restos-a-pagar-summary-sample.txt"
).read_text(encoding="utf-8")
PDF_BODY = b"%PDF-1.7 deterministic-public-obligation-fixture"


class FakeReader:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self, object_key: str) -> bytes:
        del object_key
        return self.body


class FakeRepository:
    def __init__(self) -> None:
        self.inserted = []

    def persist_validated_summary(self, artifact, summary) -> int:
        if self.inserted:
            return 0
        self.inserted.append((artifact, summary))
        return 1


class FakeRows:
    def __init__(self, rows) -> None:
        self.rows = rows

    def fetchall(self):
        return self.rows


class CapturingConnection:
    def __init__(self, rows) -> None:
        self.rows = rows
        self.query = ""
        self.parameters = ()
        self.closed = False

    def execute(self, query, parameters):
        self.query = query
        self.parameters = parameters
        return FakeRows(self.rows)

    def close(self):
        self.closed = True


def artifact_for(body: bytes = PDF_BODY) -> PublicObligationArtifact:
    return PublicObligationArtifact(
        id="00000000-0000-4000-8000-000000000921",
        sha256=hashlib.sha256(body).hexdigest(),
        object_key="municipal-transparency/documents/balancete-junho-2026.pdf",
        byte_size=len(body),
        parent_record_id="00000000-0000-4000-8000-000000000922",
        source_url="https://barreiras.mtransparente.com.br/balancete-junho-2026.pdf",
        fiscal_year=2026,
        reference_month=6,
    )


class PublicObligationPublisherTests(unittest.TestCase):
    def test_failure_job_type_is_versioned_for_auditable_retry(self):
        self.assertEqual(
            PUBLIC_OBLIGATION_JOB_TYPE,
            "public_obligation_balancete_publication/1.1.0",
        )

    def test_pending_documents_accepts_reference_keys_from_current_api(self):
        connection = CapturingConnection(
            [
                {
                    "id": "00000000-0000-4000-8000-000000000923",
                    "sha256": "a" * 64,
                    "object_key": "municipal-transparency/documents/junho.pdf",
                    "byte_size": 5034253,
                    "parent_record_id": "00000000-0000-4000-8000-000000000924",
                    "source_url": (
                        "https://barreiras.mtransparente.com.br/admin/data/"
                        "BALANCETE030826185954.pdf"
                    ),
                    "fiscal_year": 2026,
                    "reference_month": 6,
                }
            ]
        )
        repository = PostgresPublicObligationPublicationRepository(
            lambda: connection
        )

        documents = repository.pending_documents(
            limit=1,
            fiscal_year_from=2026,
            fiscal_year_to=2026,
        )

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].fiscal_year, 2026)
        self.assertEqual(documents[0].reference_month, 6)
        normalized_query = (
            " ".join(connection.query.split())
            .replace("( ", "(")
            .replace(" )", ")")
        )
        self.assertIn(
            "coalesce(record.payload ->> 'ano', record.payload ->> 'ano_ref')",
            normalized_query,
        )
        self.assertIn(
            "coalesce(record.payload ->> 'mes', record.payload ->> 'mes_ref')",
            normalized_query,
        )
        self.assertEqual(
            connection.parameters,
            (2026, 2026, PUBLIC_OBLIGATION_JOB_TYPE, 1),
        )
        self.assertTrue(connection.closed)

    def test_rejects_tampered_pdf_before_persisting(self):
        repository = FakeRepository()
        publisher = PublicObligationPublisher(
            object_reader=FakeReader(b"tampered"),
            repository=repository,
            text_extractor=lambda _body: FIXTURE_TEXT,
        )

        with self.assertRaises(ArtifactMismatchError):
            publisher.publish(artifact_for())
        self.assertEqual(repository.inserted, [])

    def test_publishes_exact_period_once_and_replay_is_idempotent(self):
        repository = FakeRepository()
        publisher = PublicObligationPublisher(
            object_reader=FakeReader(PDF_BODY),
            repository=repository,
            text_extractor=lambda _body: FIXTURE_TEXT,
        )

        first = publisher.publish(artifact_for())
        second = publisher.publish(artifact_for())

        self.assertEqual(first.status, "published")
        self.assertEqual(second.status, "already_published")
        self.assertEqual(len(repository.inserted), 1)
        _, summary = repository.inserted[0]
        self.assertEqual(summary.period_end.isoformat(), "2026-06-30")
        self.assertEqual(str(summary.payments_period_amount), "3683221.97")


if __name__ == "__main__":
    unittest.main()
