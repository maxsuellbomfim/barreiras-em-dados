from __future__ import annotations

import json
import logging
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from barreiras_collectors.commands.collect_pncp_contratos import (
    PncpContratosCollectionSummary,
    collect_contratos_batch,
    execute_controlled_pncp_contratos,
)
from barreiras_collectors.commands.collect_pncp_itens import (
    PncpItensCollectionSummary,
    collect_itens_batch,
    collect_itens_pages,
    execute_controlled_pncp_itens,
)
from barreiras_collectors.commands.pncp_runtime import (
    resolve_checkpoint_offset,
)
from barreiras_collectors.connectors.pncp import (
    COMPRAS_PAGE_SIZE,
    PncpError,
    fetch_contratos_page,
    fetch_itens_page,
    fetch_resultados_page,
)
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.persistence.models import (
    PersistenceContractError,
)
from barreiras_collectors.persistence.service import (
    PncpComprasPersistenceService,
)
from barreiras_collectors.resilience import RetryPolicy

CONTROL = "13654405000195-1-000009/2025"


class SequencedTransport:
    """Devolve as respostas na ordem dada; a última se repete."""

    def __init__(self, *responses: tuple[int, bytes]) -> None:
        self.responses = list(responses)
        self.urls: list[str] = []

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds, max_body_bytes
        self.urls.append(url)
        if len(self.responses) > 1:
            status, body = self.responses.pop(0)
        else:
            status, body = self.responses[0]
        return HttpResponse(status=status, headers={}, body=body, final_url=url)


def itens_body(numeros: list[int]) -> bytes:
    return json.dumps(
        [
            {"numeroItem": numero, "temResultado": True, "descricao": "x"}
            for numero in numeros
        ]
    ).encode()


def fetch_itens(status: int, body: bytes):
    return fetch_itens_page(
        ano=2025,
        sequencial=9,
        pagina=1,
        transport=SequencedTransport((status, body)),
        retry_policy=RetryPolicy(max_attempts=2),
        sleep=lambda _s: None,
    )


class ItensFetchTests(unittest.TestCase):
    def test_array_root_becomes_page_with_compras_cursor(self) -> None:
        page = fetch_itens(200, itens_body([1, 2]))

        assert page is not None
        self.assertEqual(len(page.items), 2)
        self.assertEqual(page.endpoint_code, "compras-api")
        self.assertEqual(page.cursor["ano"], 2025)
        self.assertEqual(page.cursor["sequencial"], 9)

    def test_204_404_and_empty_array_mean_no_content(self) -> None:
        self.assertIsNone(fetch_itens(204, b""))
        self.assertIsNone(fetch_itens(404, b""))
        self.assertIsNone(fetch_itens(200, b"[]"))

    def test_non_list_root_is_failure(self) -> None:
        with self.assertRaises(PncpError):
            fetch_itens(200, json.dumps({"error": "x"}).encode())

    def test_resultados_cursor_carries_item(self) -> None:
        body = json.dumps(
            [{"sequencialResultado": 1, "numeroItem": 77}]
        ).encode()
        page = fetch_resultados_page(
            ano=2025,
            sequencial=9,
            numero_item=77,
            transport=SequencedTransport((200, body)),
            retry_policy=RetryPolicy(max_attempts=2),
            sleep=lambda _s: None,
        )

        assert page is not None
        self.assertEqual(page.cursor["item"], 77)
        self.assertIn("/itens/77/resultados", page.request_url)

    def test_contracts_endpoint_uses_contracts_api_and_keeps_parent(self) -> None:
        body = json.dumps(
            [
                {
                    "numeroControlePNCP": "13654405000195-2-000001/2026",
                    "numeroControlePncpCompra": CONTROL,
                    "objetoContrato": "Serviço de manutenção",
                }
            ]
        ).encode()
        page = fetch_contratos_page(
            ano=2025,
            sequencial=9,
            transport=SequencedTransport((200, body)),
            retry_policy=RetryPolicy(max_attempts=2),
            sleep=lambda _s: None,
        )

        assert page is not None
        self.assertEqual(page.endpoint_code, "contratos-api")
        self.assertEqual(page.schema_name, "pncp-contratos-page")
        self.assertIn("/contratos/contratacao/2025/9", page.request_url)
        self.assertIn("pagina=1", page.request_url)

    def test_contracts_endpoint_accepts_paginated_object_root(self) -> None:
        body = json.dumps(
            {
                "data": [
                    {
                        "numeroControlePNCP": "13654405000195-2-000032/2026",
                        "numeroControlePncpCompra": CONTROL,
                    }
                ],
                "totalRegistros": 1,
                "totalPaginas": 1,
            }
        ).encode()
        page = fetch_contratos_page(
            ano=2026,
            sequencial=32,
            transport=SequencedTransport((200, body)),
            retry_policy=RetryPolicy(max_attempts=2),
            sleep=lambda _s: None,
        )

        assert page is not None
        self.assertEqual(len(page.items), 1)
        self.assertEqual(page.total_registros, 1)

    def test_contracts_endpoint_requests_selected_page(self) -> None:
        transport = SequencedTransport(
            (200, json.dumps({"data": [{}], "totalPaginas": 2}).encode())
        )

        page = fetch_contratos_page(
            ano=2026,
            sequencial=32,
            pagina=2,
            transport=transport,
            retry_policy=RetryPolicy(max_attempts=2),
            sleep=lambda _s: None,
        )

        assert page is not None
        self.assertIn("pagina=2", page.request_url)
        self.assertEqual(page.cursor["pagina"], 2)


