from __future__ import annotations

import unittest
from pathlib import Path

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

    def test_default_persistence_is_local_and_requires_no_secret(self) -> None:
        settings = PersistenceSettings.from_env({})

        self.assertEqual(settings.mode, "filesystem")
        self.assertEqual(
            settings.local_data_directory,
            Path("data") / "local-evidence",
        )
        self.assertIsNone(settings.database_url)

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
                "PERSISTENCE_MODE": "postgres-supabase",
                "DATABASE_URL": (
                    "postgresql://collector:password@db.example/"
                    "postgres?sslmode=require"
                ),
                "SUPABASE_URL": "https://project.supabase.co",
                "SUPABASE_SECRET_KEY": "testheader.testpayload.testsignature",
            }
        )

        self.assertEqual(settings.raw_artifacts_bucket, "raw-artifacts")
        self.assertEqual(settings.mode, "postgres-supabase")

    def test_rejects_remote_database_without_required_tls(self) -> None:
        with self.assertRaises(EnvironmentValidationError):
            PersistenceSettings.from_env(
                {
                    "PERSISTENCE_MODE": "postgres-supabase",
                    "DATABASE_URL": "postgresql://collector:password@db.example/db",
                    "SUPABASE_URL": "https://project.supabase.co",
                    "SUPABASE_SECRET_KEY": "testheader.testpayload.testsignature",
                }
            )

    def test_rejects_postgres_owner_as_production_worker(self) -> None:
        with self.assertRaises(EnvironmentValidationError):
            PersistenceSettings.from_env(
                {
                    "APP_ENV": "production",
                    "PERSISTENCE_MODE": "postgres-supabase",
                    "DATABASE_URL": (
                        "postgresql://postgres:password@db.example/"
                        "postgres?sslmode=require"
                    ),
                    "SUPABASE_URL": "https://project.supabase.co",
                    "SUPABASE_SECRET_KEY": "testheader.testpayload.testsignature",
                }
            )

    def test_rejects_filesystem_mode_outside_development_or_test(self) -> None:
        with self.assertRaises(EnvironmentValidationError):
            PersistenceSettings.from_env(
                {
                    "APP_ENV": "production",
                    "PERSISTENCE_MODE": "filesystem",
                }
            )

    def test_rejects_local_directory_traversal(self) -> None:
        for path in ("../outside", "data/../../outside", "C:\\outside"):
            with (
                self.subTest(path=path),
                self.assertRaises(EnvironmentValidationError),
            ):
                PersistenceSettings.from_env(
                    {
                        "PERSISTENCE_MODE": "filesystem",
                        "LOCAL_DATA_DIRECTORY": path,
                    }
                )


if __name__ == "__main__":
    unittest.main()
