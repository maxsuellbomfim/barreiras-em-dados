from __future__ import annotations

import unittest
from datetime import UTC, datetime

from barreiras_reconciliation.identity_repository import (
    IdentifierGapRegistration,
    IdentityRepository,
    IdentityTarget,
)
from barreiras_reconciliation.private_identifiers import ProtectedSourcePayload


class FakeResult:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, object]]:
        return self.rows

    def fetchone(self) -> dict[str, object] | None:
        return self.rows[0] if self.rows else None


class FakeTransaction:
    def __enter__(self) -> object:
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> bool:
        return False


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

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()


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

    def test_registers_unavailable_identifier_through_restricted_rpc(self) -> None:
        connection = FakeConnection([{"status": "inserted"}])
        repository = IdentityRepository(lambda: connection)
        target = IdentityTarget(
            source_kind="municipal",
            source_external_id="cm:1",
            election_year=2024,
            office="Vereador",
            candidate_id="123",
            origin_raw_record_id="00000000-0000-4000-8000-000000000001",
            source_collected_at=datetime(2026, 8, 13, tzinfo=UTC),
            votes_in_barreiras=321,
        )
        registration = IdentifierGapRegistration(
            target=target,
            source_record_key="candidate:2024:123",
            source_url="https://cdn.tse.jus.br/source.zip",
            archive_sha256="a" * 64,
            state_file_sha256="b" * 64,
            parser_version="tse-candidate-registry/1.1.0",
            reason="invalid_official_value",
            protected_source=ProtectedSourcePayload(
                encrypted_payload=b"ciphertext",
                nonce=b"n" * 12,
                authentication_tag=b"t" * 16,
                payload_sha256="c" * 64,
                key_version=1,
            ),
        )

        status = repository.register_unavailable(registration)

        query, params = connection.queries[2]
        self.assertIn("identity.register_tse_identifier_gap", query)
        self.assertNotIn("11111111111", repr(params))
        self.assertEqual(status, "inserted")
        self.assertTrue(connection.closed)


if __name__ == "__main__":
    unittest.main()
