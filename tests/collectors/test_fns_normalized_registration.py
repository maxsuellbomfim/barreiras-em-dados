import unittest
from dataclasses import replace
from unittest.mock import Mock

from barreiras_collectors.persistence.fns_payments import (
    FNSPaymentPagesPersistenceService,
)
from barreiras_collectors.persistence.models import ArtifactIntegrityError

from tests.collectors.test_fns_payment_pages import page as response
from tests.collectors.test_fns_payment_pages import payment
from tests.collectors.test_fns_persistence import page


class NormalizedRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.pages = []
        for index, row in enumerate((payment(reason="PRIVATE"), payment("000002"))):
            p = page("payment-detail", response(index, row))
            url = (
                p.request_url.replace("acoes=65061", "acoes=66458")
                + f"&page={index + 1}&count=1"
            )
            self.pages.append(replace(p, request_url=url, final_url=url))
        self.store, self.repo = Mock(), Mock()
        self.store.read.side_effect = [p.raw_body for p in self.pages]
        self.service = FNSPaymentPagesPersistenceService(
            object_store=self.store, repository=self.repo
        )

    def persist(self):
        return self.service.persist(
            pages=self.pages, action_id=66458, payment_year=2025
        )

    def test_all_bytes_verified_before_normalized_records_written(self):
        def write(batch):
            self.assertEqual(self.store.read.call_count, 2)
            self.assertEqual(len(batch.records), 1)
            row = batch.records[0]
            self.assertEqual(row.record_type, "fns_payment_observation")
            self.assertNotIn("PRIVATE", str(row.payload))
            self.assertFalse(row.payload["publication_allowed"])
            self.assertEqual(row.payload["order_verification"], "pending")
            self.assertEqual(batch.page.collection_status, "partial")

        self.repo.persist.side_effect = write
        report, _ = self.persist()
        self.assertEqual(report["status"], "review_required")

    def test_bad_last_original_blocks_whole_batch(self):
        self.store.read.side_effect = [self.pages[0].raw_body, b"BAD"]
        with self.assertRaises(ArtifactIntegrityError):
            self.persist()
        self.repo.persist.assert_not_called()

    def test_wrong_beneficiary_page_or_final_url_blocks_before_upload(self):
        p = self.pages[1]
        for old, new in [
            ("08595187000125", "00000000000000"),
            ("page=2", "page=1"),
            ("acoes=66458", "acoes=65061"),
        ]:
            self.pages[1] = replace(p, final_url=p.final_url.replace(old, new))
            with self.assertRaises(ArtifactIntegrityError):
                self.persist()
        self.store.read.assert_not_called()
        self.repo.persist.assert_not_called()

    def test_replay_retains_keys_and_lineage(self):
        self.persist()
        first = [c.args[0] for c in self.repo.persist.call_args_list]
        self.store.read.side_effect = [p.raw_body for p in self.pages]
        self.persist()
        second = [c.args[0] for c in self.repo.persist.call_args_list[2:]]
        for a, b in zip(first, second, strict=True):
            self.assertEqual(a.artifact_idempotency_key, b.artifact_idempotency_key)
            self.assertEqual(a.records, b.records)
            self.assertEqual(a.records[0].payload["source_sha256"], a.page.body_sha256)
