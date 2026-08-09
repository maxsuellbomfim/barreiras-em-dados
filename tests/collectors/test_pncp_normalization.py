from __future__ import annotations

import unittest
from unittest.mock import Mock

from barreiras_collectors.persistence.postgres import (
    PostgresCollectionRepository,
)


class _Transaction:
    def __enter__(self) -> _Transaction:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class PncpNormalizationRepositoryTests(unittest.TestCase):
    def test_calls_security_definer_function_with_bounded_limit(self) -> None:
        connection = Mock()
        connection.transaction.return_value = _Transaction()
        connection.execute.side_effect = [
            Mock(),
            Mock(),
            Mock(
                fetchone=Mock(
                    return_value={
                        "procurements_inserted": 2,
                        "suppliers_inserted": 1,
                        "contracts_inserted": 5,
                        "contracts_skipped": 0,
                    }
                )
            ),
        ]
        repository = PostgresCollectionRepository(lambda: connection)

        result = repository.normalize_pncp_contracts(500)

        self.assertEqual(result["contracts_inserted"], 5)
        call = connection.execute.call_args_list[-1]
        self.assertIn("procurement.normalize_pncp_contracts", call.args[0])
        self.assertEqual(call.args[1], (500,))
        connection.close.assert_called_once_with()

    def test_rejects_unsafe_limit_before_opening_connection(self) -> None:
        factory = Mock()
        repository = PostgresCollectionRepository(factory)

        with self.assertRaises(ValueError):
            repository.normalize_pncp_contracts(5001)

        factory.assert_not_called()

    def test_calls_item_normalizer_with_bounded_limit(self) -> None:
        connection = Mock()
        connection.transaction.return_value = _Transaction()
        connection.execute.side_effect = [
            Mock(),
            Mock(),
            Mock(
                fetchone=Mock(
                    return_value={
                        "items_inserted": 12,
                        "items_skipped": 3,
                    }
                )
            ),
        ]
        repository = PostgresCollectionRepository(lambda: connection)

        result = repository.normalize_pncp_items(500)

        self.assertEqual(result["items_inserted"], 12)
        call = connection.execute.call_args_list[-1]
        self.assertIn("procurement.normalize_pncp_items", call.args[0])
        self.assertEqual(call.args[1], (500,))
        connection.close.assert_called_once_with()

    def test_item_normalizer_rejects_unsafe_limit_before_connection(self) -> None:
        factory = Mock()
        repository = PostgresCollectionRepository(factory)

        with self.assertRaises(ValueError):
            repository.normalize_pncp_items(5001)

        factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
