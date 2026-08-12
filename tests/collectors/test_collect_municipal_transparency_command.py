from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

from barreiras_collectors.commands.collect_municipal_transparency import (
    DEFAULT_RESOURCE,
    FINANCIAL_DOCUMENT_RESOURCES,
    SOURCE_CONFIG,
    MunicipalTransparencyCollectionSummary,
    _bounded_env_int,
    build_balancete_monthly_searches,
    execute_controlled_municipal_transparency,
    resolve_endpoint_code,
    resolve_execution_namespace,
    resolve_municipal_document_role,
    resolve_resume_offset,
    select_pending_document_indexes,
)


class MunicipalTransparencyCommandTests(unittest.TestCase):
    def test_builds_monthly_searches_without_turning_absence_into_zero(
        self,
    ) -> None:
        searches = build_balancete_monthly_searches(
            (
                {"ano_ref": "2022", "mes_ref": "2", "titulo": "Fevereiro"},
                {"ano_ref": "2022", "mes_ref": "4", "titulo": "Abril"},
                {"ano_ref": "2022", "mes_ref": "4", "titulo": "Balanço anual"},
            ),
            period_start=date(2022, 1, 1),
            period_end=date(2022, 4, 30),
        )

        self.assertEqual(
            [
                (row.reference_month, row.search_status, row.match_count)
                for row in searches
            ],
            [
                (1, "not_found", 0),
                (2, "found", 1),
                (3, "not_found", 0),
                (4, "found", 2),
            ],
        )

    def test_refuses_to_claim_absence_when_catalog_month_is_malformed(self) -> None:
        with self.assertRaisesRegex(ValueError, "ano_ref e mes_ref"):
            build_balancete_monthly_searches(
                ({"ano_ref": "2022", "titulo": "Sem mês"},),
                period_start=date(2022, 1, 1),
                period_end=date(2022, 4, 30),
            )

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

    def test_financial_sources_include_obligation_evidence(self) -> None:
        self.assertIn("balancetes", FINANCIAL_DOCUMENT_RESOURCES)
        self.assertIn("pdc-contas-anuais", FINANCIAL_DOCUMENT_RESOURCES)
        self.assertIn("rgf", FINANCIAL_DOCUMENT_RESOURCES)

    def test_catalog_and_document_drain_use_distinct_execution_namespaces(
        self,
    ) -> None:
        catalog = resolve_execution_namespace("balancetes", download_documents=False)
        documents = resolve_execution_namespace("balancetes", download_documents=True)

        self.assertNotEqual(catalog, documents)
        self.assertRegex(catalog, r"^municipal-[0-9a-f]{12}-catalog$")
        self.assertRegex(documents, r"^municipal-[0-9a-f]{12}-documents$")

    def test_only_validated_pdf_format_is_downloaded(self) -> None:
        self.assertEqual(
            resolve_municipal_document_role(
                "https://barreiras.mtransparente.com.br/contas.PDF?download=1"
            ),
            "pdf",
        )
        self.assertIsNone(
            resolve_municipal_document_role(
                "https://barreiras.mtransparente.com.br/contas.docx"
            )
        )

    def test_document_drain_selects_only_missing_or_changed_sources(self) -> None:
        candidates = (
            (0, "record-a", "https://example.org/a.pdf"),
            (1, "record-b", "https://example.org/b-new.pdf"),
            (2, "record-c", "https://example.org/c.pdf"),
        )
        preserved = frozenset(
            {
                ("record-a", "https://example.org/a.pdf"),
                ("record-b", "https://example.org/b-old.pdf"),
            }
        )

        selection = select_pending_document_indexes(
            candidates,
            preserved=preserved,
            max_documents=1,
        )

        self.assertEqual(selection.indexes, (1,))
        self.assertEqual(selection.already_preserved, 1)
        self.assertEqual(selection.deferred, 1)

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
                documents_skipped=0,
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
                documents_skipped=0,
                pagination_capped=True,
                availability_partial=False,
                next_offset=150,
            ),
        )

        self.assertEqual(completed["outcome"].value, "partial")
        self.assertEqual(completed["observed_records"], 150)
        self.assertEqual(completed["checkpoint"], {"next_offset": 150})

    def test_unsupported_document_keeps_collection_partial(self) -> None:
        summary = MunicipalTransparencyCollectionSummary(
            pages=1,
            inserted_records=1,
            existing_records=0,
            documents_persisted=0,
            documents_failed=0,
            documents_skipped=1,
            pagination_capped=False,
            availability_partial=False,
            next_offset=0,
        )

        self.assertEqual(summary.outcome.value, "partial")


if __name__ == "__main__":
    unittest.main()
