from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from barreiras_collectors.persistence.models import PersistenceContractError
from barreiras_collectors.persistence.postgres import PostgresCollectionRepository


class _Result:
    def __init__(self, row: dict[str, int]) -> None:
        self.row = row

    def fetchone(self) -> dict[str, int]:
        return self.row


class _Connection:
    def __init__(self, row: dict[str, int]) -> None:
        self.row = row
        self.calls: list[tuple[str, tuple[object, ...] | None]] = []

    def execute(
        self,
        query: str,
        params: tuple[object, ...] | None = None,
    ) -> _Result:
        self.calls.append((query, params))
        return _Result(self.row)


def _batch(record_count: int = 3) -> SimpleNamespace:
    records = tuple(
        SimpleNamespace(
            source_record_key=f"siconfi:dca:2021:{index}",
            record_type="siconfi_dca_line",
            record_index=index,
            payload={"exercicio": 2021, "linha": index},
            payload_sha256=f"{index + 1:064x}",
            parser_version="siconfi-dca/1.0.0",
            idempotency_key=f"siconfi:dca:2021:{index}:v1",
        )
        for index in range(record_count)
    )
    return SimpleNamespace(
        records=records,
        page=SimpleNamespace(received_at="2026-08-24T12:00:00Z", body_sha256="a" * 64),
    )


class PostgresBulkRecordsTests(unittest.TestCase):
    def test_inserts_entire_batch_in_one_database_statement(self) -> None:
        connection = _Connection(
            {"inserted_records": 3, "existing_records": 0, "conflicting_records": 0}
        )

        result = PostgresCollectionRepository._records(
            connection,  # type: ignore[arg-type]
            _batch(),  # type: ignore[arg-type]
            "00000000-0000-0000-0000-000000000001",
        )

        self.assertEqual(result, (3, 0))
        self.assertEqual(len(connection.calls), 1)
        query, params = connection.calls[0]
        self.assertIn("jsonb_to_recordset", query)
        self.assertIsNotNone(params)
        payload = json.loads(str(params[0]))
        self.assertEqual(len(payload), 3)
        self.assertEqual(payload[0]["source_record_key"], "siconfi:dca:2021:0")

    def test_rejects_any_incompatible_existing_record(self) -> None:
        connection = _Connection(
            {"inserted_records": 0, "existing_records": 2, "conflicting_records": 1}
        )

        with self.assertRaisesRegex(
            PersistenceContractError,
            "Conflito de idempotência em registro bruto",
        ):
            PostgresCollectionRepository._records(
                connection,  # type: ignore[arg-type]
                _batch(2),  # type: ignore[arg-type]
                "00000000-0000-0000-0000-000000000001",
            )


if __name__ == "__main__":
    unittest.main()
