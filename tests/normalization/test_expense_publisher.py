from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from barreiras_normalization.expense_publication import (
    build_expense_publication_batch,
)
from barreiras_normalization.expense_publisher import (
    ExpenseArtifact,
    ExpensePublicationIntegrityError,
    ExpenseReportPublisher,
    PostgresExpensePublicationRepository,
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
            return FakeRows([{"id": "00000000-0000-4000-8000-000000000921"}])
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
        self.assertTrue(connection.transaction_entered)
        self.assertTrue(connection.transaction_exited)
        self.assertTrue(connection.closed)
        self.assertLessEqual(
            len(connection.calls),
            8,
            "o replay deve usar consultas em lote, não uma sequência por linha",
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
        self.assertEqual(
            connection.parameters,
            (2021, 2026, "financial_expense_publication", 5),
        )
        self.assertTrue(connection.closed)

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
