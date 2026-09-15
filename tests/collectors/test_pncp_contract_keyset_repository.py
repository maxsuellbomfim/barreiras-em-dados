from __future__ import annotations

import unittest
from unittest.mock import Mock

from barreiras_collectors.persistence.postgres import PostgresCollectionRepository


class PncpContractKeysetRepositoryTests(unittest.TestCase):
    def test_binds_cursor_and_forced_controls_without_interpolation(self) -> None:
        connection = Mock()
        connection.execute.return_value.fetchall.return_value = [
            {"control": "official-2", "ano": "2026", "sequencial": "2"}
        ]
        repository = PostgresCollectionRepository(lambda: connection)
        cursor = "control'; select 1;--"
        controls = ("official-2", "official-3")

        result = repository.pncp_pending_contratos(
            refresh_days=120, limit=51, after_control=cursor,
            include_controls=controls,
        )

        query, params = connection.execute.call_args.args
        self.assertNotIn(cursor, query)
        self.assertNotIn("official-2", query)
        self.assertNotIn("offset", query.lower())
        self.assertIn('control collate "C" >', query)
        self.assertIn('order by control collate "C"', query)
        self.assertIn("any(%s::text[])", query)
        self.assertEqual(params, (120, list(controls), cursor, cursor, 51))
        self.assertEqual(result, [("official-2", 2026, 2)])
        connection.close.assert_called_once_with()

    def test_first_batch_binds_no_cursor_and_empty_forced_controls(self) -> None:
        connection = Mock()
        connection.execute.return_value.fetchall.return_value = []
        repository = PostgresCollectionRepository(lambda: connection)

        self.assertEqual(repository.pncp_pending_contratos(
            refresh_days=0, limit=1,
        ), [])

        self.assertEqual(connection.execute.call_args.args[1], (0, [], None, None, 1))
        connection.close.assert_called_once_with()

    def test_invalid_arguments_fail_before_opening_connection(self) -> None:
        invalid = [
            {"refresh_days": -1}, {"refresh_days": True}, {"refresh_days": "120"},
            {"limit": 0}, {"limit": False}, {"limit": 1.5},
            {"after_control": ""}, {"after_control": "   "},
            {"after_control": "bad\x00control"}, {"after_control": 7},
            {"include_controls": "not-a-sequence-of-controls"},
            {"include_controls": b"not-controls"},
            {"include_controls": (None,)}, {"include_controls": ("",)},
            {"include_controls": ("bad\x00control",)},
            {"include_controls": ("   ",)},
        ]
        for overrides in invalid:
            with self.subTest(overrides=overrides):
                factory = Mock()
                repository = PostgresCollectionRepository(factory)
                args = {"refresh_days": 120, "limit": 50, **overrides}
                with self.assertRaises(ValueError):
                    repository.pncp_pending_contratos(**args)
                factory.assert_not_called()

    def test_database_failure_propagates_and_closes_connection(self) -> None:
        connection = Mock()
        connection.execute.side_effect = RuntimeError("database unavailable")
        repository = PostgresCollectionRepository(lambda: connection)

        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            repository.pncp_pending_contratos(
                refresh_days=120, limit=50, after_control="official-1",
            )

        connection.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
