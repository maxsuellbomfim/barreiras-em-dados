from __future__ import annotations

import logging
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from barreiras_collectors.collection_control import CollectionControl
from barreiras_collectors.commands import collect_pncp_contratos as command
from barreiras_collectors.connectors.pncp import PncpError


def control(number: int) -> str:
    return f"13654405000195-1-{number:06d}/2025"


class MutableBacklog:
    def __init__(self, count=120, recent=0):
        self.rows = [(control(n), 2025, n) for n in range(1, count + 1)]
        self.recent = set(range(1, recent + 1))
        self.preserved = set()
        self.visited = []
        self.progress = []

    def checkpoint_progress(self, checkpoint):
        self.progress.append(checkpoint)

    def pncp_pending_contratos(
        self,
        *,
        refresh_days,
        limit,
        offset=0,
        after_control=None,
        include_controls=(),
    ):
        del refresh_days
        eligible = [
            row
            for row in self.rows
            if (
                row[2] in self.recent
                or row[2] not in self.preserved
                or row[0] in include_controls
            )
            and (after_control is None or row[0] > after_control)
        ]
        return eligible[offset : offset + limit]

    def persist_contratos(self, page, *, control):
        self.preserved.add(page.number)
        self.visited.append(control)
        return SimpleNamespace(inserted_records=1, existing_records=0)


def page(number):
    return SimpleNamespace(
        number=number, cursor={"pagina": 1}, total_paginas=1, items=[{}]
    )


