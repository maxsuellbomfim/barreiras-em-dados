from __future__ import annotations

import unittest
from datetime import UTC, datetime

from barreiras_reconciliation.identity_repository import IdentityRepository


class FakeResult:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, object]]:
        return self.rows


class FakeConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.queries: list[tuple[str, tuple[object, ...] | None]] = []
        self.closed = False

    def execute(
        self,
        query: str,
        params: tuple[object, ...] | None = None,
    ) -> FakeResult:
        self.queries.append((query, params))
        return FakeResult(self.rows)

    def close(self) -> None:
        self.closed = True


class IdentityRepositoryTests(unittest.TestCase):
    def test_scope_excludes_ticket_and_limits_state_and_federal_to_top_ten(
        self,
    ) -> None:
        connection = FakeConnection(
            [
                {
                    "source_kind": "municipal",
                    "representative_external_id": "cm:1",
                    "election_year": 2024,
                    "office": "Vereador",
                    "candidate_id": "123",
                    "origin_raw_record_id": "00000000-0000-4000-8000-000000000001",
                    "source_collected_at": datetime(2026, 8, 13, tzinfo=UTC),
                    "votes_in_barreiras": 321,
                }
            ]
        )
        repository = IdentityRepository(lambda: connection)

        targets = repository.eligible_targets(2024)

        query, params = connection.queries[0]
        normalized_query = " ".join(query.split()).lower()
        self.assertIn("crosswalk.vote_scope = 'person'", normalized_query)
        self.assertIn("record.payload ->> 'turno' = '1'", normalized_query)
        self.assertIn("territorial_rank <= 10", normalized_query)
        self.assertIn("crosswalk.review_status = 'approved'", normalized_query)
        self.assertEqual(params, (2024, 2024))
        self.assertEqual(targets[0].candidate_id, "123")
        self.assertEqual(targets[0].votes_in_barreiras, 321)
        self.assertTrue(connection.closed)


if __name__ == "__main__":
    unittest.main()
