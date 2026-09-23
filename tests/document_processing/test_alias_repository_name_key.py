from __future__ import annotations

import re
import unittest
from pathlib import Path

from barreiras_docproc.alias_repository import _with_name_keys

MIGRATION = (
    Path(__file__).parents[2]
    / "supabase"
    / "migrations"
    / "20260808230000_current_author_filter_aliases.sql"
)


class AliasNameKeyTests(unittest.TestCase):
    def test_worker_key_matches_public_author_normalization(self) -> None:
        public = MIGRATION.read_text(encoding="utf-8")
        body = re.search(
            r"select (lower\(btrim\(regexp_replace\(\s*regexp_replace\(value.*?\)\)\))",
            public,
            re.DOTALL,
        )
        self.assertIsNotNone(body)
        expected = re.sub(r"\s+", " ", body.group(1)).replace("( ", "(")
        expanded = _with_name_keys("{name_key}(value)")
        self.assertEqual(expanded.replace(" ", ""), expected.replace(" ", ""))

    def test_only_marked_calls_are_expanded(self) -> None:
        sql = _with_name_keys("{name_key}(a.x) = lower(b.y)")
        self.assertTrue(sql.endswith("= lower(b.y)"))
        self.assertNotIn("{name_key}", sql)


if __name__ == "__main__":
    unittest.main()
