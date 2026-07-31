from __future__ import annotations

import secrets
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from barreiras_collectors.commands.collect_querido_diario import (
    _build_persistence_service,
)
from barreiras_collectors.settings import PersistenceSettings


class _FakeAuth:
    def __init__(self) -> None:
        self.credentials: dict[str, str] | None = None

    def sign_in_with_password(
        self,
        credentials: dict[str, str],
    ) -> SimpleNamespace:
        self.credentials = credentials
        return SimpleNamespace(session=object(), user=object())


class _FakeStorage:
    def __init__(self) -> None:
        self.bucket: str | None = None

    def from_(self, bucket: str) -> object:
        self.bucket = bucket
        return object()


class _FakeSupabaseClient:
    def __init__(self) -> None:
        self.auth = _FakeAuth()
        self.storage = _FakeStorage()


class CollectorCommandTests(unittest.TestCase):
    def test_cloud_mode_authenticates_with_publishable_key_and_workload(
        self,
    ) -> None:
        client = _FakeSupabaseClient()
        client_creation: dict[str, str] = {}
        workload_password = secrets.token_urlsafe(24)

        def create_client(url: str, key: str) -> _FakeSupabaseClient:
            client_creation.update(url=url, key=key)
            return client

        fake_supabase_module = SimpleNamespace(create_client=create_client)
        settings = PersistenceSettings(
            mode="postgres-supabase",
            local_data_directory=None,
            database_url=(
                "postgresql://collector_querido_diario:database-password@"
                "db.example/postgres?sslmode=require"
            ),
            supabase_url="https://project.supabase.co",
            supabase_publishable_key=("sb_publishable_000000000000000000000000"),
            supabase_workload_email="collector@example.org",
            supabase_workload_password=workload_password,
            raw_artifacts_bucket="raw-artifacts",
        )

        with (
            patch.dict(sys.modules, {"supabase": fake_supabase_module}),
            patch(
                "barreiras_collectors.commands.collect_querido_diario."
                "PostgresCollectionRepository.from_dsn",
                return_value=object(),
            ) as repository,
        ):
            _build_persistence_service(settings)

        self.assertEqual(
            client_creation,
            {
                "url": "https://project.supabase.co",
                "key": "sb_publishable_000000000000000000000000",
            },
        )
        self.assertEqual(
            client.auth.credentials,
            {
                "email": "collector@example.org",
                "password": workload_password,
            },
        )
        self.assertEqual(client.storage.bucket, "raw-artifacts")
        repository.assert_called_once_with(settings.database_url)


if __name__ == "__main__":
    unittest.main()
