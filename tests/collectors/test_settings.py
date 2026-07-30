from __future__ import annotations

import unittest

from barreiras_collectors.settings import (
    CollectorSettings,
    EnvironmentValidationError,
    PersistenceSettings,
)


class CollectorSettingsTests(unittest.TestCase):
    def test_defaults_are_safe_and_municipal(self) -> None:
        settings = CollectorSettings.from_env({})

        self.assertEqual(settings.querido_diario_territory_id, "2903201")
        self.assertEqual(settings.requests_per_minute, 30)
        self.assertEqual(settings.raw_artifacts_bucket, "raw-artifacts")

    def test_rejects_non_official_or_insecure_api_host(self) -> None:
        for url in (
            "http://api.queridodiario.ok.org.br",
            "https://127.0.0.1",
            "https://api.queridodiario.ok.org.br.evil.example",
        ):
            with self.subTest(url=url), self.assertRaises(EnvironmentValidationError):
                CollectorSettings.from_env({"QUERIDO_DIARIO_BASE_URL": url})

    def test_rejects_other_municipality(self) -> None:
        with self.assertRaises(EnvironmentValidationError):
            CollectorSettings.from_env({"QUERIDO_DIARIO_TERRITORY_ID": "2927408"})

    def test_rejects_rate_above_documented_api_limit(self) -> None:
        with self.assertRaises(EnvironmentValidationError):
            CollectorSettings.from_env({"QUERIDO_DIARIO_REQUESTS_PER_MINUTE": "61"})

    def test_rejects_server_secret_with_public_prefix(self) -> None:
        with self.assertRaises(EnvironmentValidationError):
            CollectorSettings.from_env(
                {"NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY": "must-not-leak"}
            )

    def test_persistence_settings_require_tls_and_dedicated_secret(self) -> None:
        settings = PersistenceSettings.from_env(
            {
                "APP_ENV": "development",
                "DATABASE_URL": (
                    "postgresql://collector:password@db.example/"
                    "postgres?sslmode=require"
                ),
                "SUPABASE_URL": "https://project.supabase.co",
                "SUPABASE_SECRET_KEY": "sb_secret_example_key_long_enough",
            }
        )

        self.assertEqual(settings.raw_artifacts_bucket, "raw-artifacts")

    def test_rejects_remote_database_without_required_tls(self) -> None:
        with self.assertRaises(EnvironmentValidationError):
            PersistenceSettings.from_env(
                {
                    "DATABASE_URL": "postgresql://collector:password@db.example/db",
                    "SUPABASE_URL": "https://project.supabase.co",
                    "SUPABASE_SECRET_KEY": "sb_secret_example_key_long_enough",
                }
            )

    def test_rejects_postgres_owner_as_production_worker(self) -> None:
        with self.assertRaises(EnvironmentValidationError):
            PersistenceSettings.from_env(
                {
                    "APP_ENV": "production",
                    "DATABASE_URL": (
                        "postgresql://postgres:password@db.example/"
                        "postgres?sslmode=require"
                    ),
                    "SUPABASE_URL": "https://project.supabase.co",
                    "SUPABASE_SECRET_KEY": "sb_secret_example_key_long_enough",
                }
            )


if __name__ == "__main__":
    unittest.main()
