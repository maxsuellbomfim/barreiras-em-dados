from __future__ import annotations

import json
import unittest
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from barreiras_collectors.commands import collect_pncp_contratos as command
from barreiras_collectors.persistence.service import PncpComprasPersistenceService

from tests.collectors import test_pncp_contract_inconclusive_batch as helpers
from tests.collectors.test_pncp_contract_inconclusive_batch import (
    Backlog,
    body,
    control,
)
from tests.collectors.test_pncp_itens import FakeObjectStore


class ContractObservationEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.helper = helpers.ContractInconclusiveBatchTests()
        self.repository = Backlog(count=1)
        self.service = PncpComprasPersistenceService(
            object_store=FakeObjectStore(), repository=self.repository
        )

    def collect(self, batch, service=None):
        with patch.object(command, "collect_contratos_batch", return_value=batch):
            return self.helper.collect(self.repository, service or self.service)

    def test_empty_query_has_preserved_evidence_not_global_completeness(self):
        batch = self.helper.batch((200, b"[]"))
        observation = self.collect(batch).control_observations[0]
        self.assertEqual(observation["version"], 1)
        self.assertEqual(observation["scope"], "pncp_contracts_query")
        self.assertEqual(observation["state"], "empty_confirmed")
        self.assertEqual(observation["control"], control(1))
        self.assertEqual(observation["records_preserved"], 0)
        self.assertEqual(len(observation["pages"]), 1)
        evidence = observation["pages"][0]
        self.assertTrue(evidence["raw_artifact_id"])
        self.assertEqual(evidence["sha256"], batch.pages[0].body_sha256)
        self.assertEqual(evidence["page"], 1)
        self.assertEqual(evidence["http_status"], 200)
        self.assertEqual(evidence["records"], 0)
        self.assertLessEqual(
            datetime.fromisoformat(observation["started_at"]),
            datetime.fromisoformat(observation["finished_at"]),
        )
        self.assertIsNotNone(datetime.fromisoformat(observation["finished_at"]).tzinfo)
        self.assertNotIn("raw_body", json.dumps(observation))

    def test_success_counts_observed_rows_even_when_already_preserved(self):
        batch = self.helper.batch((200, body(count=1)))
        first = self.collect(batch).control_observations[0]
        second = self.collect(batch).control_observations[0]
        self.assertEqual(first["state"], "query_complete")
        self.assertEqual(second["records_preserved"], 1)
        self.assertEqual(first["pages"][0]["sha256"], second["pages"][0]["sha256"])

    def test_inconclusive_response_has_no_fabricated_artifact(self):
        for status in (404, 204):
            with self.subTest(status=status):
                observation = self.collect(
                    self.helper.batch((status, b""))
                ).control_observations[0]
                self.assertEqual(observation["state"], "inconclusive")
                self.assertEqual(observation["http_status"], status)
                self.assertEqual(observation["pages"], [])
                self.assertIsNone(observation["records_preserved"])

    def test_partial_query_keeps_valid_pages_without_claiming_total(self):
        observation = self.collect(
            self.helper.batch((200, body()), (404, b""))
        ).control_observations[0]
        self.assertEqual(observation["state"], "inconclusive")
        self.assertEqual(observation["records_preserved"], 50)
        self.assertEqual(len(observation["pages"]), 1)
        self.assertEqual(observation["response_page"], 2)

    def test_page_limit_is_distinct_from_response_failure(self):
        batch = self.helper.batch((200, body(count=1)))
        observation = self.collect(replace(batch, truncated=True)).control_observations[
            0
        ]
        self.assertEqual(observation["state"], "partial")
        self.assertEqual(observation["reason"], "page_limit")

    def test_storage_failure_cannot_publish_empty_or_leak_exception(self):
        def fail(*args, **kwargs):
            raise RuntimeError("private-secret-that-must-not-be-copied")

        with self.assertRaises(command.PncpContratosBatchFailure) as raised:
            self.collect(
                self.helper.batch((200, b"[]")), SimpleNamespace(persist_contratos=fail)
            )
        observation = raised.exception.summary.control_observations[0]
        self.assertEqual(observation["state"], "interrupted")
        self.assertEqual(observation["pages"], [])
        self.assertIsNone(observation["records_preserved"])
        self.assertNotIn("private-secret", json.dumps(observation))

    def test_hash_mismatch_fails_closed(self):
        persist = self.service.persist_contratos

        def wrong_hash(*args, **kwargs):
            return replace(persist(*args, **kwargs), sha256="0" * 64)

        with self.assertRaises(command.PncpContratosBatchFailure) as raised:
            self.collect(
                self.helper.batch((200, b"[]")),
                SimpleNamespace(persist_contratos=wrong_hash),
            )
        self.assertEqual(raised.exception.summary.empty_controls, ())
        self.assertEqual(
            raised.exception.summary.control_observations[0]["state"], "interrupted"
        )

    def test_failure_after_first_page_retains_only_verified_evidence(self):
        batch = self.helper.batch((200, body()), (200, b"[]"))
        persist = self.service.persist_contratos
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("storage failure")
            return persist(*args, **kwargs)

        with self.assertRaises(command.PncpContratosBatchFailure) as raised:
            self.collect(batch, SimpleNamespace(persist_contratos=fail_second))
        observation = raised.exception.summary.control_observations[0]
        self.assertEqual(observation["state"], "interrupted")
        self.assertEqual(len(observation["pages"]), 1)
        self.assertEqual(observation["records_preserved"], 50)
        self.assertEqual(raised.exception.summary.retry_controls, (control(1),))

    def test_unattempted_controls_are_not_given_observations(self):
        self.repository.count = 3
        self.service = SimpleNamespace(persist_contratos=lambda *a, **k: None)
        with self.assertRaises(command.PncpContratosBatchFailure) as raised:
            self.collect(self.helper.batch((200, b"[]")))
        self.assertEqual(
            [item["control"] for item in raised.exception.summary.control_observations],
            [control(1)],
        )
        self.assertEqual(len(self.repository.progress[0]["retry_controls"]), 3)

    def test_observations_reach_private_run_metrics(self):
        summary = self.collect(self.helper.batch((200, b"[]")))
        completed = {}

        class Lifecycle:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def complete(self, **values):
                completed.update(values)

        command.execute_controlled_pncp_contratos(
            control=Lifecycle(), operation=lambda: summary
        )
        self.assertEqual(
            completed["metrics"]["control_observations"],
            list(summary.control_observations),
        )


if __name__ == "__main__":
    unittest.main()
