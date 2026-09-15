from __future__ import annotations

import json
import unittest
from datetime import date
from unittest.mock import MagicMock, Mock

from barreiras_collectors.persistence.models import PersistenceContractError
from barreiras_collectors.persistence.postgres import PostgresCollectionRepository

RUN_ID = "00000000-0000-4000-8000-000000000001"
ENDPOINT_ID = "00000000-0000-4000-8000-000000000002"


def fixture(*, run_exists: bool = True, partition_error: Exception | None = None):
    connection = MagicMock()
    run = {
        "endpoint_id": ENDPOINT_ID,
        "period_start": date(2026, 9, 7),
        "period_end": date(2026, 9, 14),
    }

    def execute(query, params=None):
        result = Mock()
        normalized = " ".join(query.lower().split())
        if normalized.startswith("update source.collection_runs"):
            result.fetchone.return_value = run if run_exists else None
        elif normalized.startswith("insert into source.collection_partitions"):
            if partition_error is not None:
                raise partition_error
        return result

    connection.execute.side_effect = execute
    return PostgresCollectionRepository(lambda: connection), connection


class PncpContractCheckpointProgressTests(unittest.TestCase):
    def test_reserves_all_retries_without_completing_or_resolving(self) -> None:
        repository, connection = fixture()
        checkpoint = {
            "cursor_version": 2,
            "next_after_control": "13654405000195-1-000099/2023",
            "retry_controls": [f"13654405000195-1-{i:06d}/2023" for i in range(1, 151)],
            "pending_truncated": True,
            "contract_pages_truncated_controls": [],
        }

        repository.pncp_contract_checkpoint_progress(
            run_id=RUN_ID, checkpoint=checkpoint,
        )

        calls = connection.execute.call_args_list
        self.assertEqual(len(calls), 4)
        self.assertEqual(calls[0].args, ("set local statement_timeout = '15s'",))
        self.assertEqual(calls[1].args, ("set local lock_timeout = '5s'",))
        update, update_params = calls[2].args
        insert, insert_params = calls[3].args
        self.assertEqual(json.loads(update_params[0]), checkpoint)
        self.assertEqual(update_params[1], RUN_ID)
        self.assertEqual(insert_params[:4], (
            ENDPOINT_ID, date(2026, 9, 7), date(2026, 9, 14), RUN_ID,
        ))
        self.assertEqual(json.loads(insert_params[4]), checkpoint)
        normalized_update = " ".join(update.lower().split())
        self.assertIn("run.status = 'running'", normalized_update)
        self.assertIn("source.slug = 'pncp'", normalized_update)
        self.assertIn("endpoint.slug = 'contratos-api'", normalized_update)
        self.assertIn("run.source_endpoint_id = endpoint.id", normalized_update)
        self.assertIn("run.collection_window_start as period_start", normalized_update)
        self.assertIn("run.collection_window_end as period_end", normalized_update)
        self.assertNotIn("set status", normalized_update)
        self.assertNotIn("completed_at =", normalized_update)
        self.assertNotIn("metrics =", normalized_update)
        self.assertIn("'backlog:contratos'", insert)
        self.assertIn("'partial'", insert)
        self.assertIn("completed_at = null", insert.lower())
        self.assertIn("observed_records = 0", insert.lower())
        for call in calls:
            self.assertNotIn("collection_failures", call.args[0])
            self.assertNotIn("public.", call.args[0])
            self.assertNotIn("decision", call.args[0])
        connection.transaction.return_value.__enter__.assert_called_once_with()
        connection.transaction.return_value.__exit__.assert_called_once_with(
            None, None, None,
        )
        connection.close.assert_called_once_with()

    def test_missing_or_out_of_scope_run_aborts_before_partition_write(self) -> None:
        repository, connection = fixture(run_exists=False)

        with self.assertRaises(PersistenceContractError):
            repository.pncp_contract_checkpoint_progress(run_id=RUN_ID, checkpoint={})

        self.assertEqual(connection.execute.call_count, 3)
        transaction_exit = connection.transaction.return_value.__exit__
        self.assertIs(transaction_exit.call_args.args[0], PersistenceContractError)
        connection.close.assert_called_once_with()

    def test_partition_failure_rolls_back_run_checkpoint_and_propagates(self) -> None:
        error = RuntimeError("partition unavailable")
        repository, connection = fixture(partition_error=error)

        with self.assertRaises(RuntimeError) as raised:
            repository.pncp_contract_checkpoint_progress(run_id=RUN_ID, checkpoint={})

        self.assertIs(raised.exception, error)
        self.assertEqual(connection.execute.call_count, 4)
        transaction_exit = connection.transaction.return_value.__exit__
        self.assertIs(transaction_exit.call_args.args[0], RuntimeError)
        self.assertIs(transaction_exit.call_args.args[1], error)
        connection.close.assert_called_once_with()

    def test_invalid_arguments_fail_before_connection(self) -> None:
        for overrides in (
            {"run_id": ""}, {"run_id": "   "}, {"run_id": "bad\x00id"},
            {"run_id": None}, {"checkpoint": []}, {"checkpoint": None},
        ):
            with self.subTest(overrides=overrides):
                factory = Mock()
                repository = PostgresCollectionRepository(factory)
                with self.assertRaises(ValueError):
                    repository.pncp_contract_checkpoint_progress(**{
                        "run_id": RUN_ID, "checkpoint": {}, **overrides,
                    })
                factory.assert_not_called()

    def test_unserializable_checkpoint_fails_before_connection(self) -> None:
        factory = Mock()
        repository = PostgresCollectionRepository(factory)
        with self.assertRaises(TypeError):
            repository.pncp_contract_checkpoint_progress(
                run_id=RUN_ID, checkpoint={"retry_controls": object()},
            )
        factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
