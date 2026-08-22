from __future__ import annotations

import logging
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from barreiras_collectors.commands.collect_municipal_transparency import (
    DEFAULT_RESOURCE,
    DOCUMENT_RESOURCES,
    FINANCIAL_DOCUMENT_RESOURCES,
    NO_MATCHING_OFFICIAL_DOCUMENT_EXIT_CODE,
    PERSONNEL_DOCUMENT_RESOURCES,
    SOURCE_CONFIG,
    MunicipalTransparencyCollectionSummary,
    NoMatchingOfficialDocumentError,
    _bounded_env_int,
    _collect_resource,
    build_balancete_monthly_searches,
    cli_entrypoint,
    execute_controlled_municipal_transparency,
    matches_document_reference,
    require_complete_document_match,
    resolve_endpoint_code,
    resolve_execution_namespace,
    resolve_municipal_document_role,
    resolve_resume_offset,
    select_pending_document_indexes,
    should_defer_document_for_byte_budget,
)


class MunicipalTransparencyCommandTests(unittest.TestCase):
    def test_cli_distinguishes_missing_official_document_from_operational_failure(
        self,
    ) -> None:
        target = "barreiras_collectors.commands.collect_municipal_transparency.main"
        with (
            patch(target, side_effect=NoMatchingOfficialDocumentError("ausente")),
            patch("builtins.print") as print_mock,
        ):
            self.assertEqual(
                cli_entrypoint([]),
                NO_MATCHING_OFFICIAL_DOCUMENT_EXIT_CODE,
            )
        print_mock.assert_called_once()

    def test_exact_document_contract_accepts_preserved_or_new_matches(self) -> None:
        require_complete_document_match(
            MunicipalTransparencyCollectionSummary(
                pages=1,
                inserted_records=0,
                existing_records=200,
                documents_persisted=1,
                documents_failed=0,
                documents_skipped=0,
                pagination_capped=False,
                availability_partial=False,
                next_offset=0,
                documents_matched=2,
                documents_already_preserved=1,
            )
        )

    def test_exact_document_contract_rejects_absence_and_partial_coverage(
        self,
    ) -> None:
        empty = MunicipalTransparencyCollectionSummary(
            pages=1,
            inserted_records=0,
            existing_records=200,
            documents_persisted=0,
            documents_failed=0,
            documents_skipped=0,
            pagination_capped=False,
            availability_partial=False,
            next_offset=0,
        )
        partial = MunicipalTransparencyCollectionSummary(
            pages=1,
            inserted_records=0,
            existing_records=200,
            documents_persisted=0,
            documents_failed=0,
            documents_skipped=1,
            pagination_capped=False,
            availability_partial=False,
            next_offset=0,
            documents_matched=1,
        )

        with self.assertRaisesRegex(RuntimeError, "Nenhum documento oficial"):
            require_complete_document_match(empty)
        with self.assertRaisesRegex(RuntimeError, "cobertura parcial"):
            require_complete_document_match(partial)

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
        self.assertIn(
            "pdc-convenios-transferencias-realizadas",
            FINANCIAL_DOCUMENT_RESOURCES,
        )
        self.assertIn("pdc-obras-pdc", FINANCIAL_DOCUMENT_RESOURCES)
        self.assertIn("contratos", FINANCIAL_DOCUMENT_RESOURCES)

    def test_personnel_documents_are_private_collection_inputs(self) -> None:
        self.assertEqual(PERSONNEL_DOCUMENT_RESOURCES, frozenset({"servidores"}))
        self.assertIn("servidores", DOCUMENT_RESOURCES)
        self.assertTrue(FINANCIAL_DOCUMENT_RESOURCES < DOCUMENT_RESOURCES)

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

    def test_personnel_document_filter_uses_official_month_and_type(self) -> None:
        regular = {
            "ano_ref": "2025",
            "mes_ref": "12",
            "tipo": "1",
            "titulo": "\u00a0RELAC\u0327A\u0303O\u00a0DE\u00a0SERVIDORES\u00a0",
        }
        historical_untyped = {
            "ano_ref": "2025",
            "mes_ref": "2",
            "tipo": "",
            "titulo": "RELAÇÃO   DE SERVIDORES",
        }
        allowed_untyped_titles = frozenset({"Relação de Servidores"})
        allowed_titles = frozenset(
            {
                "Relação de Servidores",
                "Relação Servidores",
                "Relação de Servidores 13º Salário",
            }
        )

        self.assertTrue(
            matches_document_reference(
                regular,
                reference_month=date(2025, 12, 1),
                allowed_types=frozenset({"1"}),
                allowed_titles=allowed_titles,
                allowed_untyped_titles=allowed_untyped_titles,
            )
        )
        self.assertTrue(
            matches_document_reference(
                historical_untyped,
                reference_month=date(2025, 2, 1),
                allowed_types=frozenset({"1"}),
                allowed_titles=allowed_titles,
                allowed_untyped_titles=allowed_untyped_titles,
            )
        )
        self.assertFalse(
            matches_document_reference(
                {**regular, "tipo": "4"},
                reference_month=date(2025, 12, 1),
                allowed_types=frozenset({"1"}),
                allowed_titles=allowed_titles,
                allowed_untyped_titles=allowed_untyped_titles,
            )
        )
        self.assertFalse(
            matches_document_reference(
                {
                    **historical_untyped,
                    "titulo": "Relação de Funcionários Terceirizados - atualizado",
                },
                reference_month=date(2025, 2, 1),
                allowed_types=frozenset({"1"}),
                allowed_titles=allowed_titles,
                allowed_untyped_titles=allowed_untyped_titles,
            )
        )
        self.assertFalse(
            matches_document_reference(
                {
                    **historical_untyped,
                    "titulo": "Relação de Estagiários - atualizado",
                },
                reference_month=date(2025, 2, 1),
                allowed_types=frozenset({"1"}),
                allowed_titles=allowed_titles,
                allowed_untyped_titles=allowed_untyped_titles,
            )
        )
        self.assertFalse(
            matches_document_reference(
                {**regular, "titulo": "Relação de Estagiários"},
                reference_month=date(2025, 12, 1),
                allowed_types=frozenset({"1"}),
                allowed_titles=allowed_titles,
                allowed_untyped_titles=allowed_untyped_titles,
            )
        )
        self.assertFalse(
            matches_document_reference(
                {**regular, "titulo": "Relação de Funcionários Terceirizados"},
                reference_month=date(2025, 12, 1),
                allowed_types=frozenset({"1"}),
                allowed_titles=allowed_titles,
                allowed_untyped_titles=allowed_untyped_titles,
            )
        )
        self.assertTrue(
            matches_document_reference(
                {**regular, "titulo": "Relação de Servidores 13º Salário"},
                reference_month=date(2025, 12, 1),
                allowed_types=frozenset({"1"}),
                allowed_titles=allowed_titles,
                allowed_untyped_titles=allowed_untyped_titles,
            )
        )
        self.assertFalse(
            matches_document_reference(
                {**regular, "mes_ref": "11"},
                reference_month=date(2025, 12, 1),
                allowed_types=frozenset({"1"}),
                allowed_titles=allowed_titles,
                allowed_untyped_titles=allowed_untyped_titles,
            )
        )
        self.assertFalse(
            matches_document_reference(
                {"ano_ref": "inválido", "mes_ref": "12", "tipo": "1"},
                reference_month=date(2025, 12, 1),
                allowed_types=frozenset({"1"}),
                allowed_titles=allowed_titles,
                allowed_untyped_titles=allowed_untyped_titles,
            )
        )

    def test_bounded_env_int_rejects_values_outside_safe_window(self) -> None:
        with patch.dict("os.environ", {"TEST_MUNICIPAL_LIMIT": "61"}, clear=False):
            with self.assertRaises(RuntimeError):
                _bounded_env_int(
                    "TEST_MUNICIPAL_LIMIT",
                    default=10,
                    minimum=1,
                    maximum=60,
                )

    def test_batch_byte_budget_allows_first_document_to_avoid_starvation(self) -> None:
        self.assertFalse(
            should_defer_document_for_byte_budget(
                persisted_documents=0,
                persisted_bytes=0,
                next_document_bytes=80 * 1024 * 1024,
                max_batch_bytes=64 * 1024 * 1024,
            )
        )

    def test_batch_byte_budget_defers_following_document(self) -> None:
        self.assertTrue(
            should_defer_document_for_byte_budget(
                persisted_documents=1,
                persisted_bytes=50 * 1024 * 1024,
                next_document_bytes=20 * 1024 * 1024,
                max_batch_bytes=64 * 1024 * 1024,
            )
        )

    def test_document_drain_stops_before_persisting_over_budget(self) -> None:
        page = SimpleNamespace(
            items=(
                {"url": "https://barreiras.mtransparente.com.br/a.pdf"},
                {"url": "https://barreiras.mtransparente.com.br/b.pdf"},
                {"url": "https://barreiras.mtransparente.com.br/c.pdf"},
            ),
            resource="servidores",
            cursor={"offset": 0},
            body_sha256="a" * 64,
        )

        class ServiceProbe:
            def __init__(self) -> None:
                self.persisted_documents: list[str] = []

            def persist(self, _page):
                return SimpleNamespace(
                    inserted_records=3,
                    existing_records=0,
                )

            def record_input(self, _page, *, index, item):
                del item
                return SimpleNamespace(source_record_key=f"record-{index}")

            def preserved_document_identities(self, _source_keys):
                return frozenset()

            def persist_document(self, *, document, **_values):
                self.persisted_documents.append(document.source_url)

        sizes = iter((40, 30, 10))

        class DocumentClientProbe:
            def fetch(self, url, *, role):
                del role
                return SimpleNamespace(
                    source_url=url,
                    body_size_bytes=next(sizes) * 1024 * 1024,
                )

        service = ServiceProbe()
        environment = {
            "MUNICIPAL_TRANSPARENCY_MAX_BATCH_DOCUMENT_BYTES": str(64 * 1024 * 1024)
        }
        module = "barreiras_collectors.commands.collect_municipal_transparency"
        with (
            patch(f"{module}.iter_resource_pages", return_value=iter((page,))),
            patch(
                f"{module}.MunicipalTransparencyDocumentClient",
                return_value=DocumentClientProbe(),
            ),
            patch.dict("os.environ", environment, clear=False),
        ):
            summary = _collect_resource(
                service=service,  # type: ignore[arg-type]
                source_code="prefeitura-barreiras-transparencia",
                endpoint_code="dados-abertos-api",
                base_url="https://portaldatransparencia.barreiras.ba.gov.br/api",
                resource="servidores",
                limit=500,
                offset=0,
                max_pages=1,
                allow_partial=True,
                download_documents=True,
                max_documents=5,
                collector_settings=SimpleNamespace(read_timeout_seconds=30),
                logger=logging.getLogger(__name__),
            )

        self.assertEqual(service.persisted_documents, [page.items[0]["url"]])
        self.assertEqual(summary.documents_persisted, 1)
        self.assertEqual(summary.documents_bytes_persisted, 40 * 1024 * 1024)
        self.assertEqual(summary.documents_skipped, 2)
        self.assertTrue(summary.documents_byte_budget_exhausted)
        self.assertEqual(summary.outcome.value, "partial")

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

    def test_missing_required_document_is_terminal_blocked_not_failed(self) -> None:
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
        summary = MunicipalTransparencyCollectionSummary(
            pages=1,
            inserted_records=3,
            existing_records=0,
            documents_persisted=0,
            documents_failed=0,
            documents_skipped=0,
            pagination_capped=False,
            availability_partial=False,
            next_offset=0,
            documents_matched=0,
        )

        with self.assertRaises(NoMatchingOfficialDocumentError):
            execute_controlled_municipal_transparency(
                control=control,  # type: ignore[arg-type]
                operation=lambda: summary,
                require_document_match=True,
            )

        self.assertEqual(events, ["started", "completed:blocked", "closed"])
        self.assertEqual(control.values["observed_records"], 3)
        self.assertEqual(
            control.values["block_reason"],
            "Documento oficial exato não localizado no catálogo da fonte.",
        )

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

    def test_exhausted_byte_budget_is_visible_in_control_metrics(self) -> None:
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
                pages=1,
                inserted_records=200,
                existing_records=0,
                documents_persisted=2,
                documents_failed=0,
                documents_skipped=3,
                pagination_capped=False,
                availability_partial=False,
                next_offset=0,
                documents_bytes_persisted=63 * 1024 * 1024,
                documents_byte_budget_exhausted=True,
            ),
        )

        self.assertEqual(completed["outcome"].value, "partial")
        self.assertEqual(
            completed["metrics"]["documents_bytes_persisted"],
            63 * 1024 * 1024,
        )
        self.assertTrue(completed["metrics"]["documents_byte_budget_exhausted"])


if __name__ == "__main__":
    unittest.main()
