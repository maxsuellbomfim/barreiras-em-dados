"""Guarda contra `%` solto em SQL parametrizado.

O driver trata `%` como início de marcador quando a consulta leva
parâmetros: `like 'automated:%'` derrubou a publicação em produção com
"only '%s', '%b', '%t' are allowed as placeholders". Testes com
repositório falso não exercitam SQL, então a checagem é sobre o fonte.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

MODULES = (
    Path(__file__).parents[2]
    / "workers"
    / "document-processing"
    / "src"
    / "barreiras_docproc"
    / "postgres.py",
    Path(__file__).parents[2]
    / "workers"
    / "collectors"
    / "src"
    / "barreiras_collectors"
    / "persistence"
    / "postgres.py",
)

# Marcadores válidos do psycopg e o escape literal.
_VALID = re.compile(r"%[sbt%]")


class SqlPlaceholderTests(unittest.TestCase):
    def test_no_bare_percent_in_sql_literals(self) -> None:
        for module in MODULES:
            source = module.read_text(encoding="utf-8")
            for line_number, line in enumerate(source.splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("--"):
                    continue
                if "%" not in line:
                    continue
                remaining = _VALID.sub("", line)
                self.assertNotIn(
                    "%",
                    remaining,
                    msg=(
                        f"{module.name}:{line_number} tem '%' solto em SQL; "
                        "escreva '%%' para o curinga do LIKE.\n"
                        f"  {stripped}"
                    ),
                )


if __name__ == "__main__":
    unittest.main()
