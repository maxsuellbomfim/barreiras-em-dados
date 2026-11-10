from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from barreiras_docproc.alias_repository import (
    MAX_OBSERVED_NAME_LENGTH,
    RepresentativeAliasRepository,
)
from barreiras_docproc.commands import suggest_representative_aliases as command


class _Rows:
    def fetchone(self):
        return None


class _Connection:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple]] = []

    def execute(self, sql, params=()):
        self.statements.append((sql, tuple(params)))
        return _Rows()

    def close(self) -> None:
        pass


class OversizedObservedNameTests(unittest.TestCase):
    def test_queue_sends_names_the_table_rejects_to_the_end(self) -> None:
        connection = _Connection()
        RepresentativeAliasRepository(lambda: connection).pending_author_aliases(7)
        sql, params = connection.statements[-1]
        self.assertLess(
            sql.index("(length(authors.author_name) > %s)"),
            sql.index("authors.item_count desc"),
        )
        self.assertEqual(params[-2:], (MAX_OBSERVED_NAME_LENGTH, 7))

    def test_oversized_name_is_skipped_without_aborting_the_batch(self) -> None:
        persisted: list[str] = []
        base = {
            "source_record_keys": ["leis:1"],
            "item_count": 1,
            "candidates": [],
            "historical_candidates": [],
        }

        class FakeRepository:
            def pending_author_aliases(self, limit):
                return (
                    {**base, "observed_name": "A" * (MAX_OBSERVED_NAME_LENGTH + 1)},
                    {**base, "observed_name": "Fulano de Tal"},
                )

            def persist_suggestion(self, **kwargs):
                persisted.append(kwargs["observed_name"])

        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                command.PersistenceSettings,
                "from_env",
                return_value=SimpleNamespace(database_url="postgresql://local"),
            ),
            patch.object(
                command.RepresentativeAliasRepository,
                "from_dsn",
                return_value=FakeRepository(),
            ),
            self.assertLogs(command.__name__, level="WARNING") as logs,
        ):
            self.assertEqual(command.main(["--limit", "5"]), 0)

        self.assertEqual(persisted, ["Fulano de Tal"])
        self.assertTrue(
            any("observed_name_too_long" in line for line in logs.output)
        )


if __name__ == "__main__":
    unittest.main()
