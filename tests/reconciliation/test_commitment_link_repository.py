from __future__ import annotations

import json
import unittest
from contextlib import nullcontext

from barreiras_reconciliation import commitment_contract_links as links
from barreiras_reconciliation.commands.link_commitments_to_contracts import (
    link_pending,
)
from barreiras_reconciliation.commitment_contract_links import (
    LinkDecision,
    MunicipalContract,
)
from barreiras_reconciliation.commitment_link_repository import (
    CommitmentLinkRepository,
    PendingCommitment,
)


class Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class Connection:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.queries: list[str] = []
        self.params: list[object] = []

    def execute(self, query, params=None):
        self.queries.append(" ".join(query.split()))
        self.params.append(params)
        return Result(self.rows)

    def transaction(self):
        return nullcontext()

    def close(self):
        return None


class RepositoryTests(unittest.TestCase):
    def test_contracts_are_latest_version_per_official_portal_id(self) -> None:
        connection = Connection(
            [
                {
                    "raw_record_id": "r1",
                    "portal_id": "1520",
                    "number": "098/2026",
                    "contractor": "CONSTRUTORA E SERVIÇOS CHAGAS LTDA",
                }
            ]
        )

        contracts = CommitmentLinkRepository(lambda: connection).municipal_contracts()

        query = connection.queries[0]
        self.assertIn("select distinct on (record.payload ->> 'id')", query)
        self.assertIn("record_type = 'municipal_transparency_contratos'", query)
        self.assertIn("record.collected_at desc", query)
        self.assertEqual(
            contracts,
            (
                MunicipalContract(
                    "r1", "098/2026", "CONSTRUTORA E SERVIÇOS CHAGAS LTDA", "1520"
                ),
            ),
        )

    def test_pending_excludes_commitments_already_decided_by_this_rule(self) -> None:
        connection = Connection(
            [{"raw_record_id": "c1", "payload": {links.FIELD_KEY: "O-1"}}]
        )

        pending = CommitmentLinkRepository(lambda: connection).pending_commitments(
            links.RULE_VERSION, 10
        )

        query = connection.queries[0]
        self.assertIn("record.record_type = 'municipal_commitment_webrun'", query)
        self.assertIn("link.rule_version = %s", query)
        self.assertEqual(connection.params[0], (links.RULE_VERSION, 10))
        self.assertEqual(pending[0].row, {links.FIELD_KEY: "O-1"})

    def test_decisions_are_inserted_append_only(self) -> None:
        connection = Connection([{"inserted": 1}])
        decision = LinkDecision(
            "O-1",
            links.LINKED,
            "",
            "Contrato nº 098/2026",
            "r1",
            contract_portal_id="1520",
        )

        inserted = CommitmentLinkRepository(lambda: connection).record_decisions(
            (("c1", decision),)
        )

        query = connection.queries[0]
        self.assertIn("insert into finance.commitment_contract_links", query)
        self.assertIn(
            "on conflict (commitment_raw_record_id, rule_version) do nothing", query
        )
        self.assertNotIn("update", query.lower().replace("update_", ""))
        payload = json.loads(connection.params[0][0])
        self.assertEqual(payload[0]["contract_portal_id"], "1520")
        self.assertEqual(payload[0]["rule_version"], links.RULE_VERSION)
        self.assertEqual(inserted, 1)


class FakeRepository:
    def __init__(self, pending):
        self.pending = list(pending)
        self.recorded = []

    def municipal_contracts(self):
        return (
            MunicipalContract(
                "r1", "098/2026", "CONSTRUTORA E SERVIÇOS CHAGAS LTDA", "1520"
            ),
        )

    def pending_commitments(self, rule_version, limit):
        batch, self.pending = self.pending[:limit], self.pending[limit:]
        return tuple(batch)

    def record_decisions(self, decisions):
        self.recorded.extend(decisions)
        return len(decisions)


class LinkPendingTests(unittest.TestCase):
    def test_decides_every_pending_commitment_until_exhausted(self) -> None:
        pending = [
            PendingCommitment(
                "c1",
                {
                    links.FIELD_KEY: "O-10",
                    links.FIELD_HISTORY: "Contrato nº 098/2026 no valor",
                    links.FIELD_CREDITOR: "CONSTRUTORA E SERVIÇOS CHAGAS EIRELI",
                },
            ),
            PendingCommitment("c2", {links.FIELD_KEY: "E-5"}),
            PendingCommitment("c3", {links.FIELD_KEY: "O-11"}),
        ]
        repository = FakeRepository(pending)

        summary = link_pending(repository, max_commitments=10)

        self.assertEqual(summary["decided"], 3)
        self.assertEqual(
            summary["outcomes"],
            {
                "fora_do_escopo:extra_orcamentario": 1,
                "ligado": 1,
                "sem_citacao": 1,
            },
        )
        linked = repository.recorded[0][1]
        self.assertEqual(
            (linked.contract_record_key, linked.contract_portal_id), ("r1", "1520")
        )

    def test_respects_the_maximum(self) -> None:
        repository = FakeRepository(
            [PendingCommitment(f"c{n}", {links.FIELD_KEY: f"O-{n}"}) for n in range(5)]
        )

        summary = link_pending(repository, max_commitments=2)

        self.assertEqual(summary["decided"], 2)
        self.assertEqual(len(repository.pending), 3)


if __name__ == "__main__":
    unittest.main()
