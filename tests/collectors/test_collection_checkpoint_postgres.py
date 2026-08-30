from __future__ import annotations

import unittest
from datetime import UTC, date, datetime

from barreiras_collectors.persistence.postgres import PostgresCollectionRepository


class QueryResult:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class CheckpointConnection:
    def __init__(self, row):
        self.row = row
        self.calls: list[tuple[str, tuple[object, ...] | None]] = []
        self.closed = False

    def execute(self, query, params=None):
        self.calls.append((query, params))
        return QueryResult(self.row)

    def close(self):
        self.closed = True


class CompletionConnection(CheckpointConnection):
    def transaction(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        del exc_type, exc_value, traceback
        return False

    def execute(self, query, params=None):
        self.calls.append((query, params))
        normalized = " ".join(query.lower().split())
        if normalized.startswith("update source.collection_runs"):
            return QueryResult(
                {
                    "endpoint_id": "00000000-0000-0000-0000-000000000001",
                    "attempt_count": 2,
                }
            )
        return QueryResult()


class CollectionCheckpointPostgresTests(unittest.TestCase):
    def test_partial_completion_persists_failure_without_resolving_it(self) -> None:
        connection = CompletionConnection(None)
        repository = PostgresCollectionRepository(lambda: connection)
        completed_at = datetime(2026, 8, 24, 15, 0, tzinfo=UTC)

        repository.complete_controlled_run(
            run_id="00000000-0000-0000-0000-000000000010",
            partition_key="snapshot:despesa",
            period_start=date(2023, 4, 1),
            period_end=date(2023, 4, 30),
            outcome="partial",
            observed_records=55,
            checkpoint={"next_offset": 0},
            metrics={"documents_failed": 1},
            block_reason=None,
            partial_failure={
                "error_type": "SourceContractError",
                "error_detail": "O documento oficial não é um PDF válido.",
                "retryable": True,
            },
            completed_at=completed_at,
        )

        queries = [" ".join(query.lower().split()) for query, _ in connection.calls]
        self.assertTrue(
            any(
                query.startswith("insert into source.collection_failures")
                for query in queries
            )
        )
        self.assertFalse(
            any(
                query.startswith("update source.collection_failures")
                for query in queries
            )
        )
        self.assertTrue(connection.closed)

    def test_complete_partition_resolves_prior_failure(self) -> None:
        connection = CompletionConnection(None)
        repository = PostgresCollectionRepository(lambda: connection)

        repository.complete_controlled_run(
            run_id="00000000-0000-0000-0000-000000000011",
            partition_key="snapshot:despesa",
            period_start=date(2023, 4, 1),
            period_end=date(2023, 4, 30),
            outcome="complete",
            observed_records=55,
            checkpoint={"next_offset": 0},
            metrics={"documents_failed": 0},
            block_reason=None,
            partial_failure=None,
            completed_at=datetime(2026, 8, 24, 16, 0, tzinfo=UTC),
        )

        queries = [" ".join(query.lower().split()) for query, _ in connection.calls]
        self.assertTrue(
            any(
                query.startswith("update source.collection_failures")
                for query in queries
            )
        )

    def test_returns_checkpoint_for_exact_source_endpoint_and_partition(self) -> None:
        connection = CheckpointConnection({"checkpoint": {"next_offset": 150}})
        repository = PostgresCollectionRepository(lambda: connection)

        checkpoint = repository.collection_partition_checkpoint(
            source_code="prefeitura-barreiras",
            endpoint_code="dados-abertos-api",
            partition_key="snapshot:pdc-resumo-execucao-da-receita",
        )

        self.assertEqual(checkpoint, {"next_offset": 150})
        self.assertEqual(
            connection.calls[0][1],
            (
                "prefeitura-barreiras",
                "dados-abertos-api",
                "snapshot:pdc-resumo-execucao-da-receita",
            ),
        )
        self.assertTrue(connection.closed)

    def test_missing_partition_returns_none(self) -> None:
        connection = CheckpointConnection(None)
        repository = PostgresCollectionRepository(lambda: connection)

        self.assertIsNone(
            repository.collection_partition_checkpoint(
                source_code="pncp",
                endpoint_code="consulta-contratacoes",
                partition_key="published:2026-07-01:2026-07-31",
            )
        )

    def test_pncp_item_backlog_applies_checkpoint_offset(self) -> None:
        connection = CheckpointConnection(None)
        connection.row = None
        repository = PostgresCollectionRepository(lambda: connection)

        repository.pncp_pending_itens(
            refresh_days=120,
            limit=51,
            offset=100,
        )

        self.assertIn("offset %s", connection.calls[0][0].lower())
        self.assertEqual(connection.calls[0][1], (120, 51, 100))

    def test_pncp_contract_backlog_applies_checkpoint_offset(self) -> None:
        connection = CheckpointConnection(None)
        repository = PostgresCollectionRepository(lambda: connection)

        repository.pncp_pending_contratos(
            refresh_days=120,
            limit=51,
            offset=50,
        )

        self.assertIn("offset %s", connection.calls[0][0].lower())
        self.assertEqual(connection.calls[0][1], (120, 51, 50))

    def test_pncp_backfill_anchor_uses_only_classified_control_partitions(
        self,
    ) -> None:
        class CoverageConnection(CheckpointConnection):
            def execute(self, query, params=None):
                self.calls.append((query, params))
                normalized = " ".join(query.lower().split())
                if (
                    "source.collection_partitions" in normalized
                    and "partition.status in ('complete', 'empty')" in normalized
                    and "run.status = 'succeeded'" in normalized
                ):
                    return QueryResult({"anchor": date(2025, 6, 8)})
                return QueryResult({"anchor": date(2025, 4, 9)})

        connection = CoverageConnection(None)
        repository = PostgresCollectionRepository(lambda: connection)

        self.assertEqual(repository.pncp_backfill_anchor(), date(2025, 6, 8))
        self.assertTrue(connection.closed)

    def test_tcm_document_planner_respects_open_retry_schedule(self) -> None:
        connection = CheckpointConnection(None)
        repository = PostgresCollectionRepository(lambda: connection)

        self.assertIsNone(
            repository.next_tcm_ba_document_competence(year_from=2021)
        )

        query, params = connection.calls[0]
        normalized = " ".join(query.lower().split())
        self.assertIn("source.collection_failures", normalized)
        self.assertIn("failure.status <> 'resolved'", normalized)
        self.assertIn("failure.error_type = 'tcmbaerror'", normalized)
        self.assertIn("failure.status = 'dead_lettered'", normalized)
        self.assertIn("or not failure.retryable", normalized)
        self.assertIn("failure.failed_at + interval '1 hour'", normalized)
        self.assertIn("> statement_timestamp()", normalized)
        self.assertIn("failure.partition_key = replace", normalized)
        self.assertEqual(params, (2021,))
        self.assertTrue(connection.closed)


if __name__ == "__main__":
    unittest.main()
