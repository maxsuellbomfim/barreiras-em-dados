from __future__ import annotations

import hashlib
import json
import logging
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from barreiras_collectors.commands import collect_pncp_contratos as command
from barreiras_collectors.persistence.service import PncpComprasPersistenceService

from tests.collectors.test_pncp_itens import (
    FakeObjectStore,
    FakeRepository,
    SequencedTransport,
)


def control(number):
    return f"13654405000195-1-{number:06d}/2025"


def body(start=1, count=50):
    return json.dumps(
        [
            {
                "numeroControlePNCP": f"13654405000195-2-{n:06d}/2025",
                "numeroControlePNCPCompra": control(1),
            }
            for n in range(start, start + count)
        ]
    ).encode()


class Backlog(FakeRepository):
    def __init__(self, count=3):
        super().__init__()
        self.count = count
        self.progress = []

    def pncp_pending_contratos(self, **kwargs):
        after = kwargs["after_control"]
        return [
            (control(n), 2025, n)
            for n in range(1, self.count + 1)
            if after is None or control(n) > after
        ][: kwargs["limit"]]

    def checkpoint_progress(self, checkpoint):
        self.progress.append(checkpoint)


class ContractInconclusiveBatchTests(unittest.TestCase):
    def batch(self, *responses):
        return command.collect_contratos_batch(
            ano=2025,
            sequencial=1,
            logger=logging.getLogger("test"),
            transport=SequencedTransport(*responses),
        )

    def collect(self, repository, service, cursor=None):
        return command._collect_pending(
            repository=repository,
            service=service,
            logger=logging.getLogger("test"),
            cursor=cursor or command.PncpContratosCursor(),
            checkpoint_progress=repository.checkpoint_progress,
        )

    def test_404_and_204_are_inconclusive_not_completed_empty(self):
        for status in (404, 204):
            with self.subTest(status=status):
                batch = self.batch((status, b""))
                self.assertTrue(batch.incomplete_reason)
                self.assertEqual(batch.http_status, status)
                self.assertEqual(batch.pages, ())

    def test_explicit_unpublished_response_keeps_retry_and_partial_coverage(self):
        payload = {
            "status": "404",
            "message": "Não há contrato publicado no PNCP para esta contratação.",
            "path": "/pncp-api/v1/orgaos/13654405000195/contratos/contratacao/2025/1",
        }
        batch = self.batch((404, json.dumps(payload).encode()))
        self.assertEqual(
            batch.incomplete_reason, "source_reports_no_published_contract"
        )
        repository = Backlog(count=1)
        with patch.object(command, "collect_contratos_batch", return_value=batch):
            summary = self.collect(repository, repository)
        self.assertEqual(summary.outcome.value, "partial")
        self.assertEqual(summary.retry_controls, (control(1),))
        self.assertEqual(summary.empty_controls, ())
        self.assertEqual(repository.batches, [])

    def test_valid_page_followed_by_404_keeps_page_but_not_completion(self):
        batch = self.batch((200, body()), (404, b""))
        self.assertEqual(len(batch.pages), 1)
        self.assertTrue(batch.incomplete_reason)
        self.assertEqual(batch.response_page, 2)

    def test_repeated_full_page_does_not_certify_end(self):
        batch = self.batch((200, body()), (200, body()))
        self.assertEqual(len(batch.pages), 1)
        self.assertEqual(batch.incomplete_reason, "repeated_page")

    def test_repeated_rows_in_paginated_object_do_not_certify_end(self):
        payload = {"data": json.loads(body()), "totalPaginas": 2, "totalRegistros": 100}
        batch = self.batch((200, json.dumps(payload).encode()))
        self.assertEqual(len(batch.pages), 1)
        self.assertEqual(batch.incomplete_reason, "repeated_page")

    def test_declared_total_cannot_hide_missing_rows(self):
        payload = {
            "data": json.loads(body(count=1)),
            "totalPaginas": 1,
            "totalRegistros": 2,
        }
        batch = self.batch((200, json.dumps(payload).encode()))
        self.assertTrue(batch.incomplete_reason)

    def test_inconclusive_controls_do_not_starve_later_controls(self):
        repository = Backlog()
        store = FakeObjectStore()
        service = PncpComprasPersistenceService(
            object_store=store, repository=repository
        )
        batches = [
            self.batch((404, b"")),
            self.batch((204, b"")),
            self.batch((200, b"[]")),
        ]
        with patch.object(command, "collect_contratos_batch", side_effect=batches):
            summary = self.collect(repository, service)
        self.assertEqual(summary.contratacoes_processed, 3)
        self.assertEqual(summary.outcome.value, "partial")
        self.assertEqual(summary.retry_controls, (control(1), control(2)))
        self.assertIsNone(summary.next_after_control)
        self.assertEqual(summary.empty_controls, (control(3),))
        self.assertEqual(len(summary.response_issues), 2)
        self.assertEqual(summary.inserted_records, 0)
        self.assertEqual(len(repository.batches), 1)
        self.assertEqual(repository.batches[0].records, ())
        self.assertIn(b"[]", store.objects.values())
        self.assertEqual(
            repository.batches[0].page.body_sha256, hashlib.sha256(b"[]").hexdigest()
        )

    def test_empty_evidence_clears_retry_only_after_storage_succeeds(self):
        repository = Backlog(count=1)
        service = PncpComprasPersistenceService(
            object_store=FakeObjectStore(), repository=repository
        )
        cursor = command.PncpContratosCursor(retry_controls=(control(1),))
        with patch.object(
            command, "collect_contratos_batch", return_value=self.batch((200, b"[]"))
        ):
            summary = self.collect(repository, service, cursor)
        self.assertEqual(summary.retry_controls, ())
        self.assertEqual(summary.outcome.value, "complete")
        self.assertEqual(summary.empty_controls, (control(1),))

        service = SimpleNamespace(
            persist_contratos=lambda *a, **kw: (_ for _ in ()).throw(
                RuntimeError("storage")
            )
        )
        with patch.object(
            command, "collect_contratos_batch", return_value=self.batch((200, b"[]"))
        ):
            with self.assertRaises(command.PncpContratosBatchFailure) as raised:
                self.collect(repository, service, cursor)
        self.assertEqual(raised.exception.summary.retry_controls, (control(1),))
        self.assertEqual(raised.exception.summary.empty_controls, ())

    def test_none_page_defensively_remains_pending_for_new_control(self):
        with patch.object(command, "fetch_contratos_page", return_value=None):
            batch = self.batch((200, b"[]"))
        self.assertTrue(batch.incomplete_reason)
        repository = Backlog(count=1)
        with patch.object(command, "collect_contratos_batch", return_value=batch):
            summary = self.collect(repository, repository)
        self.assertEqual(summary.retry_controls, (control(1),))

    def test_fifty_inconclusive_controls_do_not_starve_fifty_first(self):
        repository = Backlog(count=51)
        service = PncpComprasPersistenceService(
            object_store=FakeObjectStore(), repository=repository
        )
        failed = self.batch((404, b""))
        empty = self.batch((200, b"[]"))
        with patch.object(
            command, "collect_contratos_batch", side_effect=[*[failed] * 50, empty]
        ):
            first = self.collect(repository, service)
            second = self.collect(
                repository,
                service,
                command.resolve_contract_checkpoint(first.checkpoint),
            )
        self.assertEqual(first.next_after_control, control(50))
        self.assertEqual(first.retry_controls, tuple(control(n) for n in range(1, 51)))
        self.assertEqual(second.retry_controls, first.retry_controls)
        self.assertEqual(second.empty_controls, (control(51),))
        self.assertEqual(second.outcome.value, "partial")
        self.assertIsNone(second.next_after_control)
        self.assertEqual(len(repository.batches), 1)

    def test_control_records_partial_incident_and_explains_each_response(self):
        repository = Backlog(count=1)
        completed = {}

        class Lifecycle:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def complete(self, **values):
                completed.update(values)

        lifecycle = Lifecycle()
        with patch.object(
            command, "collect_contratos_batch", return_value=self.batch((404, b""))
        ):
            command.execute_controlled_pncp_contratos(
                control=lifecycle,
                operation=lambda: self.collect(repository, repository),
            )
        self.assertEqual(completed["outcome"].value, "partial")
        self.assertIsNotNone(completed["partial_failure"])
        self.assertEqual(completed["checkpoint"]["retry_controls"], [control(1)])
        self.assertEqual(completed["metrics"]["empty_controls"], [])
        self.assertEqual(
            completed["metrics"]["response_issues"],
            [
                {
                    "control": control(1),
                    "reason": "http_not_found",
                    "http_status": 404,
                    "pagina": 1,
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