class ItensPaginationTests(unittest.TestCase):
    def test_stops_when_api_ignores_pagination(self) -> None:
        full_page = itens_body(list(range(1, COMPRAS_PAGE_SIZE + 1)))
        pages = collect_itens_pages(
            ano=2025,
            sequencial=9,
            logger=logging.getLogger("test"),
            transport=SequencedTransport((200, full_page)),
        )

        self.assertEqual(len(pages), 1)

    def test_walks_real_pagination_until_short_page(self) -> None:
        first = itens_body(list(range(1, COMPRAS_PAGE_SIZE + 1)))
        second = itens_body([COMPRAS_PAGE_SIZE + 1])
        pages = collect_itens_pages(
            ano=2025,
            sequencial=9,
            logger=logging.getLogger("test"),
            transport=SequencedTransport((200, first), (200, second)),
        )

        self.assertEqual(len(pages), 2)
        self.assertEqual(len(pages[1].items), 1)

    def test_reaching_page_cap_is_reported_as_truncated(self) -> None:
        first = itens_body(list(range(1, COMPRAS_PAGE_SIZE + 1)))
        second = itens_body(
            list(range(COMPRAS_PAGE_SIZE + 1, (COMPRAS_PAGE_SIZE * 2) + 1))
        )

        with patch(
            "barreiras_collectors.commands.collect_pncp_itens.MAX_ITENS_PAGES",
            2,
        ):
            batch = collect_itens_batch(
                ano=2025,
                sequencial=9,
                logger=logging.getLogger("test"),
                transport=SequencedTransport((200, first), (200, second)),
            )

        self.assertEqual(len(batch.pages), 2)
        self.assertTrue(batch.truncated)


