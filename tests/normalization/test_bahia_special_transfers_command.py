from __future__ import annotations

import unittest

from barreiras_normalization.bahia_special_transfer_processing import (
    SpecialTransferArtifact,
    SpecialTransferArtifactMismatchError,
    SpecialTransferPersistResult,
)


def artifact(suffix: int) -> SpecialTransferArtifact:
    sha256 = str(suffix).zfill(64)
    return SpecialTransferArtifact(
        raw_artifact_id=f"00000000-0000-0000-0000-{suffix:012d}",
        sha256=sha256,
        object_key=(
            f"bahia/transferencias-especiais/archive/sha256/{sha256[:2]}/{sha256}.zip"
        ),
        source_url="https://dados.ba.gov.br/dataset/transferencias-especiais",
        collected_at="2026-08-21T04:32:47+00:00",
    )


class FakeRepository:
    def __init__(self, artifacts) -> None:
        self.artifacts = tuple(artifacts)
        self.failures = []

    def pending_artifacts(self, limit: int):
        return self.artifacts[:limit]

    def persist_failure(self, target, **kwargs) -> None:
        self.failures.append((target, kwargs))


class FakeService:
    def process(self, target):
        if target.raw_artifact_id.endswith("000000000001"):
            raise SpecialTransferArtifactMismatchError("arquivo privado.zip")
        return SpecialTransferPersistResult(True, 3)


class ProcessBahiaSpecialTransfersCommandTests(unittest.TestCase):
    def test_invalid_snapshot_is_audited_without_losing_valid_snapshot(self) -> None:
        try:
            from barreiras_normalization.commands import (
                process_bahia_special_transfers,
            )
        except ImportError:
            self.fail("o comando de normalização ainda não existe")
        run_batch = process_bahia_special_transfers.run_batch
        repository = FakeRepository([artifact(1), artifact(2)])

        summary = run_batch(
            repository=repository,  # type: ignore[arg-type]
            service=FakeService(),  # type: ignore[arg-type]
            limit=5,
        )

        self.assertEqual(summary.pending_found, 2)
        self.assertEqual(summary.processed, 1)
        self.assertEqual(summary.failed, 1)
        self.assertEqual(summary.results_inserted, 3)
        self.assertEqual(len(repository.failures), 1)
        self.assertEqual(repository.failures[0][1]["error_code"], "artifact_mismatch")
        self.assertNotIn("privado.zip", repository.failures[0][1]["error_detail"])


if __name__ == "__main__":
    unittest.main()
