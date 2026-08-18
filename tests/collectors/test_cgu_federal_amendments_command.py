from __future__ import annotations

import unittest

from barreiras_collectors.collection_control import CollectionOutcome
from barreiras_collectors.commands.collect_cgu_federal_amendments import (
    CGUFederalAmendmentCollectionSummary,
    build_cgu_execution_key,
    execute_controlled_cgu_collection,
)


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


class CGUFederalAmendmentCommandTests(unittest.TestCase):
    def test_execution_key_is_stable_for_one_actions_attempt(self) -> None:
        environment = {
            "GITHUB_RUN_ID": "31700119397",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_REPOSITORY": "maxsuellbomfim/barreiras-em-dados",
            "GITHUB_WORKFLOW": "Coletar documentos financeiros municipais",
        }
        first = build_cgu_execution_key(environment=environment)
        replay = build_cgu_execution_key(environment=environment)
        self.assertEqual(first, replay)
        self.assertRegex(first, r"^cgu-federal-amendments:execution:[0-9a-f]{64}$")

    def test_complete_only_after_records_are_persisted(self) -> None:
        control = FakeControl()

        def operation():
            self.assertTrue(control.entered)
            return CGUFederalAmendmentCollectionSummary(
                amendments=15,
                amendment_codes=15,
                authors=5,
                archive_bytes=32_110_890,
                inserted_records=15,
                existing_records=0,
                archive_sha256="a" * 64,
                source_etag='"etag"',
                first_fiscal_year=2014,
                last_fiscal_year=2023,
            )

        summary = execute_controlled_cgu_collection(
            control=control,  # type: ignore[arg-type]
            operation=operation,
        )
        self.assertEqual(summary.amendments, 15)
        self.assertEqual(control.completed["outcome"], CollectionOutcome.COMPLETE)
        self.assertEqual(control.completed["observed_records"], 15)
        self.assertEqual(control.completed["metrics"]["authors"], 5)

    def test_validated_archive_with_no_barreiras_rows_is_empty(self) -> None:
        control = FakeControl()
        summary = CGUFederalAmendmentCollectionSummary(
            amendments=0,
            amendment_codes=0,
            authors=0,
            archive_bytes=32_110_890,
            inserted_records=0,
            existing_records=0,
            archive_sha256="b" * 64,
            source_etag='"etag"',
            first_fiscal_year=0,
            last_fiscal_year=0,
        )
        execute_controlled_cgu_collection(
            control=control,  # type: ignore[arg-type]
            operation=lambda: summary,
        )
        self.assertEqual(control.completed["outcome"], CollectionOutcome.EMPTY)


if __name__ == "__main__":
    unittest.main()
