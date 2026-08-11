from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

from barreiras_normalization.public_obligation_publisher import (
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
