from __future__ import annotations

import json
import logging
import unittest
from types import SimpleNamespace

from barreiras_collectors.commands.collect_pncp_itens import (
    collect_itens_pages,
)
from barreiras_collectors.connectors.pncp import (
    COMPRAS_PAGE_SIZE,
    PncpError,
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


if __name__ == "__main__":
    unittest.main()
