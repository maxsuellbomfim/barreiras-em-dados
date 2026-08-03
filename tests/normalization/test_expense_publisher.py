from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

from barreiras_normalization.expense_publisher import (
    ExpenseArtifact,
    ExpenseReportPublisher,
)
from barreiras_normalization.revenue_publisher import ArtifactMismatchError

FIXTURE_TEXT = (
    Path(__file__).parents[2]
    / "fixtures"
    / "documents"
    / "financial-expense-report-sample.txt"
).read_text(encoding="utf-8")
PDF_BODY = b"%PDF-1.7 deterministic-expense-fixture"


class FakeReader:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self, object_key: str) -> bytes:
        del object_key
        return self.body


class FakeRepository:
    def __init__(self) -> None:
        self.inserted_batches = []

    def persist_validated_report(self, artifact, batch) -> int:
        if self.inserted_batches:
            return 0
        self.inserted_batches.append((artifact, batch))
        return len(batch.rows)


def artifact_for(body: bytes = PDF_BODY) -> ExpenseArtifact:
    return ExpenseArtifact(
        id="00000000-0000-4000-8000-000000000911",
        sha256=hashlib.sha256(body).hexdigest(),
        object_key="municipal-transparency/documents/expense-example.pdf",
        byte_size=len(body),
        parent_record_id="00000000-0000-4000-8000-000000000912",
        source_url="https://barreiras.mtransparente.com.br/expense-example.pdf",
    )


class ExpensePublisherTests(unittest.TestCase):
    def test_publisher_rejects_tampered_pdf_before_insert(self) -> None:
        repository = FakeRepository()
        publisher = ExpenseReportPublisher(
            object_reader=FakeReader(b"tampered"),
            repository=repository,
            text_extractor=lambda _body: FIXTURE_TEXT,
        )

        with self.assertRaises(ArtifactMismatchError):
            publisher.publish(artifact_for())
        self.assertEqual(repository.inserted_batches, [])

    def test_publisher_replays_without_duplicate_lines(self) -> None:
        repository = FakeRepository()
        publisher = ExpenseReportPublisher(
            object_reader=FakeReader(PDF_BODY),
            repository=repository,
            text_extractor=lambda _body: FIXTURE_TEXT,
        )

        first = publisher.publish(artifact_for())
        second = publisher.publish(artifact_for())

        self.assertEqual(first.status, "published")
        self.assertEqual(first.published_lines, 3)
        self.assertEqual(second.status, "already_published")
        self.assertEqual(second.published_lines, 0)
        self.assertEqual(len(repository.inserted_batches), 1)


if __name__ == "__main__":
    unittest.main()
