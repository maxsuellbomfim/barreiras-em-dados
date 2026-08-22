from __future__ import annotations

import hashlib
import unittest
from datetime import date

from barreiras_normalization.payroll_compensation_publisher import (
    PAYROLL_COMPENSATION_PUBLICATION_JOB_TYPE,
    PayrollCompensationArtifact,
    PayrollCompensationPublisher,
    compensation_bands_payload,
)
from barreiras_normalization.revenue_publisher import ArtifactMismatchError

PDF_BODY = b"%PDF-1.7 deterministic-payroll-compensation-fixture"
FIXTURE_TEXT = "\n".join(
    (
        "PREFEITURA MUNICIPAL DE BARREIRAS",
        "Listagem Sintética E-TCM",
        "FOLHA.........: 1-Normal, 3-Complementar, 9-Rescisão",
        "Mat. Nome Cargo Regime/Vínculo Local de Trabalho Provento Desconto Líquido",
        "100 PESSOA OMITIDA CARGO OMITIDO Estatutário LOCAL 1.500,00 100,00 1.400,00",
        "101 PESSOA OMITIDA CARGO OMITIDO Comissionado LOCAL 4.000,00 500,00 3.500,00",
        "Total de Funcionários: 2 5.500,00 600,00 4.900,00",
        "Total de Funcionários Geral: 2 5.500,00 600,00 4.900,00",
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

    def persist_distribution(self, artifact, distribution) -> int:
        if self.inserted:
            return 0
        self.inserted.append((artifact, distribution))
        return 1


def artifact_for(body: bytes = PDF_BODY) -> PayrollCompensationArtifact:
    return PayrollCompensationArtifact(
        aggregate_id="00000000-0000-4000-8000-000000000960",
        artifact_id="00000000-0000-4000-8000-000000000961",
        sha256=hashlib.sha256(body).hexdigest(),
        object_key="municipal-transparency/documents/payroll-example.pdf",
        byte_size=len(body),
        parent_record_id="00000000-0000-4000-8000-000000000962",
        source_url="https://barreiras.mtransparente.com.br/payroll-example.pdf",
        reference_month=date(2026, 7, 1),
    )


class PayrollCompensationPublisherTests(unittest.TestCase):
    def test_failure_job_is_versioned(self) -> None:
        self.assertEqual(
            PAYROLL_COMPENSATION_PUBLICATION_JOB_TYPE,
            "payroll_compensation_publication/1.0.0",
        )

    def test_rejects_tampered_pdf_before_parsing(self) -> None:
        repository = FakeRepository()
        publisher = PayrollCompensationPublisher(
            object_reader=FakeReader(b"tampered"),
            repository=repository,
            text_extractor=lambda _body: FIXTURE_TEXT,
        )

        with self.assertRaises(ArtifactMismatchError):
            publisher.publish(artifact_for())
        self.assertEqual(repository.inserted, [])

    def test_publishes_only_aggregate_bands_and_replay_is_idempotent(self) -> None:
        repository = FakeRepository()
        publisher = PayrollCompensationPublisher(
            object_reader=FakeReader(PDF_BODY),
            repository=repository,
            text_extractor=lambda _body: FIXTURE_TEXT,
        )

        first = publisher.publish(artifact_for())
        second = publisher.publish(artifact_for())

        self.assertEqual(first.status, "published")
        self.assertEqual(second.status, "already_published")
        payload = compensation_bands_payload(repository.inserted[0][1])
        self.assertEqual(
            payload,
            [
                {
                    "band_code": "up_to_1500",
                    "band_label": "Até R$ 1.500",
                    "employee_count": 1,
                    "gross_amount": "1500.00",
                },
                {
                    "band_code": "from_3000_01_to_5000",
                    "band_label": "De R$ 3.000,01 a R$ 5 mil",
                    "employee_count": 1,
                    "gross_amount": "4000.00",
                },
            ],
        )
        serialized = repr(payload).casefold()
        for forbidden in ("cpf", "nome", "matricula", "desconto", "líquido"):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