class ControlledPncpDependentResourcesTests(unittest.TestCase):
    @staticmethod
    def _control_probe(completed: dict[str, object]):
        class ControlProbe:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                del exc_type, exc_value, traceback
                return False

            def complete(self, **values):
                completed.update(values)

        return ControlProbe()

    def test_items_backlog_or_page_cap_marks_partition_partial(self) -> None:
        completed: dict[str, object] = {}

        execute_controlled_pncp_itens(
            control=self._control_probe(completed),  # type: ignore[arg-type]
            operation=lambda: PncpItensCollectionSummary(
                contratacoes_processed=50,
                itens_inserted=250,
                resultados_inserted=10,
                pending_truncated=True,
                item_pages_truncated_controls=(CONTROL,),
                start_offset=0,
                next_offset=50,
            ),
        )

        self.assertEqual(completed["outcome"].value, "partial")
        self.assertEqual(completed["observed_records"], 50)
        self.assertEqual(
            completed["checkpoint"],
            {
                "pending_truncated": True,
                "item_pages_truncated_controls": [CONTROL],
                "next_offset": 50,
            },
        )

    def test_empty_items_backlog_is_explicit_empty(self) -> None:
        completed: dict[str, object] = {}

        execute_controlled_pncp_itens(
            control=self._control_probe(completed),  # type: ignore[arg-type]
            operation=lambda: PncpItensCollectionSummary(
                0, 0, 0, False, (), 50, 0
            ),
        )

        self.assertEqual(completed["outcome"].value, "empty")

    def test_contracts_backlog_cap_marks_partition_partial(self) -> None:
        completed: dict[str, object] = {}

        execute_controlled_pncp_contratos(
            control=self._control_probe(completed),  # type: ignore[arg-type]
            operation=lambda: PncpContratosCollectionSummary(
                contratacoes_processed=50,
                pages=25,
                inserted_records=12,
                existing_records=13,
                pending_truncated=True,
                contract_pages_truncated_controls=(),
                start_offset=0,
                next_offset=50,
            ),
        )

        self.assertEqual(completed["outcome"].value, "partial")
        self.assertEqual(completed["observed_records"], 50)
        self.assertEqual(
            completed["checkpoint"],
            {
                "pending_truncated": True,
                "contract_pages_truncated_controls": [],
                "next_offset": 50,
            },
        )

    def test_contract_page_cap_is_reported_as_truncated(self) -> None:
        full = [
            {"numeroControlePNCP": f"13654405000195-2-{index:06d}/2026"}
            for index in range(COMPRAS_PAGE_SIZE)
        ]
        first = json.dumps(
            {"data": full, "totalPaginas": 3, "totalRegistros": 150}
        ).encode()
        second = json.dumps(
            {"data": full, "totalPaginas": 3, "totalRegistros": 150}
        ).encode()

        with patch(
            "barreiras_collectors.commands.collect_pncp_contratos."
            "MAX_CONTRATOS_PAGES",
            2,
        ):
            batch = collect_contratos_batch(
                ano=2026,
                sequencial=32,
                logger=logging.getLogger("test"),
                transport=SequencedTransport((200, first), (200, second)),
            )

        self.assertEqual(len(batch.pages), 2)
        self.assertTrue(batch.truncated)

    def test_contract_list_root_probes_until_short_page(self) -> None:
        first = json.dumps(
            [
                {
                    "numeroControlePNCP": (
                        f"13654405000195-2-{index:06d}/2026"
                    )
                }
                for index in range(COMPRAS_PAGE_SIZE)
            ]
        ).encode()
        second = json.dumps(
            [{"numeroControlePNCP": "13654405000195-2-999999/2026"}]
        ).encode()

        batch = collect_contratos_batch(
            ano=2026,
            sequencial=32,
            logger=logging.getLogger("test"),
            transport=SequencedTransport((200, first), (200, second)),
        )

        self.assertEqual(len(batch.pages), 2)
        self.assertFalse(batch.truncated)

    def test_backlog_resume_accepts_only_non_negative_integer(self) -> None:
        self.assertEqual(resolve_checkpoint_offset({"next_offset": 50}), 50)
        self.assertEqual(resolve_checkpoint_offset({"next_offset": "50"}), 0)
        self.assertEqual(resolve_checkpoint_offset({"next_offset": -1}), 0)
        self.assertEqual(resolve_checkpoint_offset(None), 0)


class FakeObjectStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_if_absent(self, *, object_key, body, content_type, expected_sha256):
        del content_type
        created = object_key not in self.objects
        self.objects.setdefault(object_key, body)
        return SimpleNamespace(
            sha256=expected_sha256,
            byte_size=len(body),
            created=created,
        )

    def read(self, object_key):
        return self.objects[object_key]


class FakeRepository:
    def __init__(self) -> None:
        self.batches = []

    def persist(self, batch):
        self.batches.append(batch)
        return SimpleNamespace(
            collection_run_id="run",
            raw_artifact_id="artifact",
            inserted_records=len(batch.records),
            existing_records=0,
        )


