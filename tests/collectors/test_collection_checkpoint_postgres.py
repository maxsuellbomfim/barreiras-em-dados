from __future__ import annotations

import unittest
from datetime import date

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


class CollectionCheckpointPostgresTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
