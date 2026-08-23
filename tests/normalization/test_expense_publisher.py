from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from barreiras_normalization.commands.publish_expense_reports import (
    completion_exit_code,
)
from barreiras_normalization.expense_publication import (
    ExpenseTotalSourceConflict,
    build_expense_publication_batch,
)
from barreiras_normalization.expense_publisher import (
    ExpenseArtifact,
    ExpensePublicationIntegrityError,
    ExpenseReportPublisher,
    PostgresExpensePublicationRepository,
    plan_expense_report_version,
)
from barreiras_normalization.financial_expense_pdf import parse_expense_pdf_text
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


class FakeRows:
    def __init__(self, rows) -> None:
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class CapturingConnection:
    def __init__(self, rows=()) -> None:
        self.rows = rows
        self.query = ""
        self.parameters = ()
        self.closed = False

    def execute(self, query, parameters=()):
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


class ExistingExpenseReportConnection:
    def __init__(self, batch, *, existing_allocation=False) -> None:
        self.batch = batch
        self.existing_allocation = existing_allocation
        self.calls = []
        self.allocation_parameters = []
        self.closed = False
        self.transaction_entered = False
        self.transaction_exited = False

    def transaction(self):
        return FakeTransaction(self)

    def execute(self, query, parameters=()):
        self.calls.append((query, parameters))
        normalized = " ".join(query.lower().split())
        if "from org.public_bodies" in normalized:
            return FakeRows([{"id": "00000000-0000-4000-8000-000000000920"}])
        if "insert into finance.expense_reports" in normalized:
            return FakeRows([])
        if "select report.id::text" in normalized:
            return FakeRows(
                [
                    {
                        "id": "00000000-0000-4000-8000-000000000921",
                        "origin_raw_record_id": (
                            "00000000-0000-4000-8000-000000000913"
                        ),
                        "version": 1,
                        "external_id": (
                            f"{artifact_for().sha256}:{self.batch.batch_sha256}"
                        ),
                        "methodology_version": self.batch.methodology_version,
                    }
                ]
            )
        if "insert into finance.expense_lines" in normalized:
            return FakeRows([])
        if (
            "from finance.expense_lines as line" in normalized
            and "order by line.line_number" in normalized
        ):
            return FakeRows(
                [
                    {
                        "id": f"00000000-0000-4000-8000-{row.line_number:012d}",
                        "line_number": row.line_number,
                        "expense_code": row.expense_code,
                        "description": row.description,
                        "source_code": row.source_code,
                        "fixed_amount": row.fixed_amount,
                        "additions_amount": row.additions_amount,
                        "reductions_amount": row.reductions_amount,
                        "updated_amount": row.updated_amount,
                        "committed_period_amount": row.committed_period_amount,
                        "committed_to_date_amount": row.committed_to_date_amount,
                        "liquidated_period_amount": row.liquidated_period_amount,
                        "liquidated_to_date_amount": row.liquidated_to_date_amount,
                        "paid_period_amount": row.paid_period_amount,
                        "paid_to_date_amount": row.paid_to_date_amount,
                        "unpaid_committed_amount": row.unpaid_committed_amount,
                        "balance_amount": row.balance_amount,
                    }
                    for row in self.batch.rows
                ]
            )
        if "select line.id::text" in normalized:
            line_number = int(parameters[1])
            row = self.batch.rows[line_number - 1]
            return FakeRows(
                [
                    {
                        "id": f"00000000-0000-4000-8000-{line_number:012d}",
                        "expense_code": row.expense_code,
                        "description": row.description,
                        "source_code": row.source_code,
                        "fixed_amount": row.fixed_amount,
                        "additions_amount": row.additions_amount,
                        "reductions_amount": row.reductions_amount,
                        "updated_amount": row.updated_amount,
                        "committed_period_amount": row.committed_period_amount,
                        "committed_to_date_amount": row.committed_to_date_amount,
                        "liquidated_period_amount": row.liquidated_period_amount,
                        "liquidated_to_date_amount": row.liquidated_to_date_amount,
                        "paid_period_amount": row.paid_period_amount,
                        "paid_to_date_amount": row.paid_to_date_amount,
                        "unpaid_committed_amount": row.unpaid_committed_amount,
                        "balance_amount": row.balance_amount,
                    }
                ]
            )
        if (
            "with input_rows as" in normalized
            and "insert into finance.expense_line_budget_units" in normalized
        ):
            payload = json.loads(parameters[0])
            self.allocation_parameters.extend(payload)
            return FakeRows(
                [
                    {
                        "id": "00000000-0000-4000-8000-000000000922",
                        "expense_line_id": item["expense_line_id"],
                        "origin_raw_record_id": item["origin_raw_record_id"],
                        "source_document_artifact_id": item[
                            "source_document_artifact_id"
                        ],
                        "version": item["version"],
                        "budget_unit_code": (
                            "999999"
                            if self.existing_allocation
                            else item["budget_unit_code"]
                        ),
                        "budget_unit_name": (
                            "UNIDADE DIVERGENTE"
                            if self.existing_allocation
                            else item["budget_unit_name"]
                        ),
                        "methodology_version": (
                            "public-expense-pdf/1.0.0"
                            if self.existing_allocation
                            else item["methodology_version"]
                        ),
                        "inserted": not self.existing_allocation,
                    }
                    for item in payload
                ]
            )
        if "insert into finance.expense_line_budget_units" in normalized:
            self.allocation_parameters.append(parameters)
            if self.existing_allocation:
                return FakeRows([])
            return FakeRows([{"id": "00000000-0000-4000-8000-000000000922"}])
        if "from finance.expense_line_budget_units" in normalized:
            return FakeRows(
                [
                    {
                        "budget_unit_code": "999999",
                        "budget_unit_name": "UNIDADE DIVERGENTE",
                        "methodology_version": "public-expense-pdf/1.0.0",
                    }
                ]
            )
        return FakeRows([])

    def close(self):
        self.closed = True


