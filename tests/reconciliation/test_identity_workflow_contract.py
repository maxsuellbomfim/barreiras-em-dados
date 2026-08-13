from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class IdentityWorkflowContractTests(unittest.TestCase):
    def test_representation_workflow_runs_private_import_only_with_dedicated_secrets(
        self,
    ) -> None:
        workflow = (ROOT / ".github/workflows/collect-representation.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("Registrar identidades privadas oficiais", workflow)
        self.assertIn(
            "barreiras_reconciliation.commands.import_tse_identities",
            workflow,
        )
        self.assertIn("workers/reconciliation/src", workflow)
        self.assertIn("IDENTITY_DATABASE_URL", workflow)
        self.assertIn("IDENTITY_AES_KEY_B64", workflow)
        self.assertIn("IDENTITY_HMAC_KEY_B64", workflow)
        self.assertIn("steps.identity_secrets.outputs.configured == 'true'", workflow)
        self.assertNotIn("IDENTITY_DATABASE_URL: ${{ secrets.QUERIDO", workflow)

    def test_command_source_never_prints_private_identity_fields(self) -> None:
        command = ROOT / (
            "workers/reconciliation/src/barreiras_reconciliation/commands/"
            "import_tse_identities.py"
        )
        self.assertTrue(command.exists())
        source = command.read_text(encoding="utf-8").casefold()
        for forbidden in (".cpf", "last_four", '"fingerprint"', "encrypted_value"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
