from __future__ import annotations

import hashlib
import json
import unittest
from decimal import Decimal
from pathlib import Path

from barreiras_normalization.public_obligation_publisher import (
    PUBLIC_OBLIGATION_JOB_TYPE,
    PUBLIC_OBLIGATION_METHODOLOGY,
    PostgresPublicObligationPublicationRepository,
    PublicObligationArtifact,
    PublicObligationExtraction,
    PublicObligationExtractionProvenance,
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
    def __init__(self, *, previous_month_to_date=None) -> None:
        self.inserted = []
        self.conflicts = []
        self.previous = previous_month_to_date

    def persist_validated_summary(self, artifact, summary, provenance) -> int:
        if self.inserted:
            return 0
        self.inserted.append((artifact, summary, provenance))
        return 1

    def previous_month_to_date(self, artifact):
        del artifact
        return self.previous

    def record_progression_conflict(
        self,
        artifact,
        summary,
        provenance,
        *,
        previous_month_to_date,
    ) -> int:
        if self.conflicts:
            return 0
        self.conflicts.append(
            (artifact, summary, provenance, previous_month_to_date)
        )
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


class FakeTransaction:
    def __init__(self, connection) -> None:
        self.connection = connection

    def __enter__(self):
        self.connection.transaction_entered = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        del exc_type, exc_value, traceback
        self.connection.transaction_exited = True


class ProgressionConflictConnection:
    def __init__(self) -> None:
        self.calls = []
        self.closed = False
        self.transaction_entered = False
        self.transaction_exited = False

    def transaction(self):
        return FakeTransaction(self)

    def execute(self, query, parameters=()):
        self.calls.append((query, parameters))
        normalized = " ".join(query.lower().split())
        if "select obligation.id::text" in normalized:
            return FakeRows(
                [
                    {
                        "id": "00000000-0000-4000-8000-000000000930",
                        "payments_to_date_amount": Decimal("45364644.05"),
                        "evidence_item_id": (
                            "00000000-0000-4000-8000-000000000931"
                        ),
                    }
                ]
            )
        if "from org.public_bodies" in normalized:
            return FakeRows(
                [{"id": "00000000-0000-4000-8000-000000000932"}]
            )
        if "insert into finance.public_obligations" in normalized:
            return FakeRows(
                [{"id": "00000000-0000-4000-8000-000000000933"}]
            )
        if "insert into evidence.evidence_items" in normalized:
            return FakeRows(
                [{"id": "00000000-0000-4000-8000-000000000934"}]
            )
        return FakeRows([])

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
            "public_obligation_balancete_publication/1.5.5",
        )
        self.assertEqual(
            PUBLIC_OBLIGATION_METHODOLOGY,
            "public-obligations-balancete/1.5.5",
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
        repository = PostgresPublicObligationPublicationRepository(lambda: connection)

        documents = repository.pending_documents(
            limit=1,
            fiscal_year_from=2026,
            fiscal_year_to=2026,
        )

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].fiscal_year, 2026)
        self.assertEqual(documents[0].reference_month, 6)
        normalized_query = (
            " ".join(connection.query.split()).replace("( ", "(").replace(" )", ")")
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
            (
                2026,
                2026,
                PUBLIC_OBLIGATION_METHODOLOGY,
                PUBLIC_OBLIGATION_JOB_TYPE,
                1,
            ),
        )
        self.assertTrue(connection.closed)
        self.assertIn(
            "job.status in ('failed', 'succeeded', 'dead_lettered')",
            normalized_query,
        )
        self.assertIn("public_obligation_section_absent", normalized_query)
        self.assertIn("public_obligation_section_incomplete", normalized_query)
        self.assertNotIn("public_obligation_progression_conflict", normalized_query)
        self.assertIn("result.validation_status = 'valid'", normalized_query)
        self.assertIn(
            "result.extractor_version = %s",
            normalized_query,
        )

    def test_pending_documents_selects_only_monthly_reports_in_period_order(self):
        connection = CapturingConnection([])
        repository = PostgresPublicObligationPublicationRepository(lambda: connection)

        repository.pending_documents(
            limit=25,
            fiscal_year_from=2021,
            fiscal_year_to=2025,
        )

        normalized_query = " ".join(connection.query.lower().split())
        self.assertIn(
            "btrim(coalesce(record.payload ->> 'titulo', '')) "
            "~* '^balancete[[:space:]]'",
            normalized_query,
        )
        self.assertIn(
            "order by fiscal_year asc, reference_month asc, created_at asc, id",
            normalized_query,
        )

    def test_records_source_section_absence_as_terminal_valid_result(self):
        connection = CapturingConnection([])
        repository = PostgresPublicObligationPublicationRepository(lambda: connection)

        repository.record_section_absent(
            artifact_for(),
            detail="O balancete oficial nao contem a secao RESTOS A PAGAR.",
        )

        normalized_query = " ".join(connection.query.lower().split())
        self.assertIn("insert into raw.extraction_jobs", normalized_query)
        self.assertIn("'succeeded'", normalized_query)
        self.assertIn("insert into raw.extraction_results", normalized_query)
        self.assertIn("public_obligation_section_absent", normalized_query)
        self.assertTrue(connection.closed)

    def test_records_incomplete_source_section_as_terminal_valid_result(self):
        connection = CapturingConnection([])
        repository = PostgresPublicObligationPublicationRepository(lambda: connection)

        repository.record_section_incomplete(
            artifact_for(),
            detail="A secao existe, mas o PDF termina sem o total declarado.",
        )

        normalized_query = " ".join(connection.query.lower().split())
        self.assertIn("insert into raw.extraction_jobs", normalized_query)
        self.assertIn("'succeeded'", normalized_query)
        self.assertIn("insert into raw.extraction_results", normalized_query)
        self.assertIn(
            "public_obligation_section_incomplete",
            connection.parameters,
        )
        self.assertTrue(connection.closed)

    def test_reads_previous_month_accumulated_value_for_reconciliation(self):
        connection = CapturingConnection(
            [{"payments_to_date_amount": Decimal("24003976.26")}]
        )
        repository = PostgresPublicObligationPublicationRepository(lambda: connection)

        value = repository.previous_month_to_date(artifact_for())

        self.assertEqual(value, Decimal("24003976.26"))
        normalized_query = " ".join(connection.query.lower().split())
        self.assertIn("period_end = %s::date", normalized_query)
        self.assertIn("obligation_type = 'restos_a_pagar_total'", normalized_query)
        self.assertTrue(connection.closed)

    def test_persists_progression_conflict_with_both_evidence_values(self):
        connection = ProgressionConflictConnection()
        repository = PostgresPublicObligationPublicationRepository(lambda: connection)
        extraction = PublicObligationPublisher(
            object_reader=FakeReader(PDF_BODY),
            repository=FakeRepository(),
            text_extractor=lambda _body: FIXTURE_TEXT,
        ).validate(artifact_for())

        inserted = repository.record_progression_conflict(
            artifact_for(),
            extraction.summary,
            extraction.provenance,
            previous_month_to_date=Decimal("45364644.05"),
        )

        self.assertEqual(inserted, 1)
        self.assertTrue(connection.transaction_entered)
        self.assertTrue(connection.transaction_exited)
        self.assertTrue(connection.closed)
        all_queries = " ".join(query.lower() for query, _ in connection.calls)
        all_parameters = tuple(
            value for _, parameters in connection.calls for value in parameters
        )
        self.assertIn("insert into finance.public_obligations", all_queries)
        self.assertIn("insert into evidence.source_conflicts", all_queries)
        self.assertIn("insert into raw.extraction_results", all_queries)
        self.assertIn("public_obligation_progression_conflict", all_parameters)
        self.assertIn(Decimal("45364644.06"), all_parameters)
        json_parameters = [
            json.loads(value)
            for value in all_parameters
            if isinstance(value, str) and value.startswith("{")
        ]
        self.assertIn(
            {
                "period_end": "2026-05-31",
                "payments_to_date_amount": "45364644.05",
            },
            json_parameters,
        )
        self.assertIn(
            {
                "period_start": "2026-06-01",
                "payments_prior_amount": "45364644.06",
                "difference_amount": "0.01",
            },
            json_parameters,
        )

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
        _, summary, provenance = repository.inserted[0]
        self.assertEqual(summary.period_end.isoformat(), "2026-06-30")
        self.assertEqual(str(summary.payments_period_amount), "3683221.97")
        self.assertEqual(provenance.extraction_method, "embedded_text")

    def test_records_progression_conflict_without_publishing_as_validated(self):
        repository = FakeRepository(
            previous_month_to_date=Decimal("45364644.05")
        )
        publisher = PublicObligationPublisher(
            object_reader=FakeReader(PDF_BODY),
            repository=repository,
            text_extractor=lambda _body: FIXTURE_TEXT,
        )

        result = publisher.publish(artifact_for())

        self.assertEqual(result.status, "source_conflict")
        self.assertEqual(repository.inserted, [])
        self.assertEqual(len(repository.conflicts), 1)
        _, summary, provenance, previous = repository.conflicts[0]
        self.assertEqual(summary.payments_prior_amount, Decimal("45364644.06"))
        self.assertEqual(previous, Decimal("45364644.05"))
        self.assertEqual(provenance.extraction_method, "embedded_text")

    def test_validate_checks_artifact_and_extracts_without_persisting(self):
        repository = FakeRepository()
        publisher = PublicObligationPublisher(
            object_reader=FakeReader(PDF_BODY),
            repository=repository,
            text_extractor=lambda _body: FIXTURE_TEXT,
        )

        extraction = publisher.validate(artifact_for())

        self.assertEqual(
            str(extraction.summary.payments_to_date_amount),
            "49047866.03",
        )
        self.assertEqual(repository.inserted, [])

    def test_uses_ocr_fallback_for_structurally_incomplete_embedded_text(self):
        repository = FakeRepository()
        ocr_calls = []

        def ocr_extractor(body, *, fiscal_year, reference_month):
            ocr_calls.append((body, fiscal_year, reference_month))
            from barreiras_normalization.public_obligation_pdf import (
                parse_restos_a_pagar_summary,
            )

            return PublicObligationExtraction(
                summary=parse_restos_a_pagar_summary(
                    FIXTURE_TEXT,
                    fiscal_year=fiscal_year,
                    reference_month=reference_month,
                ),
                provenance=PublicObligationExtractionProvenance(
                    extraction_method="ocr",
                    extraction_parser_version="gazette-ocr-text/1.0.0",
                    page_numbers=(74, 75),
                    rotation_degrees=270,
                ),
            )

        publisher = PublicObligationPublisher(
            object_reader=FakeReader(PDF_BODY),
            repository=repository,
            text_extractor=lambda _body: "RESTOS A PAGAR\ntexto truncado",
            ocr_extractor=ocr_extractor,
        )

        result = publisher.publish(artifact_for())

        self.assertEqual(result.status, "published")
        self.assertEqual(ocr_calls, [(PDF_BODY, 2026, 6)])
        self.assertEqual(repository.inserted[0][2].extraction_method, "ocr")

    def test_does_not_use_ocr_to_override_arithmetic_mismatch(self):
        repository = FakeRepository()
        ocr_calls = []
        bad_text = FIXTURE_TEXT.replace(
            "49.047.866,03 3.683.221,97 45.364.644,06",
            "49.047.866,04 3.683.221,97 45.364.644,06",
        )
        publisher = PublicObligationPublisher(
            object_reader=FakeReader(PDF_BODY),
            repository=repository,
            text_extractor=lambda _body: bad_text,
            ocr_extractor=lambda *_args, **_kwargs: ocr_calls.append(True),
        )

        from barreiras_normalization.public_obligation_pdf import (
            PublicObligationArithmeticError,
        )

        with self.assertRaises(PublicObligationArithmeticError):
            publisher.publish(artifact_for())
        self.assertEqual(ocr_calls, [])
        self.assertEqual(repository.inserted, [])


if __name__ == "__main__":
    unittest.main()
