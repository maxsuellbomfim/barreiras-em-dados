from __future__ import annotations

import unittest
from unittest.mock import patch

from barreiras_collectors.commands.collect_municipal_transparency import (
    DEFAULT_RESOURCE,
    SOURCE_CONFIG,
    _bounded_env_int,
)


class MunicipalTransparencyCommandTests(unittest.TestCase):
    def test_sources_are_official_and_have_distinct_codes(self) -> None:
        self.assertEqual(
            set(SOURCE_CONFIG),
            {"prefeitura", "camara"},
        )
        self.assertNotEqual(SOURCE_CONFIG["prefeitura"][0], SOURCE_CONFIG["camara"][0])
        self.assertEqual(DEFAULT_RESOURCE, "pdc-resumo-execucao-da-receita")

    def test_bounded_env_int_rejects_values_outside_safe_window(self) -> None:
        with patch.dict("os.environ", {"TEST_MUNICIPAL_LIMIT": "61"}, clear=False):
            with self.assertRaises(RuntimeError):
                _bounded_env_int(
                    "TEST_MUNICIPAL_LIMIT",
                    default=10,
                    minimum=1,
                    maximum=60,
                )


if __name__ == "__main__":
    unittest.main()
