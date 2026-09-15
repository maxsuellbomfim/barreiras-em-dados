from __future__ import annotations

import io
import json
import logging
import sys
import traceback
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, call, patch

import httpx
from barreiras_normalization.bahia_special_transfer_processing import (
    SpecialTransferArtifact,
    SpecialTransferArtifactMismatchError,
    SpecialTransferPersistResult,
)
from barreiras_normalization.commands import process_bahia_special_transfers as command


def artifact(suffix: int) -> SpecialTransferArtifact:
    sha256 = str(suffix).zfill(64)
    return SpecialTransferArtifact(
        raw_artifact_id=f"00000000-0000-0000-0000-{suffix:012d}",
        sha256=sha256,
        object_key=(
            f"bahia/transferencias-especiais/archive/sha256/{sha256[:2]}/{sha256}.zip"
        ),
        source_url="https://dados.ba.gov.br/dataset/transferencias-especiais",
        collected_at="2026-08-21T04:32:47+00:00",
    )


class FakeRepository:
    def __init__(self, artifacts) -> None:
        self.artifacts = tuple(artifacts)
        self.failures = []

    def pending_artifacts(self, limit: int):
        return self.artifacts[:limit]

    def persist_failure(self, target, **kwargs) -> None:
        self.failures.append((target, kwargs))


class FakeService:
    def process(self, target):
        if target.raw_artifact_id.endswith("000000000001"):
            raise SpecialTransferArtifactMismatchError("arquivo privado.zip")
        return SpecialTransferPersistResult(True, 3)


class ProcessBahiaSpecialTransfersCommandTests(unittest.TestCase):
    def test_invalid_snapshot_is_audited_without_losing_valid_snapshot(self) -> None:
        try:
            from barreiras_normalization.commands import (
                process_bahia_special_transfers,
            )
        except ImportError:
            self.fail("o comando de normalização ainda não existe")
        run_batch = process_bahia_special_transfers.run_batch
        repository = FakeRepository([artifact(1), artifact(2)])

        summary = run_batch(
            repository=repository,  # type: ignore[arg-type]
            service=FakeService(),  # type: ignore[arg-type]
            limit=5,
        )

        self.assertEqual(summary.pending_found, 2)
        self.assertEqual(summary.processed, 1)
        self.assertEqual(summary.failed, 1)
        self.assertEqual(summary.results_inserted, 3)
        self.assertEqual(len(repository.failures), 1)
        self.assertEqual(repository.failures[0][1]["error_code"], "artifact_mismatch")
        self.assertNotIn("privado.zip", repository.failures[0][1]["error_detail"])


class SpecialTransferStorageAuthenticationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = MagicMock()
        self.authenticated = SimpleNamespace(session=object(), user=object())
        self.client.auth.sign_in_with_password.return_value = self.authenticated
        self.settings = SimpleNamespace(
            mode="postgres-supabase",
            database_url="private-dsn",
            supabase_url="https://test.invalid",
            supabase_publishable_key="private-api-key",
            supabase_workload_email="worker-private@example.invalid",
            supabase_workload_password="private-password",  # noqa: S106 - test sentinel
            raw_artifacts_bucket="raw-artifacts",
        )

        def activate(patcher):
            mocked = patcher.start()
            self.addCleanup(patcher.stop)
            return mocked

        activate(
            patch.dict(
                sys.modules,
                {
                    "supabase": SimpleNamespace(
                        create_client=Mock(return_value=self.client)
                    )
                },
            )
        )
        activate(
            patch.object(
                command.CollectorSettings,
                "from_env",
                return_value=SimpleNamespace(log_level="INFO"),
            )
        )
        activate(
            patch.object(
                command.PersistenceSettings, "from_env", return_value=self.settings
            )
        )
        activate(patch.object(command.logging, "basicConfig"))
        self.repository = activate(
            patch.object(command.BahiaSpecialTransferRepository, "from_dsn")
        )
        self.service = activate(
            patch.object(command, "SpecialTransferExtractionService")
        )
        self.store = activate(patch.object(command, "SupabaseStorageObjectStore"))
        self.batch = activate(
            patch.object(
                command,
                "run_batch",
                return_value=command.SpecialTransferBatchSummary(1, 1, 0, 1, 3),
            )
        )
        self.sleep = activate(patch("time.sleep"))
        activate(patch("random.random", return_value=1))
        self.output = io.StringIO()
        logger = logging.getLogger(command.__name__)
        handler = logging.StreamHandler(self.output)
        handler.setFormatter(logging.Formatter("%(message)s"))
        previous_level = logger.level
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        self.addCleanup(logger.setLevel, previous_level)
        self.addCleanup(logger.removeHandler, handler)

    def assert_nothing_processed(self) -> None:
        self.repository.assert_not_called()
        self.service.assert_not_called()
        self.store.assert_not_called()
        self.client.storage.from_.assert_not_called()
        self.batch.assert_not_called()

    def assert_sanitized(self, error: Exception | None = None) -> None:
        rendered = self.output.getvalue()
        if error is not None:
            rendered += "".join(traceback.format_exception(error))
            self.assertIsNone(error.__cause__)
            self.assertTrue(error.__suppress_context__)
        for marker in (
            "private-password",
            "worker-private@example.invalid",
            "private-api-key",
            "private-dsn",
            "sensitive-exception",
            "https://auth.invalid/private-token",
        ):
            self.assertNotIn(marker, rendered)

    def test_timeout_then_success_runs_one_batch(self) -> None:
        self.client.auth.sign_in_with_password.side_effect = [
            httpx.ReadTimeout("sensitive-exception"),
            self.authenticated,
        ]
        self.assertEqual(command.main(["--limit", "1"]), 0)
        self.assertEqual(self.client.auth.sign_in_with_password.call_count, 2)
        self.sleep.assert_called_once_with(0.5)
        self.repository.assert_called_once_with("private-dsn")
        self.client.storage.from_.assert_called_once_with("raw-artifacts")
        self.batch.assert_called_once_with(
            repository=self.repository.return_value,
            service=self.service.return_value,
            limit=1,
        )
        self.assert_sanitized()

    def test_network_error_then_success_uses_the_same_credentials(self) -> None:
        self.client.auth.sign_in_with_password.side_effect = [
            httpx.ConnectError("sensitive-exception"),
            self.authenticated,
        ]
        self.assertEqual(command.main([]), 0)
        self.assertEqual(
            self.client.auth.sign_in_with_password.call_args_list,
            [
                call(
                    {
                        "email": self.settings.supabase_workload_email,
                        "password": self.settings.supabase_workload_password,
                    }
                ),
            ]
            * 2,
        )
        self.batch.assert_called_once()
        self.assert_sanitized()

    def test_exhausted_timeouts_never_open_data_and_hide_the_error_chain(self) -> None:
        self.client.auth.sign_in_with_password.side_effect = httpx.ReadTimeout(
            "sensitive-exception https://auth.invalid/private-token"
        )
        with self.assertRaises(RuntimeError) as raised:
            command.main([])
        self.assertEqual(self.client.auth.sign_in_with_password.call_count, 3)
        self.assertEqual(self.sleep.call_args_list, [call(0.5), call(1.0)])
        self.assert_nothing_processed()
        events = [json.loads(line) for line in self.output.getvalue().splitlines()]
        self.assertEqual([event["attempt"] for event in events], [1, 2, 3])
        self.assertEqual([event["will_retry"] for event in events], [True, True, False])
        self.assert_sanitized(raised.exception)

    def test_permanent_authentication_error_is_not_retried(self) -> None:
        self.client.auth.sign_in_with_password.side_effect = RuntimeError(
            "sensitive-exception worker-private@example.invalid private-password"
        )
        with self.assertRaises(RuntimeError) as raised:
            command.main([])
        self.client.auth.sign_in_with_password.assert_called_once()
        self.sleep.assert_not_called()
        self.assert_nothing_processed()
        self.assert_sanitized(raised.exception)

    def test_missing_session_or_user_fails_without_processing_or_retry(self) -> None:
        for response in (
            SimpleNamespace(session=None, user=object()),
            SimpleNamespace(session=object(), user=None),
            None,
        ):
            with self.subTest(response=response):
                self.client.auth.sign_in_with_password.reset_mock()
                self.client.auth.sign_in_with_password.return_value = response
                with self.assertRaises(RuntimeError):
                    command.main([])
                self.client.auth.sign_in_with_password.assert_called_once()
                self.sleep.assert_not_called()
                self.assert_nothing_processed()

    def test_processing_failure_is_not_mislabeled_or_retried_as_authentication(
        self,
    ) -> None:
        self.batch.return_value = command.SpecialTransferBatchSummary(1, 0, 1, 0, 0)
        self.assertEqual(command.main([]), 1)
        self.client.auth.sign_in_with_password.assert_called_once()
        self.batch.assert_called_once()
        self.sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
