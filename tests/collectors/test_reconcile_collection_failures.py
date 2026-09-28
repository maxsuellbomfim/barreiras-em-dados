import unittest
from contextlib import nullcontext

from barreiras_collectors.commands.reconcile_collection_failures import reconcile


class FakeConnection:
    def __init__(self) -> None:
        self.sql: list[str] = []
        self.closed = False

    def transaction(self):
        return nullcontext()

    def execute(self, sql: str):
        self.sql.append(sql)
        return self

    def fetchall(self):
        return [
            {"rule": "same_partition_recovered", "resolved_count": 0},
            {"rule": "covered_by_primary_source", "resolved_count": 143},
        ]

    def close(self) -> None:
        self.closed = True


class FakeRepository:
    def __init__(self) -> None:
        self.connection = FakeConnection()

    def connection_factory(self):
        return self.connection


class ReconcileCollectionFailuresTest(unittest.TestCase):
    def test_delegates_to_versioned_sql_function_and_closes(self) -> None:
        repository = FakeRepository()
        counts = reconcile(repository)  # type: ignore[arg-type]
        self.assertEqual(
            counts,
            {"same_partition_recovered": 0, "covered_by_primary_source": 143},
        )
        self.assertIn(
            "source.reconcile_collection_failures()", repository.connection.sql[0]
        )
        self.assertTrue(repository.connection.closed)


if __name__ == "__main__":
    unittest.main()