class ContractResumeTests(unittest.TestCase):
    def collect(self, repository, cursor=None):
        return command._collect_pending(
            repository=repository,
            service=repository,
            logger=logging.getLogger("test-contract-resume"),
            cursor=cursor or command.resolve_contract_checkpoint(None),
            checkpoint_progress=repository.checkpoint_progress,
        )

    @staticmethod
    def batch(*, ano, sequencial, logger):
        del ano, logger
        return command.PncpContratosPageBatch((page(sequencial),), False)

    def run_sweep(self, recent):
        repository = MutableBacklog(recent=recent)
        cursor = None
        outcomes = []
        with patch.object(command, "collect_contratos_batch", side_effect=self.batch):
            for _ in range(3):
                summary = self.collect(repository, cursor)
                outcomes.append(summary.outcome.value)
                cursor = command.resolve_contract_checkpoint(summary.checkpoint)
        self.assertEqual(repository.visited, [control(n) for n in range(1, 121)])
        self.assertEqual(outcomes, ["partial", "partial", "complete"])
        self.assertIsNone(cursor.after_control)

    def test_three_batches_do_not_skip_fifty_rows_removed_from_mutable_queue(self):
        self.run_sweep(recent=0)

    def test_recent_rows_staying_eligible_do_not_starve_history(self):
        self.run_sweep(recent=50)

    def test_legacy_offset_restarts_with_explicit_reason_and_keeps_pending_keys(self):
        cursor = command.resolve_contract_checkpoint(
            {
                "next_offset": 50,
                "contract_pages_truncated_controls": [control(3)],
            }
        )
        self.assertIsNone(cursor.after_control)
        self.assertEqual(cursor.restart_reason, "legacy_offset")
        self.assertEqual(cursor.retry_controls, (control(3),))
        repository = MutableBacklog()
        with patch.object(command, "collect_contratos_batch", side_effect=self.batch):
            summary = self.collect(repository, cursor)
        self.assertEqual(repository.visited[0], control(1))
        self.assertNotIn("next_offset", summary.checkpoint)
        self.assertEqual(summary.checkpoint["cursor_version"], 1)

    def test_truncated_control_is_not_lost_when_artifact_makes_it_ineligible(self):
        repository = MutableBacklog(count=51)
        with patch.object(
            command,
            "collect_contratos_batch",
            side_effect=[
                command.PncpContratosPageBatch((page(1),), True),
                *[
                    self.batch(ano=2025, sequencial=n, logger=None)
                    for n in range(2, 52)
                ],
            ],
        ):
            first = self.collect(repository)
            second = self.collect(
                repository, command.resolve_contract_checkpoint(first.checkpoint)
            )
        self.assertEqual(second.outcome.value, "partial")
        self.assertEqual(second.checkpoint["retry_controls"], [control(1)])
        with patch.object(command, "collect_contratos_batch", side_effect=self.batch):
            third = self.collect(
                repository, command.resolve_contract_checkpoint(second.checkpoint)
            )
        self.assertEqual(repository.visited.count(control(1)), 2)
        self.assertEqual(third.checkpoint["retry_controls"], [])
        self.assertEqual(third.outcome.value, "complete")

    def test_error_after_preserving_page_keeps_failed_and_prior_truncated_keys(self):
        repository = MutableBacklog(count=3)
        original = repository.persist_contratos

        def persist_then_fail(item, *, control):
            result = original(item, control=control)
            if item.number == 2:
                raise PncpError("source temporarily unavailable")
            return result

        completed = {}

        class ControlProbe:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def complete(self, **values):
                completed.update(values)

        repository.persist_contratos = persist_then_fail
        with patch.object(
            command,
            "collect_contratos_batch",
            side_effect=[
                command.PncpContratosPageBatch((page(1),), True),
                self.batch(ano=2025, sequencial=2, logger=None),
            ],
        ):
            with self.assertRaises(command.PncpContratosBatchFailure):
                command.execute_controlled_pncp_contratos(
                    control=ControlProbe(),
                    operation=lambda: self.collect(repository),
                )
        self.assertEqual(completed["outcome"].value, "partial")
        self.assertEqual(
            completed["checkpoint"]["retry_controls"], [control(1), control(2)]
        )
        self.assertIsNotNone(completed["partial_failure"])
        repository.persist_contratos = original
        with patch.object(command, "collect_contratos_batch", side_effect=self.batch):
            resumed = self.collect(
                repository, command.resolve_contract_checkpoint(completed["checkpoint"])
            )
            final = self.collect(
                repository, command.resolve_contract_checkpoint(resumed.checkpoint)
            )
        self.assertEqual(set(repository.visited), {control(1), control(2), control(3)})
        self.assertEqual(final.outcome.value, "complete")
        self.assertEqual(final.checkpoint["retry_controls"], [])

    def test_invalid_cursor_restarts_but_invalid_retry_cannot_be_silently_dropped(self):
        for invalid in (50, True, "", "not-a-control"):
            with self.subTest(invalid=invalid):
                cursor = command.resolve_contract_checkpoint(
                    {
                        "cursor_version": 1,
                        "next_after_control": invalid,
                        "retry_controls": [control(1)],
                    }
                )
                self.assertIsNone(cursor.after_control)
                self.assertEqual(cursor.restart_reason, "invalid_cursor")
                self.assertEqual(cursor.retry_controls, (control(1),))
        for invalid in ("not-a-list", ["not-a-control"], [None]):
            with self.subTest(invalid_retry=invalid):
                with self.assertRaises(ValueError):
                    command.resolve_contract_checkpoint(
                        {"cursor_version": 1, "retry_controls": invalid}
                    )

    def test_pending_key_missing_from_selection_is_not_declared_empty(self):
        repository = MutableBacklog(count=0)
        cursor = command.resolve_contract_checkpoint(
            {
                "cursor_version": 1,
                "retry_controls": [control(7)],
            }
        )
        summary = self.collect(repository, cursor)
        self.assertEqual(summary.outcome.value, "partial")
        self.assertEqual(summary.checkpoint["retry_controls"], [control(7)])

    def test_progress_checkpoint_is_required_before_fetching_any_page(self):
        repository = MutableBacklog(count=2)

        def unavailable(_checkpoint):
            raise RuntimeError("checkpoint unavailable")

        repository.checkpoint_progress = unavailable
        with patch.object(command, "collect_contratos_batch") as fetch:
            with self.assertRaisesRegex(RuntimeError, "checkpoint unavailable"):
                self.collect(repository)
        fetch.assert_not_called()
        self.assertEqual(repository.preserved, set())

    def test_invalid_selected_key_does_not_contaminate_durable_checkpoint(self):
        repository = MutableBacklog(count=1)
        repository.rows = [("not-a-control", 2025, 1)]
        with patch.object(command, "collect_contratos_batch") as fetch:
            with self.assertRaisesRegex(ValueError, "chave inválida"):
                self.collect(repository)
        self.assertEqual(repository.progress, [])
        fetch.assert_not_called()

    def test_real_control_does_not_double_finalize_partial_failure(self):
        repository = MutableBacklog(count=2)
        completed, failed = [], []
        repository.start_controlled_run = lambda **_values: "run-1"
        repository.complete_controlled_run = lambda **values: completed.append(values)
        repository.fail_controlled_run = lambda **values: failed.append(values)
        lifecycle = CollectionControl(
            repository=repository,
            source_code="pncp",
            endpoint_code="contratos-api",
            idempotency_key="pncp-contract-resume:test",
            collector_version="test",
            partition_key="backlog:contratos",
            period_start=date(2026, 9, 15),
            period_end=date(2026, 9, 15),
        )
        with patch.object(
            command, "collect_contratos_batch", side_effect=PncpError("unavailable")
        ):
            with self.assertRaises(command.PncpContratosBatchFailure):
                command.execute_controlled_pncp_contratos(
                    control=lifecycle,
                    operation=lambda: self.collect(repository),
                )
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["outcome"], "partial")
        self.assertEqual(failed, [])
        self.assertEqual(
            repository.progress[-1]["retry_controls"], [control(1), control(2)]
        )

    def test_main_returns_failure_for_known_retry_but_not_for_planned_batch_cap(self):
        for retries, expected in (((), 0), ((control(1),), 1)):
            summary = command.PncpContratosCollectionSummary(
                50,
                2,
                2,
                0,
                True,
                (),
                None,
                control(50),
                retries,
            )
            with (
                patch.object(
                    command.CollectorSettings,
                    "from_env",
                    return_value=SimpleNamespace(log_level="INFO"),
                ),
                patch.object(
                    command.PersistenceSettings,
                    "from_env",
                    return_value=SimpleNamespace(
                        mode="postgres-supabase", database_url="test"
                    ),
                ),
                patch.object(command.PostgresCollectionRepository, "from_dsn"),
                patch.object(
                    command, "execute_controlled_pncp_contratos", return_value=summary
                ),
                patch.object(command.logging, "basicConfig"),
            ):
                self.assertEqual(command.main([]), expected)

    def test_abrupt_interruption_retains_durable_reservation(self):
        repository = MutableBacklog(count=3)
        with patch.object(
            command,
            "collect_contratos_batch",
            side_effect=[
                command.PncpContratosPageBatch((page(1),), True),
                KeyboardInterrupt(),
            ],
        ):
            with self.assertRaises(KeyboardInterrupt):
                self.collect(repository)
        self.assertEqual(
            repository.progress[-1]["retry_controls"],
            [control(1), control(2), control(3)],
        )
        self.assertIsNone(repository.progress[-1]["next_after_control"])
        with patch.object(command, "collect_contratos_batch", side_effect=self.batch):
            resumed = self.collect(
                repository, command.resolve_contract_checkpoint(repository.progress[-1])
            )
        self.assertEqual(resumed.outcome.value, "complete")
        self.assertEqual(
            repository.visited, [control(1), control(1), control(2), control(3)]
        )

    def test_final_checkpoint_failure_leaves_prepared_reservation_available(self):
        repository = MutableBacklog(count=2)

        class ControlProbe:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def complete(self, **_values):
                raise RuntimeError("final checkpoint unavailable")

        with patch.object(command, "collect_contratos_batch", side_effect=self.batch):
            with self.assertRaisesRegex(RuntimeError, "final checkpoint unavailable"):
                command.execute_controlled_pncp_contratos(
                    control=ControlProbe(),
                    operation=lambda: self.collect(repository),
                )
            resumed = self.collect(
                repository, command.resolve_contract_checkpoint(repository.progress[-1])
            )
        self.assertEqual(resumed.outcome.value, "complete")
        self.assertEqual(
            repository.visited, [control(1), control(2), control(1), control(2)]
        )

    def test_empty_retry_is_not_silently_cleared(self):
        repository = MutableBacklog(count=1)
        cursor = command.resolve_contract_checkpoint(
            {
                "cursor_version": 1,
                "retry_controls": [control(1)],
            }
        )
        with patch.object(
            command,
            "collect_contratos_batch",
            return_value=command.PncpContratosPageBatch((), False),
        ):
            summary = self.collect(repository, cursor)
        self.assertEqual(summary.outcome.value, "partial")
        self.assertEqual(summary.checkpoint["retry_controls"], [control(1)])

    def test_thirty_truncated_retries_do_not_prevent_advance_to_later_keys(self):
        repository = MutableBacklog(count=120)
        cursor = None

        def batch(*, ano, sequencial, logger):
            result = self.batch(ano=ano, sequencial=sequencial, logger=logger)
            return command.PncpContratosPageBatch(result.pages, sequencial <= 30)

        with patch.object(command, "collect_contratos_batch", side_effect=batch):
            for _ in range(3):
                summary = self.collect(repository, cursor)
                cursor = command.resolve_contract_checkpoint(summary.checkpoint)
        self.assertEqual(repository.visited, [control(n) for n in range(1, 121)])
        self.assertEqual(len(cursor.retry_controls), 30)
        self.assertEqual(summary.outcome.value, "partial")


if __name__ == "__main__":
    unittest.main()
