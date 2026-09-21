from __future__ import annotations

import json
import logging
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from barreiras_collectors.commands import collect_pncp_contratos as command
from barreiras_collectors.connectors.pncp import PncpError, fetch_contratos_page
from barreiras_collectors.persistence.postgres import PostgresCollectionRepository
from barreiras_collectors.persistence.service import PncpComprasPersistenceService

from tests.collectors.test_pncp_itens import (
    FakeObjectStore,
    FakeRepository,
    SequencedTransport,
)

FUND = "13250888000162"
PURCHASE = f"{FUND}-1-000003/2026"
CONTRACT = "13654405000195-2-000023/2026"


class ContractOwnerTests(unittest.TestCase):
    def test_fund_purchase_can_have_prefeitura_contract(self):
        transport = SequencedTransport(
            (
                200,
                json.dumps(
                    [
                        {
                            "numeroControlePNCP": CONTRACT,
                            "numeroControlePNCPCompra": PURCHASE,
                        }
                    ]
                ).encode(),
            )
        )
        batch = command.collect_contratos_batch(
            ano=2026,
            sequencial=3,
            cnpj=FUND,
            logger=logging.getLogger("test"),
            transport=transport,
        )
        self.assertEqual(len(batch.pages), 1)
        self.assertIsNone(batch.incomplete_reason)
        self.assertIn(f"/orgaos/{FUND}/contratos/contratacao/2026/3", transport.urls[0])
        repository = FakeRepository()
        service = PncpComprasPersistenceService(
            object_store=FakeObjectStore(),
            repository=repository,
        )
        service.persist_contratos(batch.pages[0], control=PURCHASE)
        self.assertEqual(
            repository.batches[0].records[0].source_record_key,
            f"pncp:contrato:{CONTRACT}",
        )

    def test_invalid_owner_is_rejected_before_http(self):
        transport = SequencedTransport((200, b"[]"))
        with self.assertRaises(PncpError):
            fetch_contratos_page(
                ano=2026, sequencial=3, cnpj="../bad", transport=transport
            )
        self.assertEqual(transport.urls, [])

    def test_pending_passes_purchase_owner_to_batch(self):
        repository = SimpleNamespace(
            pncp_pending_contratos=lambda **kwargs: [
                (PURCHASE, 2026, 3),
            ]
        )
        batch = command.PncpContratosPageBatch((), False, "http_not_found", 404, 1)
        with patch.object(
            command, "collect_contratos_batch", return_value=batch
        ) as fetch:
            summary = command._collect_pending(
                repository=repository,
                service=SimpleNamespace(),
                logger=logging.getLogger("test"),
                cursor=command.PncpContratosCursor(),
                checkpoint_progress=lambda checkpoint: None,
            )
        self.assertEqual(fetch.call_args.kwargs["cnpj"], FUND)
        self.assertEqual(summary.retry_controls, (PURCHASE,))
        self.assertEqual(summary.outcome.value, "partial")

    def test_queue_requires_purchase_owner_in_artifact(self):
        connection = Mock()
        connection.execute.return_value.fetchall.return_value = []
        PostgresCollectionRepository(lambda: connection).pncp_pending_contratos(
            refresh_days=120,
            limit=51,
        )
        query = " ".join(connection.execute.call_args.args[0].split())
        self.assertIn(
            "substring(artifact.source_url from '/orgaos/([0-9]{14})/') "
            "= split_part(contratacao.control, '-', 1)",
            query,
        )