class BulkExpenseLineConnection:
    def __init__(self) -> None:
        self.calls = []
        self.line_payload = []
        self.evidence_payload = []

    def execute(self, query, parameters=()):
        self.calls.append((query, parameters))
        normalized = " ".join(query.lower().split())
        payload = json.loads(parameters[0])
        if "insert into finance.expense_lines" in normalized:
            self.line_payload = payload
            return FakeRows(
                [
                    {
                        "id": f"00000000-0000-4000-8000-{item['line_number']:012d}",
                        "line_number": item["line_number"],
                    }
                    for item in payload
                ]
            )
        if "'finance.expense_lines'" in normalized:
            self.evidence_payload = payload
            return FakeRows([])
        raise AssertionError(f"consulta inesperada: {normalized[:160]}")


class SourceConflictConnection:
    def __init__(self) -> None:
        self.calls = []
        self._evidence_number = 0

    def execute(self, query, parameters=()):
        self.calls.append((query, parameters))
        normalized = " ".join(query.lower().split())
        if "select 1 from evidence.source_conflicts" in normalized:
            return FakeRows([])
        if "insert into evidence.evidence_items" in normalized:
            self._evidence_number += 1
            return FakeRows(
                [
                    {
                        "id": (
                            "00000000-0000-4000-8000-"
                            f"{930 + self._evidence_number:012d}"
                        )
                    }
                ]
            )
        if "insert into evidence.source_conflicts" in normalized:
            return FakeRows([])
        raise AssertionError(f"consulta inesperada: {normalized[:160]}")


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
    def test_persists_literal_total_source_conflict_with_two_evidences(
        self,
    ) -> None:
        base = build_expense_publication_batch(parse_expense_pdf_text(FIXTURE_TEXT))
        batch = replace(
            base,
            total_source_conflicts=(
                ExpenseTotalSourceConflict(
                    field_name="total_reductions_amount",
                    declared_amount=Decimal("263599171.60"),
                    calculated_amount=Decimal("263599171.68"),
                    difference_amount=Decimal("0.08"),
                ),
            ),
        )
        connection = SourceConflictConnection()

        PostgresExpensePublicationRepository._persist_total_source_conflicts(
            connection,
            artifact=artifact_for(),
            batch=batch,
            report_id="00000000-0000-4000-8000-000000000921",
            origin_raw_record_id="00000000-0000-4000-8000-000000000913",
        )

        self.assertEqual(len(connection.calls), 4)
        conflict_parameters = connection.calls[-1][1]
        self.assertEqual(conflict_parameters[1], "total_reductions_amount")
        self.assertEqual(
            json.loads(conflict_parameters[4]),
            {"declared_amount": "263599171.60"},
        )
        self.assertEqual(
            json.loads(conflict_parameters[5]),
            {
                "calculated_amount": "263599171.68",
                "difference_amount": "0.08",
            },
        )

    def test_new_report_persists_lines_and_evidence_in_two_bulk_queries(self) -> None:
        batch = build_expense_publication_batch(parse_expense_pdf_text(FIXTURE_TEXT))
        connection = BulkExpenseLineConnection()

        published = PostgresExpensePublicationRepository._persist_new_report_lines(
            connection,
            artifact=artifact_for(),
            batch=batch,
            report_id="00000000-0000-4000-8000-000000000921",
            origin_raw_record_id="00000000-0000-4000-8000-000000000913",
        )

        self.assertEqual(published, len(batch.rows))
        self.assertEqual(len(connection.calls), 2)
        self.assertEqual(len(connection.line_payload), len(batch.rows))
        self.assertEqual(len(connection.evidence_payload), len(batch.rows))
        self.assertEqual(
            {item["line_number"] for item in connection.line_payload},
            {row.line_number for row in batch.rows},
        )
        self.assertTrue(
            all(
                item["raw_artifact_id"] == artifact_for().id
                for item in connection.evidence_payload
            )
        )

    def test_replay_rejects_existing_budget_unit_divergence(self) -> None:
        batch = build_expense_publication_batch(parse_expense_pdf_text(FIXTURE_TEXT))
        connection = ExistingExpenseReportConnection(
            batch,
            existing_allocation=True,
        )
        repository = PostgresExpensePublicationRepository(lambda: connection)

        with self.assertRaisesRegex(
            ExpensePublicationIntegrityError,
            "unidade orçamentária publicada",
        ):
            repository.persist_validated_report(artifact_for(), batch)

    def test_replay_adds_budget_units_to_existing_validated_lines(self) -> None:
        batch = build_expense_publication_batch(parse_expense_pdf_text(FIXTURE_TEXT))
        connection = ExistingExpenseReportConnection(batch)
        repository = PostgresExpensePublicationRepository(lambda: connection)

        self.assertEqual(
            repository.persist_validated_report(artifact_for(), batch),
            0,
        )

        self.assertEqual(len(connection.allocation_parameters), 3)
        self.assertEqual(
            {
                (parameters["budget_unit_code"], parameters["budget_unit_name"])
                for parameters in connection.allocation_parameters
            },
            {("010101", "CAMARA MUNICIPAL DE BARREIRAS")},
        )
        self.assertEqual(
            {
                parameters["origin_raw_record_id"]
                for parameters in connection.allocation_parameters
            },
            {"00000000-0000-4000-8000-000000000913"},
            "o replay deve preservar a origem do relatório publicado, mesmo que "
            "o mesmo artefato seja reencontrado por outro registro bruto",
        )
        self.assertTrue(connection.transaction_entered)
        self.assertTrue(connection.transaction_exited)
        self.assertTrue(connection.closed)
        self.assertLessEqual(
            len(connection.calls),
            9,
            "o replay deve usar consultas em lote, não uma sequência por linha",
        )
        self.assertTrue(
            any(
                "insert into raw.extraction_jobs" in " ".join(query.lower().split())
                and "'succeeded'" in query.lower()
                for query, _parameters in connection.calls
            ),
            "um replay concluído deve limpar o diagnóstico de falha anterior",
        )

    def test_pending_documents_includes_reports_without_budget_unit_allocation(
        self,
    ) -> None:
        connection = CapturingConnection()
        repository = PostgresExpensePublicationRepository(lambda: connection)

        self.assertEqual(
            repository.pending_documents(
                limit=5,
                fiscal_year_from=2021,
                fiscal_year_to=2026,
            ),
            (),
        )

        query = " ".join(connection.query.lower().split())
        self.assertIn("finance.expense_line_budget_units", query)
        self.assertIn("allocation.expense_line_id is null", query)
        self.assertIn("replay_candidates as", query)
        self.assertIn("current_reports as materialized", query)
        self.assertIn("report.methodology_version <> %s", query)
        self.assertIn("new_candidates as", query)
        self.assertIn("union all", query)
        self.assertIn("report.origin_raw_record_id::text as parent_record_id", query)
        self.assertIn("job.status = 'dead_lettered'", query)
        self.assertNotIn("job.status = 'failed'", query)
        self.assertEqual(
            connection.parameters,
            (
                2021,
                2026,
                "public-expense-pdf/1.3.0",
                2021,
                2026,
                "financial_expense_publication",
                5,
            ),
        )
        self.assertTrue(connection.closed)

    def test_older_methodology_creates_a_new_auditable_version(self) -> None:
        batch = build_expense_publication_batch(parse_expense_pdf_text(FIXTURE_TEXT))
        plan = plan_expense_report_version(
            {
                "id": "00000000-0000-4000-8000-000000000921",
                "origin_raw_record_id": "00000000-0000-4000-8000-000000000913",
                "version": 1,
                "external_id": "immutable-old-digest",
                "methodology_version": "public-expense-pdf/1.1.0",
            },
            artifact=artifact_for(),
            batch=batch,
        )

        self.assertEqual(plan.action, "insert")
        self.assertEqual(plan.version, 2)
        self.assertEqual(
            plan.supersedes_id,
            "00000000-0000-4000-8000-000000000921",
        )
        self.assertEqual(
            plan.origin_raw_record_id,
            "00000000-0000-4000-8000-000000000913",
        )

    def test_failure_is_retryable_until_dead_letter(self) -> None:
        connection = CapturingConnection()
        repository = PostgresExpensePublicationRepository(lambda: connection)

        repository.record_failure(
            artifact_for(),
            error_code="ExpensePublicationIntegrityError",
            error_detail="falha transitória de reconciliação",
        )

        query = " ".join(connection.query.lower().split())
        self.assertIn("attempt_count + 1 >= raw.extraction_jobs.max_attempts", query)
        self.assertIn("then 'dead_lettered'", query)
        self.assertIn("else 'failed'", query)

    def test_command_fails_when_any_artifact_needs_review(self) -> None:
        self.assertEqual(completion_exit_code(needs_review=0), 0)
        self.assertEqual(completion_exit_code(needs_review=1), 1)

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
