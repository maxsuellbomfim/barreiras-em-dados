from __future__ import annotations

import unittest
from unittest.mock import patch

from barreiras_collectors.commands.collect_municipal_transparency import (
    DEFAULT_RESOURCE,
    SOURCE_CONFIG,
    MunicipalTransparencyCollectionSummary,
    _bounded_env_int,
    execute_controlled_municipal_transparency,
    resolve_endpoint_code,
    resolve_resume_offset,
)


class MunicipalTransparencyCommandTests(unittest.TestCase):
    def test_resolves_specific_legislative_endpoints(self) -> None:
        self.assertEqual(resolve_endpoint_code("camara", "leis"), "leis-api")
        self.assertEqual(
            resolve_endpoint_code("camara", "indicacoes"),
            "indicacoes-api",
        )
        self.assertEqual(
            resolve_endpoint_code("camara", "requerimentos"),
            "dados-abertos-api",
        )
        self.assertEqual(
            resolve_endpoint_code("prefeitura", "leis"),
            "dados-abertos-api",
        )

    def test_partial_checkpoint_resumes_from_next_offset(self) -> None:
        self.assertEqual(
            resolve_resume_offset(
                explicit_offset=None,
                checkpoint={"next_offset": 150},
            ),
            150,
        )

    def test_explicit_offset_overrides_checkpoint(self) -> None:
        self.assertEqual(
            resolve_resume_offset(
                explicit_offset=25,
                checkpoint={"next_offset": 150},
            ),
            25,
        )

    def test_malformed_checkpoint_restarts_safely(self) -> None:
        self.assertEqual(
            resolve_resume_offset(
                explicit_offset=None,
                checkpoint={"next_offset": "150"},
            ),
            0,
        )

    def test_sources_are_official_and_have_distinct_codes(self) -> None:
        self.assertEqual(
            set(SOURCE_CONFIG),
            {"prefeitura", "camara"},
        )
        self.assertNotEqual(SOURCE_CONFIG["prefeitura"][0], SOURCE_CONFIG["camara"][0])
        self.assertEqual(DEFAULT_RESOURCE, "pdc-resumo-execucao-da-receita")

    def test_bounded_env_int_rejects_values_outside_safe_window(self) -> None:
        with patch.dict("os.environ", {"TEST_MUNICIPAL_LIMIT": "61"}, clear=False):
            with self.assertRaises(RuntimeError):
                _bounded_env_int(
                    "TEST_MUNICIPAL_LIMIT",
                    default=10,
                    minimum=1,
                    maximum=60,
                )

    def test_control_records_empty_snapshot_explicitly(self) -> None:
        events: list[str] = []

        class ControlProbe:
            def __enter__(self):
                events.append("started")
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                del exc_type, exc_value, traceback
                events.append("closed")
                return False

            def complete(self, **values):
                events.append(f"completed:{values['outcome'].value}")
                self.values = values

        control = ControlProbe()

        def operation() -> MunicipalTransparencyCollectionSummary:
            self.assertEqual(events, ["started"])
            return MunicipalTransparencyCollectionSummary(
                pages=1,
                inserted_records=0,
                existing_records=0,
                documents_persisted=0,
                documents_failed=0,
                pagination_capped=False,
                availability_partial=False,
                next_offset=0,
            )

        execute_controlled_municipal_transparency(
            control=control,  # type: ignore[arg-type]
            operation=operation,
        )

        self.assertEqual(events, ["started", "completed:empty", "closed"])
        self.assertEqual(control.values["observed_records"], 0)

    def test_page_cap_and_document_failure_mark_snapshot_partial(self) -> None:
        completed: dict[str, object] = {}

        class ControlProbe:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                del exc_type, exc_value, traceback
                return False

            def complete(self, **values):
                completed.update(values)

        execute_controlled_municipal_transparency(
            control=ControlProbe(),  # type: ignore[arg-type]
            operation=lambda: MunicipalTransparencyCollectionSummary(
                pages=3,
                inserted_records=120,
                existing_records=30,
                documents_persisted=4,
                documents_failed=1,
                pagination_capped=True,
                availability_partial=False,
                next_offset=150,
            ),
        )

        self.assertEqual(completed["outcome"].value, "partial")
        self.assertEqual(completed["observed_records"], 150)
        self.assertEqual(completed["checkpoint"], {"next_offset": 150})


if __name__ == "__main__":
    unittest.main()
