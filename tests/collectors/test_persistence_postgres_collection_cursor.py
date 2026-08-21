from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from barreiras_collectors.persistence.models import PersistenceBatch
from barreiras_collectors.persistence.postgres import PostgresCollectionRepository


class _Result:
    @staticmethod
    def fetchone():
        return {"id": "run-id"}


class _Connection:
    def __init__(self) -> None:
        self.parameters: tuple[object, ...] = ()

    def execute(self, _query, parameters):
        self.parameters = parameters
        return _Result()


def _batch(cursor: dict[str, object], *, record_count: int = 2) -> PersistenceBatch:
    page = SimpleNamespace(
        cursor=cursor,
        body_size_bytes=100,
        http_status=200,
        collection_status="success",
        idempotency_key="run-key",
        window_start="2025-01-01",
        window_end="2025-12-31",
        attempts=1,
        requested_at="2026-08-21T12:00:00+00:00",
        received_at="2026-08-21T12:00:01+00:00",
    )
    return PersistenceBatch(
        page=page,  # type: ignore[arg-type]
        object_key="source/archive.zip",
        artifact_idempotency_key="artifact-key",
        collector_version="collector/1.0.0",
        parser_version="parser/1.0.0",
        records=tuple(SimpleNamespace() for _ in range(record_count)),  # type: ignore[arg-type]
    )


class PostgresCollectionCursorTests(unittest.TestCase):
    def test_preserves_opaque_annual_cursor_without_requiring_offset(self) -> None:
        connection = _Connection()

        run_id = PostgresCollectionRepository._collection_run_id(
            connection,  # type: ignore[arg-type]
            _batch({"year": 2025, "size": 2}),
            "endpoint-id",
        )

        self.assertEqual(run_id, "run-id")
        self.assertEqual(
            json.loads(str(connection.parameters[7])),
            {"year": 2025, "size": 2},
        )

    def test_advances_offset_cursor_without_discarding_extra_dimensions(self) -> None:
        connection = _Connection()

        PostgresCollectionRepository._collection_run_id(
            connection,  # type: ignore[arg-type]
            _batch({"offset": 50, "size": 25, "resource": "revenues"}),
            "endpoint-id",
        )

        self.assertEqual(
            json.loads(str(connection.parameters[7])),
            {"offset": 52, "size": 25, "resource": "revenues"},
        )


if __name__ == "__main__":
    unittest.main()
