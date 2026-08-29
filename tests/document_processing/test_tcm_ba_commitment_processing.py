from __future__ import annotations

import unittest

from barreiras_docproc.processing import PageInput, TextArtifact
from barreiras_docproc.tcm_ba_commitments import (
    EXTRACTOR_VERSION,
    TcmBaCommitmentBatch,
    TcmBaCommitmentExtractionService,
    TcmBaCommitmentPersistResult,
    commitment_candidate_payload,
    commitment_job_idempotency_key,
)


class FakeRepository:
    def __init__(self) -> None:
        self.batches: list[TcmBaCommitmentBatch] = []

    def persist_tcm_ba_commitment_candidates(
        self,
        batch: TcmBaCommitmentBatch,
    ) -> TcmBaCommitmentPersistResult:
        self.batches.append(batch)
        return TcmBaCommitmentPersistResult(
            job_created=True,
            results_inserted=len(batch.candidates),
        )


def artifact() -> TextArtifact:
    return TextArtifact(
        raw_artifact_id="00000000-0000-0000-0000-000000000902",
        sha256="b" * 64,
        object_key=(f"tcm-ba/monthly-documents/2021/01/pdf/sha256/bb/{'b' * 64}.pdf"),
    )


def complete_note_page() -> PageInput:
    return PageInput(
        page_number=3,
        parser_version="pypdf/fixture",
        text=(
            "NOTA DE EMPENHO Nº 45/2021\n"
            "Emissão: 20/01/2021\n"
            "Credor: PESSOA EXEMPLO - CPF 123.456.789-09\n"
            "Valor: R$ 2.000,00\n"
            "Dotação: 02.05.123.456\n"
        ),
        sha256="c" * 64,
    )


class TcmBaCommitmentProcessingTests(unittest.TestCase):
    def test_service_persists_review_candidate_with_versioned_lineage(self) -> None:
        repository = FakeRepository()
        source = artifact()

        result = TcmBaCommitmentExtractionService(
            repository=repository,
        ).process(source, (complete_note_page(),))

        self.assertTrue(result.job_created)
        self.assertEqual(result.results_inserted, 1)
        batch = repository.batches[0]
        self.assertEqual(batch.job_type, "tcm_ba_commitment_candidates")
        self.assertEqual(batch.extractor_version, EXTRACTOR_VERSION)
        self.assertEqual(
            batch.job_idempotency_key,
            commitment_job_idempotency_key(source.sha256),
        )

    def test_candidate_payload_is_a_redacted_non_public_review_record(self) -> None:
        repository = FakeRepository()
        source = artifact()
        TcmBaCommitmentExtractionService(repository=repository).process(
            source,
            (complete_note_page(),),
        )
        batch = repository.batches[0]

        payload = commitment_candidate_payload(
            batch.candidates[0],
            source,
        )

        self.assertEqual(payload["schema_name"], "tcm-ba-commitment-candidate")
        self.assertEqual(payload["candidate_status"], "complete")
        self.assertEqual(payload["source_page_number"], 3)
        self.assertEqual(payload["source_artifact_sha256"], "b" * 64)
        self.assertEqual(payload["missing_fields"], [])
        serialized = str(payload)
        self.assertNotIn("123.456.789-09", serialized)
        self.assertNotIn("finance.commitments", serialized)

    def test_service_records_zero_candidate_job_for_incidental_mentions(self) -> None:
        repository = FakeRepository()
        incidental = PageInput(
            page_number=1,
            parser_version="pypdf/fixture",
            text="A contratada deverá retirar a Nota de Empenho.",
            sha256="d" * 64,
        )

        result = TcmBaCommitmentExtractionService(
            repository=repository,
        ).process(artifact(), (incidental,))

        self.assertTrue(result.job_created)
        self.assertEqual(result.results_inserted, 0)
        self.assertEqual(repository.batches[0].candidates, ())


if __name__ == "__main__":
    unittest.main()
