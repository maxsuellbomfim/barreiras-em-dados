from __future__ import annotations

import hashlib
import logging
import unittest
from argparse import ArgumentTypeError
from datetime import date
from pathlib import Path

from barreiras_normalization.commands.publish_payroll_reports import (
    KnownPypdfLayoutWarningFilter,
    _parse_reference_month,
)
from barreiras_normalization.payroll_publisher import (
    PAYROLL_PUBLICATION_JOB_TYPE,
    PayrollArtifact,
    PayrollReportPublisher,
    PostgresPayrollPublicationRepository,
)
from barreiras_normalization.revenue_publisher import ArtifactMismatchError

FIXTURE_TEXT = (
    Path(__file__).parents[2]
    / "fixtures"
    / "documents"
    / "payroll-report-aggregate-sample.txt"
).read_text(encoding="utf-8")
PDF_BODY = b"%PDF-1.7 deterministic-payroll-fixture"


class FakeReader:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self, object_key: str) -> bytes:
        del object_key
        return self.body


class FakeRepository:
    def __init__(self) -> None:
        self.inserted = []

    def persist_validated_report(self, artifact, report) -> int:
        if self.inserted:
            return 0
        self.inserted.append((artifact, report))
        return 1


class FakeRows:
    def __init__(self, rows) -> None:
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


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


def artifact_for(body: bytes = PDF_BODY) -> PayrollArtifact:
    return PayrollArtifact(
        id="00000000-0000-4000-8000-000000000951",
        sha256=hashlib.sha256(body).hexdigest(),
        object_key="municipal-transparency/documents/payroll-example.pdf",
        byte_size=len(body),
        parent_record_id="00000000-0000-4000-8000-000000000952",
        source_url="https://barreiras.mtransparente.com.br/payroll-example.pdf",
        reference_month=date(2026, 7, 1),
    )


class PayrollPublisherTests(unittest.TestCase):
    def test_known_layout_warning_filter_condenses_only_recoverable_noise(
        self,
    ) -> None:
        warning_filter = KnownPypdfLayoutWarningFilter()
        known_warning = logging.LogRecord(
            name=("pypdf._text_extraction._layout_mode._fixed_width_page"),
            level=logging.WARNING,
            pathname=__file__,
            lineno=1,
            msg="Unbalanced target operations, expected %r.",
            args=(b"Q",),
            exc_info=None,
        )
        different_warning = logging.LogRecord(
            name=known_warning.name,
            level=logging.WARNING,
            pathname=__file__,
            lineno=1,
            msg="Rotated text discovered. Output will be incomplete.",
            args=(),
            exc_info=None,
        )
        same_message_as_error = logging.LogRecord(
            name=known_warning.name,
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg=known_warning.msg,
            args=known_warning.args,
            exc_info=None,
        )

        self.assertFalse(warning_filter.filter(known_warning))
        self.assertTrue(warning_filter.filter(different_warning))
        self.assertTrue(warning_filter.filter(same_message_as_error))
        self.assertEqual(warning_filter.suppressed_count, 1)

    def test_reference_month_requires_year_and_two_digit_month(self) -> None:
        self.assertEqual(_parse_reference_month("2026-07"), date(2026, 7, 1))
        for invalid in ("2026-7", "07-2026", "2026-13", "texto"):
            with self.subTest(invalid=invalid), self.assertRaises(ArgumentTypeError):
                _parse_reference_month(invalid)

    def test_failure_job_is_versioned(self) -> None:
        self.assertEqual(
            PAYROLL_PUBLICATION_JOB_TYPE,
            "payroll_report_publication/1.2.0",
        )

    def test_pending_documents_accepts_only_regular_staff_documents(self) -> None:
        connection = CapturingConnection(
            [
                {
                    "id": "00000000-0000-4000-8000-000000000951",
                    "sha256": "a" * 64,
                    "object_key": "municipal-transparency/documents/payroll.pdf",
                    "byte_size": 2478977,
                    "parent_record_id": ("00000000-0000-4000-8000-000000000952"),
                    "source_url": (
                        "https://barreiras.mtransparente.com.br/payroll.pdf"
                    ),
                    "reference_month": date(2026, 7, 1),
                }
            ]
        )
        repository = PostgresPayrollPublicationRepository(lambda: connection)

        documents = repository.pending_documents(
            limit=5,
            fiscal_year_from=2021,
            fiscal_year_to=2026,
            reference_month=date(2026, 7, 1),
        )

        self.assertEqual(documents[0].reference_month, date(2026, 7, 1))
        query = " ".join(connection.query.lower().split())
        self.assertIn("record.payload ->> 'tipo' = '1'", query)
        self.assertIn(
            "coalesce(trim(record.payload ->> 'tipo'), '') = ''",
            query,
        )
        self.assertIn("translate(", query)
        self.assertIn("= 'relacao de servidores'", query)
        self.assertIn(
            "record.record_type = 'municipal_transparency_servidores'",
            query,
        )
        self.assertIn(
            "aggregate.parser_version = %s",
            query,
        )
        self.assertIn("job.status in ('failed', 'dead_lettered')", query)
        self.assertIn("make_date(", query)
        self.assertIn("coalesce( %s::date", query)
        self.assertEqual(
            connection.parameters,
            (
                2021,
                2026,
                date(2026, 7, 1),
                "payroll-report-aggregate/1.3.0",
                PAYROLL_PUBLICATION_JOB_TYPE,
                5,
            ),
        )
        self.assertTrue(connection.closed)

    def test_rejects_tampered_pdf_before_parsing(self) -> None:
        repository = FakeRepository()
        publisher = PayrollReportPublisher(
            object_reader=FakeReader(b"tampered"),
            repository=repository,
            text_extractor=lambda _body: FIXTURE_TEXT,
        )

        with self.assertRaises(ArtifactMismatchError):
            publisher.publish(artifact_for())
        self.assertEqual(repository.inserted, [])

    def test_publishes_only_reconciled_aggregate_and_replay_is_idempotent(self) -> None:
        repository = FakeRepository()
        publisher = PayrollReportPublisher(
            object_reader=FakeReader(PDF_BODY),
            repository=repository,
            text_extractor=lambda _body: FIXTURE_TEXT,
        )

        first = publisher.publish(artifact_for())
        second = publisher.publish(artifact_for())

        self.assertEqual(first.status, "published")
        self.assertEqual(second.status, "already_published")
        self.assertEqual(len(repository.inserted), 1)
        _, report = repository.inserted[0]
        self.assertEqual(report.employee_count, 5)
        self.assertEqual(str(report.gross_amount), "17500.50")
        self.assertEqual(str(report.deduction_amount), "3000.25")
        self.assertEqual(str(report.net_amount), "14500.25")
        self.assertFalse(hasattr(report, "people"))
        self.assertFalse(hasattr(report, "names"))


if __name__ == "__main__":
    unittest.main()