class ComprasPersistenceTests(unittest.TestCase):
    def test_itens_records_are_keyed_by_control_and_numero(self) -> None:
        page = fetch_itens(200, itens_body([5476570]))
        assert page is not None
        repository = FakeRepository()
        service = PncpComprasPersistenceService(
            object_store=FakeObjectStore(),
            repository=repository,
        )

        result = service.persist_itens(page, control=CONTROL)

        self.assertEqual(result.inserted_records, 1)
        record = repository.batches[0].records[0]
        self.assertEqual(record.record_type, "pncp_item")
        self.assertEqual(
            record.source_record_key,
            f"pncp:item:{CONTROL}:5476570",
        )
        self.assertTrue(
            repository.batches[0].object_key.startswith(
                "pncp/procurement/itens/sha256/"
            )
        )

    def test_item_without_numero_is_contract_error(self) -> None:
        page = fetch_itens(200, json.dumps([{"descricao": "x"}]).encode())
        assert page is not None
        service = PncpComprasPersistenceService(
            object_store=FakeObjectStore(),
            repository=FakeRepository(),
        )

        with self.assertRaises(PersistenceContractError):
            service.persist_itens(page, control=CONTROL)

    def test_resultado_records_carry_sequencial(self) -> None:
        body = json.dumps(
            [
                {
                    "sequencialResultado": 1,
                    "numeroItem": 5476570,
                    "numeroControlePNCPCompra": CONTROL,
                    "valorTotalHomologado": "34836.66",
                }
            ]
        ).encode()
        page = fetch_resultados_page(
            ano=2025,
            sequencial=9,
            numero_item=5476570,
            transport=SequencedTransport((200, body)),
            retry_policy=RetryPolicy(max_attempts=2),
            sleep=lambda _s: None,
        )
        assert page is not None
        repository = FakeRepository()
        service = PncpComprasPersistenceService(
            object_store=FakeObjectStore(),
            repository=repository,
        )

        service.persist_resultados(
            page,
            control=CONTROL,
            numero_item=5476570,
        )

        record = repository.batches[0].records[0]
        self.assertEqual(record.record_type, "pncp_resultado")
        self.assertEqual(
            record.source_record_key,
            f"pncp:resultado:{CONTROL}:5476570:1",
        )

    def test_contract_records_are_keyed_by_contract_control(self) -> None:
        body = json.dumps(
            [
                {
                    "numeroControlePNCP": "13654405000195-2-000001/2026",
                    "numeroControlePncpCompra": CONTROL,
                    "objetoContrato": "Serviço de manutenção",
                }
            ]
        ).encode()
        page = fetch_contratos_page(
            ano=2025,
            sequencial=9,
            transport=SequencedTransport((200, body)),
            retry_policy=RetryPolicy(max_attempts=2),
            sleep=lambda _s: None,
        )
        assert page is not None
        repository = FakeRepository()
        service = PncpComprasPersistenceService(
            object_store=FakeObjectStore(),
            repository=repository,
        )

        result = service.persist_contratos(page, control=CONTROL)

        self.assertEqual(result.inserted_records, 1)
        record = repository.batches[0].records[0]
        self.assertEqual(record.record_type, "pncp_contrato")
        self.assertEqual(
            record.source_record_key,
            "pncp:contrato:13654405000195-2-000001/2026",
        )
        self.assertTrue(
            repository.batches[0].object_key.startswith(
                "pncp/procurement/contratos/sha256/"
            )
        )

    def test_contract_with_wrong_parent_is_rejected(self) -> None:
        page = fetch_contratos_page(
            ano=2025,
            sequencial=9,
            transport=SequencedTransport(
                (
                    200,
                    json.dumps(
                        [
                            {
                                "numeroControlePNCP": "13654405000195-2-000001/2026",
                                "numeroControlePNCPCompra": "outro",
                            }
                        ]
                    ).encode(),
                )
            ),
            retry_policy=RetryPolicy(max_attempts=2),
            sleep=lambda _s: None,
        )
        assert page is not None
        service = PncpComprasPersistenceService(
            object_store=FakeObjectStore(),
            repository=FakeRepository(),
        )

        with self.assertRaises(PersistenceContractError):
            service.persist_contratos(page, control=CONTROL)


if __name__ == "__main__":
    unittest.main()
