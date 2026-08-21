from __future__ import annotations

import hashlib
import unittest

from tests.normalization.test_bahia_special_transfers import (
    _archive,
    _centralization,
    _expense,
    _payment,
)


class _Reader:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects

    def read(self, object_key: str) -> bytes:
        return self.objects[object_key]


class _Repository:
    def __init__(self) -> None:
        self.batches = []

    def persist_extraction(self, batch):
        self.batches.append(batch)
        return type(
            "Result",
            (),
            {"job_created": True, "results_inserted": len(batch.candidates)},
        )()


def _body(object_text: str = "Peças para poços em Barreiras") -> bytes:
    return _archive(
        centralization_rows=[_centralization()],
        expense_rows=[_expense()],
        payment_rows=[_payment(object_text=object_text)],
    )


class BahiaSpecialTransferProcessingTests(unittest.TestCase):
    def test_job_version_forces_one_replay_with_annual_coverage(self) -> None:
        try:
            from barreiras_normalization.bahia_special_transfer_processing import (
                SPECIAL_TRANSFER_JOB_TYPE,
            )
        except ImportError:
            self.fail("o job de cobertura anual ainda não existe")
        self.assertEqual(
            SPECIAL_TRANSFER_JOB_TYPE,
            "bahia_special_transfer_payments_v3",
        )

    def _imports(self):
        try:
            from barreiras_normalization.bahia_special_transfer_processing import (
                SpecialTransferArtifact,
                SpecialTransferArtifactMismatchError,
                SpecialTransferExtractionService,
            )
        except ImportError:
            self.fail("o serviço de processamento ainda não existe")
        return (
            SpecialTransferArtifact,
            SpecialTransferArtifactMismatchError,
            SpecialTransferExtractionService,
        )

    def test_verifies_archive_and_persists_only_territorial_candidates(self) -> None:
        SpecialTransferArtifact, _, SpecialTransferExtractionService = self._imports()
        body = _body()
        sha256 = hashlib.sha256(body).hexdigest()
        artifact = SpecialTransferArtifact(
            raw_artifact_id="00000000-0000-0000-0000-000000002001",
            sha256=sha256,
            object_key=(
                "bahia/transferencias-especiais/archive/sha256/"
                f"{sha256[:2]}/{sha256}.zip"
            ),
            source_url="https://dados.ba.gov.br/dataset/transferencias-especiais",
            collected_at="2026-08-21T04:32:47+00:00",
        )
        repository = _Repository()
        service = SpecialTransferExtractionService(
            object_reader=_Reader({artifact.object_key: body}),
            repository=repository,
        )

        result = service.process(artifact)

        self.assertTrue(result.job_created)
        self.assertEqual(result.results_inserted, 1)
        self.assertEqual(repository.batches[0].candidates[0].author_name, "Tito")
        self.assertEqual(
            repository.batches[0].annual_coverage[0].source_payment_count,
            1,
        )
        self.assertEqual(
            repository.batches[0].annual_coverage[0].territorial_payment_count,
            1,
        )
        self.assertEqual(len(repository.batches[0].idempotency_key), 64)

    def test_rejects_bytes_that_diverge_from_collected_hash(self) -> None:
        (
            SpecialTransferArtifact,
            SpecialTransferArtifactMismatchError,
            SpecialTransferExtractionService,
        ) = self._imports()
        body = _body()
        artifact = SpecialTransferArtifact(
            raw_artifact_id="00000000-0000-0000-0000-000000002001",
            sha256=hashlib.sha256(body).hexdigest(),
            object_key="bahia/transferencias-especiais/archive/file.zip",
            source_url="https://dados.ba.gov.br/dataset/transferencias-especiais",
            collected_at="2026-08-21T04:32:47+00:00",
        )
        service = SpecialTransferExtractionService(
            object_reader=_Reader({artifact.object_key: body + b"tampered"}),
            repository=_Repository(),
        )

        with self.assertRaises(SpecialTransferArtifactMismatchError):
            service.process(artifact)

    def test_valid_snapshot_without_barreiras_is_recorded_as_zero_candidates(
        self,
    ) -> None:
        SpecialTransferArtifact, _, SpecialTransferExtractionService = self._imports()
        body = _body("Peças para poços em Barreirinhas/MA")
        sha256 = hashlib.sha256(body).hexdigest()
        artifact = SpecialTransferArtifact(
            raw_artifact_id="00000000-0000-0000-0000-000000002001",
            sha256=sha256,
            object_key="bahia/transferencias-especiais/archive/file.zip",
            source_url="https://dados.ba.gov.br/dataset/transferencias-especiais",
            collected_at="2026-08-21T04:32:47+00:00",
        )
        repository = _Repository()
        service = SpecialTransferExtractionService(
            object_reader=_Reader({artifact.object_key: body}),
            repository=repository,
        )

        result = service.process(artifact)

        self.assertTrue(result.job_created)
        self.assertEqual(result.results_inserted, 0)
        self.assertEqual(repository.batches[0].candidates, ())


if __name__ == "__main__":
    unittest.main()
