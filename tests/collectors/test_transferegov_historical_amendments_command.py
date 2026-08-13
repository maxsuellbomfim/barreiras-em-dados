from __future__ import annotations

import unittest

from barreiras_collectors.collection_control import CollectionOutcome
from barreiras_collectors.commands.collect_transferegov_historical_amendments import (
    HistoricalAmendmentCollectionSummary,
    build_historical_amendments_execution_key,
    execute_controlled_historical_amendments,
)
from barreiras_collectors.persistence.postgres import PostgresCollectionRepository


class FakeControl:
    def __init__(self) -> None:
        self.entered = False
        self.completed = None

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        del exc_type, exc_value, traceback
        return False

    def complete(self, **values):
        self.completed = values


class HistoricalAmendmentCommandTests(unittest.TestCase):
    def test_repository_reads_only_numeric_barreiras_proposals_in_period(self) -> None:
        class Result:
            @staticmethod
            def fetchall():
                return [{"id_proposta": "9001"}, {"id_proposta": "9002"}]

        class Connection:
            def __init__(self) -> None:
                self.query = ""
                self.params = ()
                self.closed = False

            def execute(self, query, params=None):
                self.query = query
                self.params = params
                return Result()

            def close(self):
                self.closed = True

        connection = Connection()
        repository = PostgresCollectionRepository(lambda: connection)  # type: ignore[arg-type]

        result = repository.historical_proposal_ids(
            year_from=2021,
            year_to=2026,
        )

        self.assertEqual(result, frozenset({"9001", "9002"}))
        self.assertIn("transferegov_historical_proposal", connection.query)
        self.assertIn("2903201", connection.query)
        self.assertEqual(connection.params, (2021, 2026))
        self.assertTrue(connection.closed)

    def test_execution_key_is_stable_for_one_actions_attempt(self) -> None:
        environment = {
            "GITHUB_RUN_ID": "31700119397",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_REPOSITORY": "maxsuellbomfim/barreiras-em-dados",
            "GITHUB_WORKFLOW": "Coletar documentos financeiros municipais",
        }
        first = build_historical_amendments_execution_key(environment=environment)
        replay = build_historical_amendments_execution_key(environment=environment)
        self.assertEqual(first, replay)
        self.assertRegex(
            first,
            r"^transferegov-historical-amendments:execution:[0-9a-f]{64}$",
        )

    def test_control_closes_only_after_matched_rows_are_persisted(self) -> None:
        control = FakeControl()

        def operation():
            self.assertTrue(control.entered)
            return HistoricalAmendmentCollectionSummary(
                amendments=9,
                matched_proposals=8,
                proposal_scope=69,
                archive_bytes=8_301_409,
                inserted_records=9,
                existing_records=0,
                archive_sha256="a" * 64,
                catalog_etag="0xETAG",
                year_from=2021,
                year_to=2026,
            )

        summary = execute_controlled_historical_amendments(
            control=control,  # type: ignore[arg-type]
            operation=operation,
        )

        self.assertEqual(summary.amendments, 9)
        self.assertEqual(control.completed["outcome"], CollectionOutcome.COMPLETE)
        self.assertEqual(control.completed["observed_records"], 9)
        self.assertEqual(control.completed["metrics"]["matched_proposals"], 8)
        self.assertEqual(control.completed["metrics"]["proposal_scope"], 69)

    def test_zero_rows_is_valid_empty_only_with_nonempty_dependency_scope(self) -> None:
        control = FakeControl()
        summary = HistoricalAmendmentCollectionSummary(
            amendments=0,
            matched_proposals=0,
            proposal_scope=69,
            archive_bytes=8_301_409,
            inserted_records=0,
            existing_records=0,
            archive_sha256="b" * 64,
            catalog_etag="0xETAG",
            year_from=2021,
            year_to=2026,
        )
        execute_controlled_historical_amendments(
            control=control,  # type: ignore[arg-type]
            operation=lambda: summary,
        )
        self.assertEqual(control.completed["outcome"], CollectionOutcome.EMPTY)

    def test_missing_proposal_dependency_cannot_be_marked_empty(self) -> None:
        control = FakeControl()
        summary = HistoricalAmendmentCollectionSummary(
            amendments=0,
            matched_proposals=0,
            proposal_scope=0,
            archive_bytes=8_301_409,
            inserted_records=0,
            existing_records=0,
            archive_sha256="b" * 64,
            catalog_etag="0xETAG",
            year_from=2021,
            year_to=2026,
        )
        with self.assertRaisesRegex(RuntimeError, "propostas históricas"):
            execute_controlled_historical_amendments(
                control=control,  # type: ignore[arg-type]
                operation=lambda: summary,
            )
        self.assertIsNone(control.completed)


if __name__ == "__main__":
    unittest.main()
