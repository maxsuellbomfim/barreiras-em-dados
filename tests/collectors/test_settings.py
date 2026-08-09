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

        self.assertEqual(settings.log_level, "INFO")
        self.assertEqual(settings.querido_diario_territory_id, "2903201")
        self.assertEqual(settings.requests_per_minute, 30)

    def test_rejects_invalid_log_level(self) -> None:
        with self.assertRaises(EnvironmentValidationError):
            CollectorSettings.from_env({"LOG_LEVEL": "verbose"})

    def test_default_persistence_is_local_and_requires_no_secret(self) -> None:
        settings = PersistenceSettings.from_env({})

        self.assertEqual(settings.mode, "filesystem")
        self.assertEqual(
            settings.local_data_directory,
            Path("data") / "local-evidence",
        )
        self.assertIsNone(settings.database_url)
        self.assertIsNone(settings.supabase_workload_password)

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

    def test_accepts_large_official_pdf_limit_within_safe_cap(self) -> None:
        settings = CollectorSettings.from_env(
            {"QUERIDO_DIARIO_MAX_DOCUMENT_BYTES": str(128 * 1024 * 1024)}
        )
        self.assertEqual(settings.max_document_bytes, 128 * 1024 * 1024)

    def test_rejects_unbounded_official_pdf_limit(self) -> None:
        with self.assertRaises(EnvironmentValidationError):
            CollectorSettings.from_env(
                {"QUERIDO_DIARIO_MAX_DOCUMENT_BYTES": str(256 * 1024 * 1024 + 1)}
            )

    def test_rejects_server_secret_with_public_prefix(self) -> None:
        with self.assertRaises(EnvironmentValidationError):
            CollectorSettings.from_env(
                {"NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY": "must-not-leak"}
            )

    def test_persistence_settings_require_scoped_workload_credentials(self) -> None:
        settings = PersistenceSettings.from_env(
            {
                "APP_ENV": "development",
                "PERSISTENCE_MODE": "postgres-supabase",
                "DATABASE_URL": (
                    "postgresql://collector_querido_diario:password@db.example/"
                    "postgres?sslmode=require"
                ),
                "SUPABASE_URL": "https://project.supabase.co",
                "SUPABASE_PUBLISHABLE_KEY": ("sb_publishable_000000000000000000000000"),
                "SUPABASE_WORKLOAD_EMAIL": "collector@example.org",
                "SUPABASE_WORKLOAD_PASSWORD": "a-strong-workload-password-123",
            }
        )

        self.assertEqual(settings.raw_artifacts_bucket, "raw-artifacts")
        self.assertEqual(settings.mode, "postgres-supabase")
        self.assertIsNone(getattr(settings, "supabase_secret_key", None))

    def test_rejects_remote_database_without_required_tls(self) -> None:
        with self.assertRaises(EnvironmentValidationError):
            PersistenceSettings.from_env(
                {
                    "PERSISTENCE_MODE": "postgres-supabase",
                    "DATABASE_URL": (
                        "postgresql://collector_querido_diario:password@db.example/db"
                    ),
                    "SUPABASE_URL": "https://project.supabase.co",
                    "SUPABASE_PUBLISHABLE_KEY": (
                        "sb_publishable_000000000000000000000000"
                    ),
                    "SUPABASE_WORKLOAD_EMAIL": "collector@example.org",
                    "SUPABASE_WORKLOAD_PASSWORD": ("a-strong-workload-password-123"),
                }
            )

    def test_production_requires_verify_full_and_versioned_ca(self) -> None:
        base = {
            "APP_ENV": "production",
            "PERSISTENCE_MODE": "postgres-supabase",
            "SUPABASE_URL": "https://project.supabase.co",
            "SUPABASE_PUBLISHABLE_KEY": ("sb_publishable_000000000000000000000000"),
            "SUPABASE_WORKLOAD_EMAIL": "collector@example.org",
            "SUPABASE_WORKLOAD_PASSWORD": "a-strong-workload-password-123",
        }
        for database_url in (
            (
                "postgresql://collector_querido_diario:password@db.example/"
                "postgres?sslmode=require"
            ),
            (
                "postgresql://collector_querido_diario:password@db.example/"
                "postgres?sslmode=verify-full"
            ),
            (
                "postgresql://collector_querido_diario:password@db.example/"
                "postgres?sslmode=verify-full&sslrootcert=other.crt"
            ),
            (
                "postgresql://collector_querido_diario:password@db.example/"
                "postgres?sslmode=verify-full&sslrootcert=/tmp/"
                "supabase-prod-ca-2021.crt"
            ),
        ):
            with self.subTest(database_url=database_url):
                with self.assertRaises(EnvironmentValidationError):
                    PersistenceSettings.from_env({**base, "DATABASE_URL": database_url})

        settings = PersistenceSettings.from_env(
            {
                **base,
                "DATABASE_URL": (
                    "postgresql://collector_querido_diario:password@db.example/"
                    "postgres?sslmode=verify-full&sslrootcert=config/"
                    "certificates/supabase-prod-ca-2021.crt"
                ),
            }
        )

        self.assertEqual(settings.mode, "postgres-supabase")

    def test_rejects_any_remote_database_role_except_dedicated_worker(
        self,
    ) -> None:
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
                    "SUPABASE_PUBLISHABLE_KEY": (
                        "sb_publishable_000000000000000000000000"
                    ),
                    "SUPABASE_WORKLOAD_EMAIL": "collector@example.org",
                    "SUPABASE_WORKLOAD_PASSWORD": ("a-strong-workload-password-123"),
                }
            )

    def test_rejects_broad_supabase_secret_for_collector(self) -> None:
        with self.assertRaises(EnvironmentValidationError):
            PersistenceSettings.from_env(
                {
                    "PERSISTENCE_MODE": "postgres-supabase",
                    "DATABASE_URL": (
                        "postgresql://collector_querido_diario:password@"
                        "db.example/postgres?sslmode=require"
                    ),
                    "SUPABASE_URL": "https://project.supabase.co",
                    "SUPABASE_PUBLISHABLE_KEY": (
                        "sb_publishable_000000000000000000000000"
                    ),
                    "SUPABASE_WORKLOAD_EMAIL": "collector@example.org",
                    "SUPABASE_WORKLOAD_PASSWORD": ("a-strong-workload-password-123"),
                    "SUPABASE_SECRET_KEY": (
                        "sb_secret_this-key-must-not-be-used-by-collector"
                    ),
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
