from __future__ import annotations

import unittest

from barreiras_collectors.collection_control import CollectionOutcome
from barreiras_collectors.commands import collect_official_diary_catalog as command


class ControlProbe:
    def __init__(self) -> None:
        self.entered = False
        self.completed = None
        self.failure = None

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        del traceback
        if exc_value is not None:
            self.failure = (exc_type, exc_value)
        return False

    def complete(self, **values):
        self.completed = values


class OfficialDiaryCatalogCommandTests(unittest.TestCase):
    def test_control_starts_before_collection_and_classifies_daily_snapshot(
        self,
    ) -> None:
        execute = getattr(command, "execute_controlled_catalog", None)
        summary_type = getattr(command, "OfficialDiaryCatalogSummary", None)
        self.assertTrue(
            callable(execute) and summary_type is not None,
            "o catálogo oficial ainda não registra cobertura controlada",
        )
        control = ControlProbe()

        def operation():
            self.assertTrue(control.entered)
            return summary_type(
                publications=27,
                inserted_records=10,
                existing_records=17,
                artifact_sha256="a" * 64,
            )

        summary = execute(
            control=control,  # type: ignore[arg-type]
            operation=operation,
        )

        self.assertEqual(summary.publications, 27)
        self.assertEqual(control.completed["outcome"], CollectionOutcome.COMPLETE)
        self.assertEqual(control.completed["observed_records"], 27)
        self.assertEqual(
            control.completed["checkpoint"],
            {"artifact_sha256": "a" * 64},
        )
        self.assertEqual(
            control.completed["metrics"],
            {
                "publications": 27,
                "inserted_records": 10,
                "existing_records": 17,
                "pages": 1,
            },
        )

    def test_external_setup_failure_remains_visible_to_control(self) -> None:
        execute = getattr(command, "execute_controlled_catalog", None)
        self.assertTrue(
            callable(execute),
            "o catálogo oficial ainda não registra falhas antes do HTTP",
        )
        control = ControlProbe()

        def failing_operation():
            self.assertTrue(control.entered)
            raise RuntimeError("falha de autenticação")

        with self.assertRaisesRegex(RuntimeError, "autenticação"):
            execute(
                control=control,  # type: ignore[arg-type]
                operation=failing_operation,
            )

        self.assertIs(control.failure[0], RuntimeError)
        self.assertRegex(str(control.failure[1]), "autenticação")
        self.assertIsNone(control.completed)

    def test_explicit_empty_window_is_not_reported_as_complete(self) -> None:
        control = ControlProbe()

        summary = command.execute_controlled_catalog(
            control=control,  # type: ignore[arg-type]
            operation=lambda: command.OfficialDiaryCatalogSummary(
                publications=0,
                inserted_records=0,
                existing_records=0,
                artifact_sha256="a" * 64,
            ),
        )

        self.assertEqual(summary.publications, 0)
        self.assertEqual(control.completed["outcome"], CollectionOutcome.EMPTY)
        self.assertEqual(control.completed["observed_records"], 0)

if __name__ == "__main__":
    unittest.main()
