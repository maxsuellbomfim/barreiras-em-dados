from __future__ import annotations

import base64
import unittest


def _environment(**overrides: str) -> dict[str, str]:
    values = {
        "APP_ENV": "production",
        "IDENTITY_DATABASE_URL": (
            "postgresql://identity_registry.project:password@db.example.com:5432/"
            "postgres?sslmode=verify-full&sslrootcert="
            "config/certificates/supabase-prod-ca-2021.crt"
        ),
        "IDENTITY_AES_KEY_B64": base64.b64encode(bytes(range(32))).decode(),
        "IDENTITY_HMAC_KEY_B64": base64.b64encode(bytes(range(32, 64))).decode(),
        "IDENTITY_KEY_VERSION": "1",
    }
    values.update(overrides)
    return values


class IdentitySettingsTests(unittest.TestCase):
    def _settings(self, values: dict[str, str]):
        try:
            from barreiras_reconciliation.identity_settings import IdentitySettings
        except ImportError:
            self.fail("as configuracoes privadas de identidade ainda nao existem")
        return IdentitySettings.from_env(values)

    def test_accepts_exclusive_role_and_two_distinct_256_bit_keys(self) -> None:
        environment = _environment()
        settings = self._settings(environment)

        self.assertEqual(settings.database_role, "identity_registry")
        self.assertEqual(len(settings.encryption_key), 32)
        self.assertEqual(len(settings.fingerprint_key), 32)
        self.assertEqual(settings.key_version, 1)
        representation = repr(settings)
        self.assertNotIn("password", representation)
        self.assertNotIn(environment["IDENTITY_AES_KEY_B64"], representation)
        self.assertNotIn(environment["IDENTITY_HMAC_KEY_B64"], representation)

    def test_rejects_collector_or_postgres_database_role(self) -> None:
        for role in ("collector_querido_diario", "postgres"):
            with self.subTest(role=role), self.assertRaisesRegex(
                ValueError,
                "identity_registry",
            ):
                self._settings(
                    _environment(
                        IDENTITY_DATABASE_URL=(
                            f"postgresql://{role}.project:password@db.example.com:5432/"
                            "postgres?sslmode=verify-full&sslrootcert="
                            "config/certificates/supabase-prod-ca-2021.crt"
                        )
                    )
                )

    def test_rejects_equal_short_or_malformed_keys(self) -> None:
        valid = base64.b64encode(bytes(range(32))).decode()
        invalid_cases = (
            {"IDENTITY_HMAC_KEY_B64": valid},
            {"IDENTITY_AES_KEY_B64": base64.b64encode(b"short").decode()},
            {"IDENTITY_AES_KEY_B64": "not-base64"},
        )
        for overrides in invalid_cases:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self._settings(_environment(**overrides))

    def test_remote_connection_requires_full_tls_verification(self) -> None:
        insecure_url = (
            "postgresql://identity_registry.project:password@db.example.com:5432/"
            "postgres?sslmode=require"
        )
        with self.assertRaisesRegex(ValueError, "verify-full"):
            self._settings(_environment(IDENTITY_DATABASE_URL=insecure_url))


if __name__ == "__main__":
    unittest.main()
