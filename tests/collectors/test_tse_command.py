import unittest
from unittest.mock import Mock, patch

from barreiras_collectors.collection_control import CollectionOutcome
from barreiras_collectors.commands import collect_tse_votes as command
from barreiras_collectors.commands.representation_control import (
    RepresentationCollectionSummary,
)


class TseCommandTests(unittest.TestCase):
    def run_summary(self, summary):
        settings = Mock(mode="postgres-supabase")
        with (
            patch.object(
                command.CollectorSettings,
                "from_env",
                return_value=Mock(log_level="INFO"),
            ),
            patch.object(
                command.PersistenceSettings, "from_env", return_value=settings
            ),
            patch.object(command.PostgresCollectionRepository, "from_dsn"),
            patch.object(command, "build_representation_control") as build,
            patch.object(
                command, "execute_controlled_representation", return_value=summary
            ),
        ):
            result = command.main([])
            self.assertEqual(
                build.call_args.kwargs["partition_key"], "election:2026:barreiras"
            )
            return result

    def test_unpublished_is_failure_not_success(self):
        self.assertEqual(
            self.run_summary(
                RepresentationCollectionSummary(
                    observed_records=0,
                    outcome=CollectionOutcome.BLOCKED,
                    block_reason="fonte ainda não publicada",
                )
            ),
            1,
        )

    def test_complete_nonempty_snapshot_succeeds(self):
        self.assertEqual(
            self.run_summary(
                RepresentationCollectionSummary(
                    observed_records=12,
                    outcome=CollectionOutcome.COMPLETE,
                )
            ),
            0,
        )
