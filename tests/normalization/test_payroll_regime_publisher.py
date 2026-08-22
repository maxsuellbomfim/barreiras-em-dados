from __future__ import annotations

import hashlib
import unittest
from datetime import date

from barreiras_normalization.payroll_regime_publisher import (
    PAYROLL_REGIME_PUBLICATION_JOB_TYPE,
    PayrollRegimeArtifact,
    PayrollRegimePublisher,
    PostgresPayrollRegimeRepository,
    regime_categories_payload,
)
from barreiras_normalization.revenue_publisher import ArtifactMismatchError

PDF_BODY = b"%PDF-1.7 deterministic-payroll-regime-fixture"


def _row(identifier: str, regime: str, gross: str, deduction: str, net: str) -> str:
    prefix = f"{identifier} PESSOA OMITIDA CARGO OMITIDO"
    return (
        f"{prefix:<80}{regime:<28}{'LOTAÇÃO OMITIDA':<25}"
        f"{gross} {deduction} {net}"
    )


FIXTURE_TEXT = "\n".join(
    (
        "PREFEITURA MUNICIPAL DE BARREIRAS",
        "RELAÇÃO DE SERVIDORES",
        "Listagem Sintética E-TCM 1-Normal, 3-Complementar, 9-RescisãoFOLHA.........:",
        f"{'Mat. Nome Cargo Provento Desconto Líquido':<80}"
        f"{'Regime/Vínculo':<28}Local de Trabalho C. Horária Admissão Demissão",
        _row("101", "Estatutário", "1.000,00", "100,00", "900,00"),
        _row("(T)", "Cargo em Comissão", "2.000,00", "400,00", "1.600,00"),
        "Total de Funcionários: 2 3.000,00 500,00 2.500,00",
        "Total de Funcionários Geral: 2 3.000,00 500,00 2.500,00",
    )
)


class FakeReader:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self, object_key: str) -> bytes:
        del object_key
        return self.body


class FakeRepository:
    def __init__(self) -> None:
        self.inserted = []

    def persist_breakdown(self, artifact, breakdown) -> int:
        if self.inserted:
            return 0
        self.inserted.append((artifact, breakdown))
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


def artifact_for(body: bytes = PDF_BODY) -> PayrollRegimeArtifact:
    return PayrollRegimeArtifact(
        aggregate_id="00000000-0000-4000-8000-000000000950",
        artifact_id="00000000-0000-4000-8000-000000000951",
        sha256=hashlib.sha256(body).hexdigest(),
        object_key="municipal-transparency/documents/payroll-example.pdf",
        byte_size=len(body),
        parent_record_id="00000000-0000-4000-8000-000000000952",
        source_url="https://barreiras.mtransparente.com.br/payroll-example.pdf",
        reference_month=date(2026, 7, 1),
    )


class PayrollRegimePublisherTests(unittest.TestCase):
    def test_failure_job_is_versioned(self) -> None:
        self.assertEqual(
            PAYROLL_REGIME_PUBLICATION_JOB_TYPE,
            "payroll_regime_publication/1.0.0",
        )

    def test_pending_selection_is_private_and_month_scoped(self) -> None:
        connection = CapturingConnection(
            [
                {
                    "aggregate_id": "00000000-0000-4000-8000-000000000950",
                    "artifact_id": "00000000-0000-4000-8000-000000000951",
                    "sha256": "a" * 64,
                    "object_key": "municipal-transparency/documents/payroll.pdf",
                    "byte_size": 2478977,
                    "parent_record_id": "00000000-0000-4000-8000-000000000952",
                    "source_url": "https://barreiras.mtransparente.com.br/payroll.pdf",
                    "reference_month": date(2026, 7, 1),
                }
            ]
        )
        repository = PostgresPayrollRegimeRepository(lambda: connection)

        documents = repository.pending_documents(
            limit=5,
            reference_month=date(2026, 7, 1),
        )

        self.assertEqual(documents[0].aggregate_id, connection.rows[0]["aggregate_id"])
        query = " ".join(connection.query.lower().split())
        self.assertIn(
            "hr.get_pending_payroll_regime_documents(%s, %s)",
            query,
        )
        self.assertEqual(connection.parameters, (5, date(2026, 7, 1)))
        self.assertTrue(connection.closed)

    def test_rejects_tampered_pdf_before_parsing(self) -> None:
        repository = FakeRepository()
        publisher = PayrollRegimePublisher(
            object_reader=FakeReader(b"tampered"),
            repository=repository,
            text_extractor=lambda _body: FIXTURE_TEXT,
        )

        with self.assertRaises(ArtifactMismatchError):
            publisher.publish(artifact_for())
        self.assertEqual(repository.inserted, [])

    def test_publishes_only_reconciled_categories_and_replay_is_idempotent(
        self,
    ) -> None:
        repository = FakeRepository()
        publisher = PayrollRegimePublisher(
            object_reader=FakeReader(PDF_BODY),
            repository=repository,
            text_extractor=lambda _body: FIXTURE_TEXT,
        )

        first = publisher.publish(artifact_for())
        second = publisher.publish(artifact_for())

        self.assertEqual(first.status, "published")
        self.assertEqual(second.status, "already_published")
        self.assertEqual(len(repository.inserted), 1)
        payload = regime_categories_payload(repository.inserted[0][1])
        self.assertEqual(
            payload,
            [
                {
                    "regime_code": "commissioned",
                    "regime_label": "Cargos em comissão",
                    "employee_count": 1,
                    "gross_amount": "2000.00",
                    "deduction_amount": "400.00",
                    "net_amount": "1600.00",
                },
                {
                    "regime_code": "statutory",
                    "regime_label": "Estatutários",
                    "employee_count": 1,
                    "gross_amount": "1000.00",
                    "deduction_amount": "100.00",
                    "net_amount": "900.00",
                },
            ],
        )
        self.assertEqual(
            set().union(*(item.keys() for item in payload)),
            {
                "regime_code",
                "regime_label",
                "employee_count",
                "gross_amount",
                "deduction_amount",
                "net_amount",
            },
        )


if __name__ == "__main__":
    unittest.main()
