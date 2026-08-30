from __future__ import annotations

import logging
import unittest

from barreiras_docproc.commands.process_tcm_ba_commitments import (
    batch_exit_code,
    run_batch,
)
from barreiras_docproc.processing import PageInput, TextArtifact
from barreiras_docproc.tcm_ba_commitment_repository import (
    TcmBaCommitmentPageSet,
)
from barreiras_docproc.tcm_ba_commitments import (
    TcmBaCommitmentPersistResult,
)


def page_set(suffix: str) -> TcmBaCommitmentPageSet:
    artifact = TextArtifact(
        raw_artifact_id=f"00000000-0000-0000-0000-0000000009{suffix}",
        sha256=suffix * 64,
        object_key=f"tcm-ba/monthly-documents/2021/01/{suffix}.pdf",
    )
    return TcmBaCommitmentPageSet(
        artifact=artifact,
        pages=(
            PageInput(
                page_number=1,
                parser_version="fixture/1.0.0",
                text="CONTRATO SEM NOTA DE EMPENHO AUTÔNOMA",
                sha256="a" * 64,
            ),
        ),
    )


class FakeRepository:
    def __init__(self, page_sets=()) -> None:
        self.page_sets = tuple(page_sets)
        self.failures = []

    def pending_page_sets(self, limit: int):
        self.limit = limit
        return self.page_sets

    def persist_failure(
        self,
        artifact,
        *,
        idempotency_key,
        error_code,
        error_detail,
    ) -> None:
        self.failures.append((artifact, idempotency_key, error_code, error_detail))


class FakeService:
    def __init__(self, *, fail_sha: str | None = None) -> None:
        self.fail_sha = fail_sha

    def process(self, artifact, pages):
        if artifact.sha256 == self.fail_sha:
            raise RuntimeError("conteúdo sensível que não deve ir ao log")
        return TcmBaCommitmentPersistResult(True, 0)


class ProcessTcmBaCommitmentsCommandTests(unittest.TestCase):
    def test_zero_candidates_is_a_successful_processed_artifact(self) -> None:
        repository = FakeRepository((page_set("1"),))
        logger = logging.getLogger("test_tcm_ba_commitment_private_events")

        with self.assertLogs(logger, level=logging.DEBUG) as captured:
            summary = run_batch(
                repository=repository,
                service=FakeService(),
                limit=5,
                logger=logger,
            )

        self.assertEqual(summary.pending_found, 1)
        self.assertEqual(summary.processed, 1)
        self.assertEqual(summary.results_inserted, 0)
        self.assertEqual(summary.failed, 0)
        self.assertEqual(batch_exit_code(summary), 0)
        self.assertEqual(captured.records[0].levelno, logging.DEBUG)
        self.assertEqual(captured.records[-1].levelno, logging.INFO)

    def test_failure_is_recorded_without_copying_exception_detail(self) -> None:
        failing = page_set("2")
        repository = FakeRepository((failing,))

        logger = logging.getLogger("test_tcm_ba_commitment_private_failure")
        with self.assertLogs(logger, level=logging.ERROR) as captured:
            summary = run_batch(
                repository=repository,
                service=FakeService(fail_sha=failing.artifact.sha256),
                limit=5,
                logger=logger,
            )

        self.assertEqual(summary.failed, 1)
        self.assertEqual(batch_exit_code(summary), 1)
        self.assertEqual(len(repository.failures), 1)
        _artifact, _key, code, detail = repository.failures[0]
        self.assertEqual(code, "processing_error")
        self.assertEqual(detail, "RuntimeError: processing failure")
        self.assertNotIn("conteúdo sensível", detail)
        self.assertNotIn(failing.artifact.sha256, "\n".join(captured.output))

    def test_empty_queue_is_not_treated_as_a_collection_failure(self) -> None:
        summary = run_batch(
            repository=FakeRepository(),
            service=FakeService(),
            limit=5,
        )

        self.assertEqual(summary.pending_found, 0)
        self.assertEqual(batch_exit_code(summary), 0)


if __name__ == "__main__":
    unittest.main()
