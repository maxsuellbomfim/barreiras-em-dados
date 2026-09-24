from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from barreiras_collectors.connectors import municipal_expenses as expenses
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.persistence.models import (
    RepositoryPersistResult,
    StoredObject,
)
from barreiras_collectors.persistence.municipal_commitments import (
    MunicipalCommitmentsPersistenceService,
)

FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "sources"
    / "prefeitura-despesas-webrun"
)
GRID = (FIXTURES / "pagamentos-grid-2026-08-sample.txt").read_bytes()
RULE = (FIXTURES / "pagamentos-rule-2026-08.txt").read_bytes()
TODAY = date(2026, 9, 24)


class SessionTransport:
    def __init__(self) -> None:
        self.forms: list[dict[str, str]] = []
        self.urls: list[str] = []

    def reset_session(self) -> None:
        return None

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds, max_body_bytes
        self.urls.append(url)
        body = GRID if "/navigate.do?" in url else b"<html></html>"
        return HttpResponse(status=200, headers={}, body=body, final_url=url)

    def post(self, url, *, form, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds, max_body_bytes
        self.forms.append(dict(form))
        return HttpResponse(status=200, headers={}, body=RULE, final_url=url)


def fetch(transport: SessionTransport | None = None) -> expenses.MonthlyGrid:
    return expenses.fetch_monthly_grid(
        expenses.PAYMENTS,
        2026,
        8,
        today=TODAY,
        transport=transport or SessionTransport(),
    )


class PaymentGridTests(unittest.TestCase):
    def test_uses_payment_form_rule_and_its_own_parameters(self) -> None:
        transport = SessionTransport()

        result = fetch(transport)

        self.assertIn("formID=7910", transport.urls[0])
        self.assertIn("componentID=1082549", transport.urls[1])
        form = transport.forms[0]
        self.assertEqual(form["ruleName"], "TRP_TRANSP_PAGAMENTO_MODIFICAR_CONSULTA")
        self.assertEqual((form["P_7"], form["P_22"], form["P_6"]), ("P", "39", ""))
        self.assertEqual(result.stage, "pagamentos")
        self.assertEqual(result.endpoint_code, "webrun-pagamentos")

    def test_brings_commitment_key_payment_id_and_structured_contract(self) -> None:
        with_contract, without_contract = fetch().rows

        self.assertEqual(
            (
                with_contract["field1082596"],
                with_contract["field1082593"],
                with_contract["field1144926"],
            ),
            ("O-250790", "355674", "014/2025CM"),
        )
        self.assertEqual(without_contract["field1144926"], "")
        # O histórico do empenho não é duplicado no pagamento.
        self.assertNotIn("field1082591", with_contract)


class ObjectStore:
    def put_if_absent(self, *, object_key, body, content_type, expected_sha256):
        del content_type
        return StoredObject(object_key, expected_sha256, len(body), True)


class Repository:
    def __init__(self) -> None:
        self.batches = []

    def persist(self, batch):
        self.batches.append(batch)
        return RepositoryPersistResult("run", "artifact", len(batch.records), 0)


class PaymentPersistenceTests(unittest.TestCase):
    def test_payments_have_their_own_lane_and_record_type(self) -> None:
        repository = Repository()

        persisted = MunicipalCommitmentsPersistenceService(
            object_store=ObjectStore(), repository=repository
        ).persist(fetch())

        batch = repository.batches[0]
        self.assertTrue(
            persisted.object_key.startswith(
                "municipal-transparency/despesas-webrun/pagamentos/sha256/"
            )
        )
        self.assertEqual(
            {record.record_type for record in batch.records},
            {"municipal_payment_webrun"},
        )
        self.assertTrue(
            batch.records[0].source_record_key.startswith(
                "prefeitura-despesas-webrun:pagamento:O-250790:"
            )
        )
        self.assertEqual(batch.page.schema_name, "municipal-payments-webrun-grid")


if __name__ == "__main__":
    unittest.main()
