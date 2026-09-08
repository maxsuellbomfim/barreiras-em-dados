import json
import unittest
from dataclasses import replace
from unittest.mock import Mock
from urllib.parse import urlencode

from barreiras_collectors.persistence.fns_comparisons import (
    FNSComparisonPersistenceService,
)
from barreiras_collectors.persistence.models import ArtifactIntegrityError

from tests.collectors.test_fns_payment_pages import page as response
from tests.collectors.test_fns_payment_pages import payment
from tests.collectors.test_fns_persistence import page


class ComparisonRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.payments = []
        for i, number in enumerate(("000001", "000002")):
            p = page("payment-detail", response(i, payment(number)))
            url = (
                p.request_url.replace("acoes=65061", "acoes=66458")
                + f"&page={i + 1}&count=1"
            )
            self.payments.append(replace(p, request_url=url, final_url=url))
        self.orders = [self.order()]
        self.repo = Mock()
        self.store = Mock()
        self.store.read.side_effect = self.read
        self.service = FNSComparisonPersistenceService(
            object_store=self.store, repository=self.repo
        )

    def order(self, *, empty=False, reason="", amount=95):
        scope = dict(
            anoPagamento="2025",
            ano="2024",
            mes="11",
            competencia="NOV de 2024",
            uf="BA",
            numeroDocumentoSiafi="000001",
            tipoDocumentoPagamento="OB",
        )
        rows = (
            []
            if empty
            else [
                dict(
                    codigoIBGE="290320",
                    municipio="BARREIRAS",
                    uf="BA",
                    valor=amount,
                    motivoRejeicao=reason,
                    anoExercicio="2024",
                    mesExercicio="11",
                    competencia="NOV de 2024",
                    contaCorrente="PRIVATE",
                )
            ]
        )
        raw = json.dumps(
            dict(
                resultado=dict(
                    pagina=0,
                    total=len(rows),
                    totalPaginas=len(rows),
                    itensPorPagina=10,
                    dados=rows,
                )
            )
        ).encode()
        p = page("payment-order-detail", raw)
        url = (
            p.request_url.split("?")[0] + "?" + urlencode(dict(scope, page=1, count=10))
        )
        return replace(p, request_url=url, final_url=url)

    def read(self, key):
        for p in self.payments + self.orders:
            if p.body_sha256 in key:
                return p.raw_body
        raise AssertionError("Unexpected original")

    def persist(self):
        return self.service.persist(
            payment_pages=self.payments,
            order_pages=self.orders,
            action_id=66458,
            payment_year=2025,
            order_number="000001",
        )

    def test_private_comparison_has_lineage_and_does_not_replace_observation(self):
        result, _ = self.persist()
        self.assertEqual(result["status"], "consistent_documentary_pair")
        batch = self.repo.persist.call_args.args[0]
        self.assertEqual(len(batch.records), 1)
        record = batch.records[0]
        self.assertEqual(record.record_type, "fns_document_comparison")
        self.assertFalse(record.payload["publication_allowed"])
        self.assertNotIn("PRIVATE", json.dumps(record.payload))
        self.assertEqual(
            record.payload["order_evidence"][0]["sha256"], self.orders[0].body_sha256
        )
        self.assertEqual(batch.page.body_sha256, self.payments[0].body_sha256)
        self.assertEqual(batch.page.collection_status, "partial")
        self.store.put_if_absent.assert_not_called()

    def test_replay_stable_but_changed_evidence_creates_new_version(self):
        self.persist()
        first = self.repo.persist.call_args.args[0]
        self.persist()
        self.assertEqual(first, self.repo.persist.call_args.args[0])
        self.orders = [self.order(reason="PRIVATE CANCELLED")]
        result, _ = self.persist()
        second = self.repo.persist.call_args.args[0]
        self.assertEqual(result["status"], "review_required")
        self.assertNotEqual(
            first.artifact_idempotency_key, second.artifact_idempotency_key
        )

    def test_absence_and_conflict_are_stored_without_payment_claim(self):
        for p, expected in (
            (self.order(empty=True), "order_not_found"),
            (self.order(amount=96), "document_conflict"),
        ):
            self.orders = [p]
            result, _ = self.persist()
            self.assertEqual(result["status"], expected)
            self.assertFalse(result["publication_allowed"])

    def test_bad_last_original_blocks_every_repository_write(self):
        self.store.read.side_effect = lambda key: (
            b"BAD" if self.orders[0].body_sha256 in key else self.read(key)
        )
        with self.assertRaises(ArtifactIntegrityError):
            self.persist()
        self.repo.persist.assert_not_called()

    def test_wrong_acquisition_scope_blocks_writes(self):
        self.orders[0] = replace(
            self.orders[0],
            final_url=self.orders[0].final_url.replace("ano=2024", "ano=2025"),
        )
        with self.assertRaises(ArtifactIntegrityError):
            self.persist()
        self.repo.persist.assert_not_called()

    def test_wrong_payment_beneficiary_blocks_writes(self):
        original = self.payments[0]
        self.payments[0] = replace(
            original,
            final_url=original.final_url.replace("08595187000125", "00000000000000"),
        )
        with self.assertRaises(ArtifactIntegrityError):
            self.persist()
        self.repo.persist.assert_not_called()

    def test_ambiguous_payment_does_not_create_comparison(self):
        original = self.payments[1]
        duplicate = page("payment-detail", response(1, payment("000001")))
        self.payments[1] = replace(
            duplicate, request_url=original.request_url, final_url=original.final_url
        )
        with self.assertRaises(ArtifactIntegrityError):
            self.persist()
        self.repo.persist.assert_not_called()
