from __future__ import annotations

import hashlib
import unittest
from dataclasses import replace
from unittest.mock import Mock

from barreiras_collectors.connectors.querido_diario import CollectedPage
from barreiras_collectors.persistence.fns import FNSPairPersistenceService
from barreiras_collectors.persistence.models import ArtifactIntegrityError

from tests.collectors.test_fns_payment_evidence import envelope, order, payment


def page(kind, body):
    query = (
        "ano=2025&tipoConsulta=2&estado=BA&municipio=290320&acoes=65061"
        "&cpfCnpjUg=08595187000125"
        if kind == "payment-detail"
        else "anoPagamento=2025&ano=2025&mes=10&uf=BA&"
        "numeroDocumentoSiafi=055607&tipoDocumentoPagamento=OB"
    )
    route = (
        "detalhe-pagamento" if kind == "payment-detail" else "detalhe-ordem-bancaria"
    )
    url = (
        f"https://consultafns.saude.gov.br/recursos/consulta-detalhada/{route}?{query}"
    )
    return CollectedPage(
        schema_name="fns-payment-response",
        schema_version="1.0.0",
        source_code="fns-consulta-detalhada",
        endpoint_code=kind,
        idempotency_key="untrusted-caller-key",
        request_url=url,
        final_url=url,
        requested_at="2026-09-05T10:00:00+00:00",
        received_at="2026-09-05T10:00:01+00:00",
        attempts=1,
        http_status=200,
        collection_status="complete",
        body_sha256=hashlib.sha256(body).hexdigest(),
        body_size_bytes=len(body),
        media_type="application/json",
        response_headers={},
        cursor={},
        raw_body=body,
        parsed=None,
    )


class FNSPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.p = page("payment-detail", envelope(payment()))
        self.o = page("payment-order-detail", envelope(order()))
        self.store = Mock()
        self.store.read.side_effect = [self.p.raw_body, self.o.raw_body]
        self.repo = Mock()
        self.service = FNSPairPersistenceService(
            object_store=self.store, repository=self.repo
        )

    def persist(self, p=None, o=None):
        return self.service.persist(
            payment=p or self.p,
            order=o or self.o,
            action_id=65061,
            payment_year=2025,
            order_number="055607",
        )

    def test_both_originals_are_verified_before_any_registration(self):
        def registered(_batch):
            self.assertEqual(self.store.read.call_count, 2)

        self.repo.persist.side_effect = registered
        self.persist()
        self.assertEqual(self.store.read.call_count, 2)
        self.assertEqual(self.repo.persist.call_count, 2)
        self.store.put_if_absent.assert_not_called()
        for call in self.repo.persist.call_args_list:
            batch = call.args[0]
            self.assertEqual(batch.records, ())  # no raw banking JSON in records
            self.assertEqual(batch.page.collection_status, "partial")
            self.assertNotEqual(batch.page.idempotency_key, "untrusted-caller-key")
            self.assertEqual(
                batch.object_key,
                f"fns/payments/2025/sha256/{batch.page.body_sha256[:2]}/"
                f"{batch.page.body_sha256}.json",
            )

    def test_corrupt_second_object_blocks_both_registrations(self):
        self.store.read.side_effect = [self.p.raw_body, b"CORRUPT_PRIVATE_VALUE"]
        with self.assertRaises(ArtifactIntegrityError) as caught:
            self.persist()
        self.assertNotIn("CORRUPT_PRIVATE_VALUE", str(caught.exception))
        self.repo.persist.assert_not_called()

    def test_invalid_metadata_or_scope_does_not_touch_storage(self):
        for changes in (
            {"body_sha256": "0" * 64},
            {"body_size_bytes": 0},
            {"http_status": 500},
            {"media_type": "text/html"},
            {"source_code": "other"},
            {"received_at": "2026-09-04T10:00:00Z"},
            {"requested_at": "2026-09-05T10:00:00"},
            {"final_url": self.p.final_url.replace("acoes=65061", "acoes=68909")},
            {"request_url": self.p.request_url.replace("https:", "http:")},
            {"request_url": self.p.request_url + "&acoes=68909"},
            {
                "request_url": self.p.request_url.replace(
                    "08595187000125", "00000000000000"
                )
            },
        ):
            with (
                self.subTest(changes=changes),
                self.assertRaises(ArtifactIntegrityError),
            ):
                self.persist(p=replace(self.p, **changes))
        self.store.read.assert_not_called()
        self.repo.persist.assert_not_called()

    def test_second_registration_failure_is_reported_and_replay_is_possible(self):
        self.repo.persist.side_effect = [Mock(), RuntimeError("database unavailable")]
        with self.assertRaises(RuntimeError):
            self.persist()
        keys = [
            call.args[0].artifact_idempotency_key
            for call in self.repo.persist.call_args_list
        ]
        self.store.read.side_effect = [self.p.raw_body, self.o.raw_body]
        self.repo.persist.side_effect = [Mock(), Mock()]
        self.persist()
        self.assertEqual(
            keys,
            [
                call.args[0].artifact_idempotency_key
                for call in self.repo.persist.call_args_list[2:]
            ],
        )

    def test_replay_identity_stable_and_headers_not_forwarded(self):
        self.persist(p=replace(self.p, response_headers={"set-cookie": "PRIVATE"}))
        first = self.repo.persist.call_args_list[0].args[0]
        self.store.read.side_effect = [self.p.raw_body, self.o.raw_body]
        self.persist(p=replace(self.p, idempotency_key="different"))
        second = self.repo.persist.call_args_list[2].args[0]
        self.assertEqual(
            first.artifact_idempotency_key, second.artifact_idempotency_key
        )
        self.assertEqual(first.page.response_headers, {})
        self.assertEqual(first.page.received_at, self.p.received_at)

    def test_invalid_pair_is_not_registered(self):
        value = order()
        value["valor"] = 1
        with self.assertRaises(ValueError):
            self.persist(o=page("payment-order-detail", envelope(value)))
        self.repo.persist.assert_not_called()
