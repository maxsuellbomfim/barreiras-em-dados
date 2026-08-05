from __future__ import annotations

import unittest
from datetime import UTC, date, datetime

from barreiras_collectors.collection_control import (
    CollectionControl,
    CollectionOutcome,
    build_execution_idempotency_key,
)


class FakeControlRepository:
    def __init__(self) -> None:
        self.started: list[dict[str, object]] = []
        self.completed: list[dict[str, object]] = []
        self.failed: list[dict[str, object]] = []

    def start_controlled_run(self, **values: object) -> str:
        self.started.append(values)
        return "run-1"

    def complete_controlled_run(self, **values: object) -> None:
        self.completed.append(values)

    def fail_controlled_run(self, **values: object) -> None:
        self.failed.append(values)


class CollectionControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = FakeControlRepository()
        self.now = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)

    def make_control(self) -> CollectionControl:
        return CollectionControl(
            repository=self.repository,
            source_code="barreiras-diario-oficial",
            endpoint_code="direct-pdf",
            idempotency_key="control:diario:2026-08-05",
            collector_version="test/1.0",
            partition_key="day:2026-08-05",
            period_start=date(2026, 8, 5),
            period_end=date(2026, 8, 5),
            clock=lambda: self.now,
        )

    def test_starts_run_before_work_and_completes_partition(self) -> None:
        control = self.make_control()

        with control:
            self.assertEqual(len(self.repository.started), 1)
            self.assertEqual(self.repository.completed, [])
            control.complete(
                outcome=CollectionOutcome.COMPLETE,
                observed_records=3,
                checkpoint={"edition": 4703},
                metrics={"documents": 3},
            )

        self.assertEqual(
            self.repository.completed,
            [
                {
                    "run_id": "run-1",
                    "partition_key": "day:2026-08-05",
                    "period_start": date(2026, 8, 5),
                    "period_end": date(2026, 8, 5),
                    "outcome": "complete",
                    "observed_records": 3,
                    "checkpoint": {"edition": 4703},
                    "metrics": {"documents": 3},
                    "block_reason": None,
                    "completed_at": self.now,
                }
            ],
        )

    def test_exception_is_sanitized_and_recorded_as_failure(self) -> None:
        control = self.make_control()

        with self.assertRaisesRegex(RuntimeError, "token=segredo"):
            with control:
                raise RuntimeError(
                    "falha em https://fonte.test/?token=segredo&password=123"
                )

        self.assertEqual(len(self.repository.failed), 1)
        failure = self.repository.failed[0]
        self.assertEqual(failure["run_id"], "run-1")
        self.assertEqual(failure["error_type"], "RuntimeError")
        self.assertNotIn("segredo", str(failure["error_detail"]))
        self.assertNotIn("123", str(failure["error_detail"]))
        self.assertEqual(failure["retryable"], True)

    def test_empty_is_a_successful_explicit_outcome(self) -> None:
        control = self.make_control()

        with control:
            control.complete(
                outcome=CollectionOutcome.EMPTY,
                observed_records=0,
            )

        self.assertEqual(self.repository.completed[0]["outcome"], "empty")
        self.assertEqual(self.repository.completed[0]["observed_records"], 0)

    def test_blocked_partition_requires_and_preserves_reason(self) -> None:
        control = self.make_control()

        with control:
            control.complete(
                outcome=CollectionOutcome.BLOCKED,
                observed_records=0,
                block_reason="fonte oficial bloqueou a consulta histórica",
            )

        self.assertEqual(self.repository.completed[0]["outcome"], "blocked")
        self.assertEqual(
            self.repository.completed[0]["block_reason"],
            "fonte oficial bloqueou a consulta histórica",
        )


class ExecutionIdempotencyKeyTests(unittest.TestCase):
    def test_github_attempt_is_stable_and_each_attempt_is_distinct(self) -> None:
        environment = {
            "GITHUB_REPOSITORY": "maxsuellbomfim/barreiras-em-dados",
            "GITHUB_WORKFLOW": "Coletar Diário",
            "GITHUB_RUN_ID": "12345",
            "GITHUB_RUN_ATTEMPT": "1",
        }

        first = build_execution_idempotency_key(
            "direct-diary",
            environment=environment,
        )
        replay = build_execution_idempotency_key(
            "direct-diary",
            environment=environment,
        )
        second_attempt = build_execution_idempotency_key(
            "direct-diary",
            environment={**environment, "GITHUB_RUN_ATTEMPT": "2"},
        )

        self.assertEqual(first, replay)
        self.assertNotEqual(first, second_attempt)
        self.assertGreaterEqual(len(first), 16)
        self.assertLessEqual(len(first), 256)
        self.assertNotIn("Coletar Diário", first)

    def test_local_executions_receive_distinct_nonces(self) -> None:
        nonces = iter(("a" * 32, "b" * 32))

        first = build_execution_idempotency_key(
            "direct-diary",
            environment={},
            nonce_factory=lambda: next(nonces),
        )
        second = build_execution_idempotency_key(
            "direct-diary",
            environment={},
            nonce_factory=lambda: next(nonces),
        )

        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
