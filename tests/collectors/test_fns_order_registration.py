import json
import unittest
from dataclasses import replace
from unittest.mock import Mock
from urllib.parse import urlencode

from barreiras_collectors.persistence.fns import FNSOrderPersistenceService
from barreiras_collectors.persistence.models import ArtifactIntegrityError

from tests.collectors.test_fns_order_pages import body, row
from tests.collectors.test_fns_persistence import page


class OrderRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.scope = dict(
            anoPagamento="2025",
            mes="04",
            ano="2025",
            competencia="Única em 2025",
            uf="BA",
            numeroDocumentoSiafi="016551",
            tipoDocumentoPagamento="OB",
        )
        self.pages = []
        for index, rows in enumerate(
            (
                [row(reason="PRIVATE CANCELAMENTO"), row("1", "OUTRO")],
                [row("2", "OUTRO")],
            )
        ):
            capture = page("payment-order-detail", body(index, rows))
            url = (
                capture.request_url.split("?")[0]
                + "?"
                + urlencode(dict(self.scope, page=str(index + 1), count="2"))
            )
            self.pages.append(replace(capture, request_url=url, final_url=url))
        self.store, self.repo = Mock(), Mock()
        self.store.read.side_effect = [p.raw_body for p in self.pages]
        self.service = FNSOrderPersistenceService(
            object_store=self.store, repository=self.repo
        )

    def persist(self):
        return self.service.persist(pages=self.pages, scope=self.scope)

    def test_rejected_order_is_preserved_without_financial_records(self):
        def write(batch):
            self.assertEqual(self.store.read.call_count, 2)
            self.assertEqual(batch.records, ())
            self.assertEqual(batch.page.collection_status, "partial")
            self.assertEqual(batch.page.response_headers, {})
            self.assertIsNone(batch.page.parsed)

        self.repo.persist.side_effect = write
        diagnostic, results = self.persist()
        self.assertEqual(diagnostic["status"], "review_required")
        self.assertFalse(diagnostic["publication_allowed"])
        self.assertEqual(len(results), 2)
        self.store.put_if_absent.assert_not_called()

    def test_bad_second_original_blocks_all_writes(self):
        self.store.read.side_effect = [self.pages[0].raw_body, b"PRIVATE BAD"]
        with self.assertRaises(ArtifactIntegrityError) as error:
            self.persist()
        self.assertNotIn("PRIVATE", str(error.exception))
        self.repo.persist.assert_not_called()

    def test_empty_response_preserves_evidence_without_financial_records(self):
        raw = json.dumps(
            dict(
                resultado=dict(
                    pagina=0, total=0, totalPaginas=0, itensPorPagina=10, dados=[]
                )
            )
        ).encode()
        capture = page("payment-order-detail", raw)
        url = (
            capture.request_url.split("?")[0]
            + "?"
            + urlencode(dict(self.scope, page="1", count="10"))
        )
        self.pages = [replace(capture, request_url=url, final_url=url)]
        self.store.read.side_effect = [raw]
        diagnostic, _ = self.persist()
        self.assertEqual(diagnostic["status"], "not_found")
        batch = self.repo.persist.call_args.args[0]
        self.assertEqual(batch.records, ())
        self.assertEqual(batch.page.collection_status, "partial")
        self.assertFalse(diagnostic["publication_allowed"])

    def test_incomplete_order_does_not_touch_storage(self):
        self.pages = self.pages[:1]
        with self.assertRaises(ArtifactIntegrityError):
            self.persist()
        self.store.read.assert_not_called()
        self.repo.persist.assert_not_called()

    def test_same_bytes_in_different_order_keep_distinct_registration_identity(self):
        self.persist()
        first = self.repo.persist.call_args_list[0].args[0]
        self.scope["numeroDocumentoSiafi"] = "018794"
        self.pages = [
            replace(
                p,
                request_url=p.request_url.replace("016551", "018794"),
                final_url=p.final_url.replace("016551", "018794"),
            )
            for p in self.pages
        ]
        self.store.read.side_effect = [p.raw_body for p in self.pages]
        self.persist()
        second = self.repo.persist.call_args_list[2].args[0]
        self.assertEqual(first.object_key, second.object_key)
        self.assertNotEqual(
            first.artifact_idempotency_key, second.artifact_idempotency_key
        )

    def test_invalid_metadata_or_request_url_blocks_before_storage(self):
        original = self.pages[1]
        for change in [
            dict(received_at="2020-01-01T00:00:00Z"),
            dict(media_type="text/html"),
            dict(body_size_bytes=0),
            dict(request_url=original.request_url.replace("016551", "018794")),
        ]:
            with self.subTest(change=change), self.assertRaises(ArtifactIntegrityError):
                self.pages[1] = replace(original, **change)
                self.persist()
        self.store.read.assert_not_called()
        self.repo.persist.assert_not_called()

    def test_replay_keys_are_stable_after_partial_database_failure(self):
        self.repo.persist.side_effect = [Mock(), RuntimeError("unavailable")]
        with self.assertRaises(RuntimeError):
            self.persist()
        keys = [
            c.args[0].artifact_idempotency_key for c in self.repo.persist.call_args_list
        ]
        self.store.read.side_effect = [p.raw_body for p in self.pages]
        self.repo.persist.side_effect = [Mock(), Mock()]
        self.persist()
        self.assertEqual(
            keys,
            [
                c.args[0].artifact_idempotency_key
                for c in self.repo.persist.call_args_list[2:]
            ],
        )
