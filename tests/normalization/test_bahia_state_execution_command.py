from __future__ import annotations

import unittest

from barreiras_normalization.bahia_state_execution_processing import (
    StateExecutionArtifact,
    StateExecutionEmptySnapshotError,
    StateExecutionPersistResult,
)


def artifact(suffix: int) -> StateExecutionArtifact:
    sha256 = str(suffix).zfill(64)
    return StateExecutionArtifact(
        raw_artifact_id=f"00000000-0000-0000-0000-{suffix:012d}",
        sha256=sha256,
        object_key=f"bahia/emendas-estaduais/archive/{sha256}.zip",
        source_url="https://dados.ba.gov.br/dataset/emendas-parlamentares",
        collected_at="2026-08-13T17:34:48+00:00",
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
            raise StateExecutionEmptySnapshotError("arquivo local secreto.zip vazio")
        return StateExecutionPersistResult(True, 17)


class ProcessBahiaStateExecutionCommandTests(unittest.TestCase):
    def test_invalid_snapshot_is_audited_without_losing_valid_snapshot(self) -> None:
        try:
            from barreiras_normalization.commands.process_bahia_state_execution import (
                run_batch,
            )
        except ImportError:
            self.fail("o comando de execucao estadual ainda nao existe")
        repository = FakeRepository([artifact(1), artifact(2)])

        summary = run_batch(
            repository=repository,  # type: ignore[arg-type]
            service=FakeService(),  # type: ignore[arg-type]
            limit=5,
        )

        self.assertEqual(summary.pending_found, 2)
        self.assertEqual(summary.processed, 1)
        self.assertEqual(summary.failed, 1)
        self.assertEqual(summary.results_inserted, 17)
        self.assertEqual(len(repository.failures), 1)
        self.assertEqual(repository.failures[0][1]["error_code"], "empty_snapshot")
        self.assertNotIn("secreto.zip", repository.failures[0][1]["error_detail"])


if __name__ == "__main__":
    unittest.main()
