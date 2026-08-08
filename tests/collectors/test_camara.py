from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from barreiras_collectors.connectors.camara import (
    CamaraError,
    deputies_page_url,
    deputy_detail_url,
    fetch_deputies_page,
    fetch_deputy_detail,
)
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.persistence.models import PersistenceContractError
from barreiras_collectors.persistence.service import CamaraPersistenceService
from barreiras_collectors.resilience import RetryPolicy


class OneShotTransport:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.body = body
        self.urls: list[str] = []

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds, max_body_bytes
        self.urls.append(url)
        return HttpResponse(
            status=self.status,
            headers={},
            body=self.body,
            final_url=url,
        )


class SequenceTransport:
    def __init__(self, responses: list[HttpResponse | BaseException]) -> None:
        self.responses = list(responses)
        self.calls = 0

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds, max_body_bytes
        self.calls += 1
        result = self.responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        return HttpResponse(
            status=result.status,
            headers=result.headers,
            body=result.body,
            final_url=url,
        )


def envelope(dados) -> bytes:
    return json.dumps({"dados": dados}).encode()


def fetch_page(status: int, body: bytes):
    return fetch_deputies_page(
        1,
        transport=OneShotTransport(status, body),
        retry_policy=RetryPolicy(max_attempts=2),
        sleep=lambda _s: None,
    )


class CamaraFetchTests(unittest.TestCase):
    def test_url_filters_bahia(self) -> None:
        self.assertIn("siglaUf=BA", deputies_page_url(1))
        self.assertTrue(deputy_detail_url(204560).endswith("/204560"))

    def test_list_page_is_persistable(self) -> None:
        page = fetch_page(
            200,
            envelope([{"id": 204560, "nome": "Fulano", "siglaPartido": "X"}]),
        )

        assert page is not None
        self.assertEqual(len(page.items), 1)
        self.assertEqual(page.source_code, "camara-federal")
        self.assertEqual(page.cursor["pagina"], 1)

    def test_detail_object_is_wrapped_as_single_item(self) -> None:
        page = fetch_deputy_detail(
            204560,
            transport=OneShotTransport(
                200,
                envelope({"id": 204560, "nomeCivil": "Fulano de Tal"}),
            ),
            retry_policy=RetryPolicy(max_attempts=2),
            sleep=lambda _s: None,
        )

        assert page is not None
        self.assertEqual(len(page.items), 1)
        self.assertEqual(page.cursor["deputado"], 204560)

    def test_empty_list_and_404_mean_no_content(self) -> None:
        self.assertIsNone(fetch_page(200, envelope([])))
        self.assertIsNone(fetch_page(404, b""))

    def test_missing_dados_is_explicit_failure(self) -> None:
        with self.assertRaises(CamaraError):
            fetch_page(200, json.dumps({"links": []}).encode())

    def test_non_json_is_explicit_failure(self) -> None:
        with self.assertRaises(CamaraError):
            fetch_page(200, b"<html>bloqueio</html>")

    def test_timeout_is_retried_before_success(self) -> None:
        transport = SequenceTransport(
            [
                TimeoutError("tempo esgotado"),
                HttpResponse(200, {}, envelope([{"id": 204560}]), "unused"),
            ]
        )
        sleeps: list[float] = []

        page = fetch_deputies_page(
            1,
            transport=transport,
            retry_policy=RetryPolicy(
                max_attempts=2,
                base_delay_seconds=1,
                max_delay_seconds=2,
            ),
            sleep=sleeps.append,
        )

        assert page is not None
        self.assertEqual(page.attempts, 2)
        self.assertEqual(transport.calls, 2)
        self.assertEqual(sleeps, [0.5])

    def test_persistent_transport_failure_raises_domain_error(self) -> None:
        transport = SequenceTransport([TimeoutError("um"), TimeoutError("dois")])

        with self.assertRaises(CamaraError) as captured:
            fetch_deputies_page(
                1,
                transport=transport,
                retry_policy=RetryPolicy(max_attempts=2),
                sleep=lambda _seconds: None,
            )

        self.assertIn("indisponível", str(captured.exception))
        self.assertEqual(transport.calls, 2)


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


class CamaraPersistenceTests(unittest.TestCase):
    def test_records_are_keyed_by_official_id(self) -> None:
        page = fetch_page(200, envelope([{"id": 204560, "nome": "Fulano"}]))
        assert page is not None
        repository = FakeRepository()
        service = CamaraPersistenceService(
            object_store=FakeObjectStore(),
            repository=repository,
        )

        service.persist(page, record_type="camara_deputado")

        record = repository.batches[0].records[0]
        self.assertEqual(record.source_record_key, "camara:deputado:204560")
        self.assertEqual(record.record_type, "camara_deputado")
        self.assertTrue(
            repository.batches[0].object_key.startswith(
                "camara-federal/deputados/sha256/"
            )
        )

    def test_record_without_id_is_contract_error(self) -> None:
        page = fetch_page(200, envelope([{"nome": "Sem identificador"}]))
        assert page is not None
        service = CamaraPersistenceService(
            object_store=FakeObjectStore(),
            repository=FakeRepository(),
        )

        with self.assertRaises(PersistenceContractError):
            service.persist(page, record_type="camara_deputado")


if __name__ == "__main__":
    unittest.main()
