from __future__ import annotations

import hashlib
import unittest

from tests.normalization.test_bahia_state_execution import (
    _archive_with_expense_rows,
)


def _expense_row() -> tuple[str, ...]:
    return (
        "2026",
        "Secretaria da Educacao",
        "SEC",
        "Assessoria de Planejamento e Gestao",
        "APG",
        "Apoio Financeiro para a Melhoria",
        "500069",
        "Antonio Henrique Junior",
        "Antonio Henrique Junior",
        "2026.3.11.11101.422.3334.500069.5",
        "237000,00",
        "237000,00",
        "0,00",
        "0,00",
        "0,00",
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
            {"job_created": True, "results_inserted": len(batch.aggregates)},
        )()


class BahiaStateExecutionProcessingTests(unittest.TestCase):
    def _imports(self):
        try:
            from barreiras_normalization.bahia_state_execution_processing import (
                StateExecutionArtifact,
                StateExecutionArtifactMismatchError,
                StateExecutionEmptySnapshotError,
                StateExecutionExtractionService,
            )
        except ImportError:
            self.fail("o servico de processamento estadual ainda nao existe")
        return (
            StateExecutionArtifact,
            StateExecutionArtifactMismatchError,
            StateExecutionEmptySnapshotError,
            StateExecutionExtractionService,
        )

    def test_restores_verified_archive_and_persists_versioned_aggregates(self) -> None:
        StateExecutionArtifact, _, _, StateExecutionExtractionService = self._imports()
        body = _archive_with_expense_rows([_expense_row()])
        sha256 = hashlib.sha256(body).hexdigest()
        artifact = StateExecutionArtifact(
            raw_artifact_id="00000000-0000-0000-0000-000000001001",
            sha256=sha256,
            object_key=f"bahia/emendas-estaduais/archive/{sha256}.zip",
            source_url="https://dados.ba.gov.br/dataset/emendas-parlamentares",
            collected_at="2026-08-13T17:34:48+00:00",
        )
        repository = _Repository()
        service = StateExecutionExtractionService(
            object_reader=_Reader({artifact.object_key: body}),
            repository=repository,
        )

        result = service.process(artifact)

        self.assertTrue(result.job_created)
        self.assertEqual(result.results_inserted, 1)
        batch = repository.batches[0]
        self.assertEqual(batch.artifact.sha256, sha256)
        self.assertEqual(batch.aggregates[0].action_code, "3334")
        self.assertEqual(len(batch.idempotency_key), 64)

    def test_rejects_storage_bytes_that_do_not_match_the_collected_hash(self) -> None:
        (
            StateExecutionArtifact,
            StateExecutionArtifactMismatchError,
            _,
            StateExecutionExtractionService,
        ) = self._imports()
        body = _archive_with_expense_rows([_expense_row()])
        artifact = StateExecutionArtifact(
            raw_artifact_id="00000000-0000-0000-0000-000000001001",
            sha256=hashlib.sha256(body).hexdigest(),
            object_key="bahia/emendas-estaduais/archive/file.zip",
            source_url="https://dados.ba.gov.br/dataset/emendas-parlamentares",
            collected_at="2026-08-13T17:34:48+00:00",
        )
        service = StateExecutionExtractionService(
            object_reader=_Reader({artifact.object_key: body + b"tampered"}),
            repository=_Repository(),
        )

        with self.assertRaises(StateExecutionArtifactMismatchError):
            service.process(artifact)

    def test_rejects_verified_archive_without_execution_rows(self) -> None:
        (
            StateExecutionArtifact,
            _,
            StateExecutionEmptySnapshotError,
            StateExecutionExtractionService,
        ) = self._imports()
        body = _archive_with_expense_rows([])
        sha256 = hashlib.sha256(body).hexdigest()
        artifact = StateExecutionArtifact(
            raw_artifact_id="00000000-0000-0000-0000-000000001001",
            sha256=sha256,
            object_key=f"bahia/emendas-estaduais/archive/{sha256}.zip",
            source_url="https://dados.ba.gov.br/dataset/emendas-parlamentares",
            collected_at="2026-08-13T17:34:48+00:00",
        )
        repository = _Repository()
        service = StateExecutionExtractionService(
            object_reader=_Reader({artifact.object_key: body}),
            repository=repository,
        )

        with self.assertRaises(StateExecutionEmptySnapshotError):
            service.process(artifact)

        self.assertEqual(repository.batches, [])


if __name__ == "__main__":
    unittest.main()
