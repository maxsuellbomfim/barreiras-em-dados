from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[2]
CONTROLLED_COMMANDS = (
    "collect_querido_diario.py",
    "collect_pncp_registry.py",
    "collect_pncp_contratacoes.py",
    "collect_pncp_itens.py",
    "collect_pncp_contratos.py",
)


class ControlledCommandVersionTests(unittest.TestCase):
    def test_versions_are_owned_by_sources_not_runtime_settings(self) -> None:
        commands_dir = (
            ROOT
            / "workers"
            / "collectors"
            / "src"
            / "barreiras_collectors"
            / "commands"
        )

        invalid_references: list[str] = []
        for filename in CONTROLLED_COMMANDS:
            source = (commands_dir / filename).read_text(encoding="utf-8")
            tree = ast.parse(source, filename=filename)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Attribute):
                    continue
                if node.attr != "collector_version":
                    continue
                if not isinstance(node.value, ast.Name):
                    continue
                if node.value.id == "collector_settings":
                    invalid_references.append(f"{filename}:{node.lineno}")

        self.assertEqual(
            invalid_references,
            [],
            "versão do coletor deve vir do contrato da fonte: "
            + ", ".join(invalid_references),
        )


if __name__ == "__main__":
    unittest.main()
