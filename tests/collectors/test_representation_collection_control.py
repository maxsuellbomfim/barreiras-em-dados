from __future__ import annotations

import unittest
from datetime import date
from importlib import import_module

from barreiras_collectors.collection_control import CollectionOutcome
from barreiras_collectors.commands.representation_control import (
    RepresentationCollectionSummary,
    build_representation_control,
    execute_controlled_representation,
)


class ControlProbe:
    def __init__(self) -> None:
        self.entered = False
        self.completed: dict[str, object] = {}

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        del exc_type, exc_value, traceback
        return False

    def complete(self, **values: object) -> None:
        self.completed.update(values)


class RepositoryProbe:
    def __init__(self) -> None:
        self.started: list[dict[str, object]] = []

    def start_controlled_run(self, **values: object) -> str:
        self.started.append(values)
        return "run-1"

    def complete_controlled_run(self, **values: object) -> None:
        del values

    def fail_controlled_run(self, **values: object) -> None:
        del values


class RepresentationCollectionControlTests(unittest.TestCase):
    def test_representation_commands_load_with_control_contract(self) -> None:
        modules = (
            "collect_camara_deputies",
            "collect_vereadores",
            "collect_alba_deputies",
            "collect_municipal_executive",
            "collect_tse_votes",
        )

        for module_name in modules:
            module = import_module(
                f"barreiras_collectors.commands.{module_name}"
            )
            self.assertTrue(callable(module.main))
            self.assertTrue(callable(module.execute_controlled_representation))

    def test_completes_snapshot_with_explicit_partial_coverage(self) -> None:
        control = ControlProbe()

        summary = execute_controlled_representation(
            control=control,  # type: ignore[arg-type]
            operation=lambda: RepresentationCollectionSummary(
                observed_records=63,
                outcome=CollectionOutcome.PARTIAL,
                metrics={"profiles_succeeded": 60, "profiles_failed": 3},
                checkpoint={"remaining_profiles": 3},
            ),
        )

        self.assertTrue(control.entered)
        self.assertEqual(summary.observed_records, 63)
        self.assertEqual(control.completed["outcome"], CollectionOutcome.PARTIAL)
        self.assertEqual(control.completed["observed_records"], 63)
        self.assertEqual(control.completed["checkpoint"], {"remaining_profiles": 3})

    def test_blocked_snapshot_requires_reason(self) -> None:
        with self.assertRaisesRegex(ValueError, "block_reason"):
            RepresentationCollectionSummary(
                observed_records=0,
                outcome=CollectionOutcome.BLOCKED,
            )

    def test_builds_daily_control_for_exact_source_endpoint(self) -> None:
        repository = RepositoryProbe()
        control = build_representation_control(
            repository=repository,  # type: ignore[arg-type]
            source_code="tse",
            endpoint_code="votacao-munzona",
            namespace="tse-votes-2024",
            collector_version="tse-collector/0.1.0",
            parser_version="tse-votacao-munzona/1.0.0",
            partition_key="election:2024:barreiras",
            snapshot_date=date(2026, 8, 5),
        )

        with control:
            control.complete(
                outcome=CollectionOutcome.COMPLETE,
                observed_records=289,
            )

        self.assertEqual(repository.started[0]["source_code"], "tse")
        self.assertEqual(
            repository.started[0]["endpoint_code"],
            "votacao-munzona",
        )
        self.assertEqual(repository.started[0]["period_start"], date(2026, 8, 5))


if __name__ == "__main__":
    unittest.main()
