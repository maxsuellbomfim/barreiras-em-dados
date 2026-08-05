from __future__ import annotations

import unittest

from barreiras_collectors.persistence.postgres import PostgresCollectionRepository


class QueryResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row

    def fetchall(self):
        return []


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


if __name__ == "__main__":
    unittest.main()
