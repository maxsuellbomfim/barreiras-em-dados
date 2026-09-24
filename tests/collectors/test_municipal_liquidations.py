from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

from barreiras_collectors.collection_control import (
    CollectionControl,
    CollectionOutcome,
)
from barreiras_collectors.commands.collect_municipal_commitments import (
    execute_controlled_month,
)
from barreiras_collectors.connectors import municipal_expenses as expenses
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.persistence.models import (
    RepositoryPersistResult,
    StoredObject,
)
from barreiras_collectors.persistence.municipal_commitments import (
    MunicipalCommitmentsPersistenceService,
    stage_records,
)

FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "sources"
    / "prefeitura-despesas-webrun"
)
GRID = (FIXTURES / "liquidacoes-grid-2026-08-sample.txt").read_bytes()
RULE = (FIXTURES / "liquidacoes-rule-2026-08.txt").read_bytes()
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


def fetch() -> expenses.MonthlyGrid:
    return expenses.fetch_monthly_grid(
        expenses.LIQUIDATIONS, 2026, 8, today=TODAY, transport=SessionTransport()
    )


class LiquidationGridTests(unittest.TestCase):
    def test_uses_liquidation_form_rule_and_grid(self) -> None:
        transport = SessionTransport()

        result = expenses.fetch_monthly_grid(
            expenses.LIQUIDATIONS, 2026, 8, today=TODAY, transport=transport
        )

        self.assertIn("formID=7907", transport.urls[0])
        self.assertIn("componentID=1089430", transport.urls[1])
        form = transport.forms[0]
        self.assertEqual(form["ruleName"], "TRP_TRANSP_LIQUIDAC_MODIFICAR_CONSULTA")
        self.assertEqual(
            (form["P_0"], form["P_1"], form["P_6"]), ("01/08/2026", "31/08/2026", "P")
        )
        self.assertEqual(result.stage, "liquidacoes")
        self.assertEqual(result.endpoint_code, "webrun-liquidacoes")
        self.assertEqual(result.declared_total, 2)

    def test_brings_the_commitment_key_from_the_hidden_detail_fields(self) -> None:
        rows = fetch().rows

        self.assertEqual(
            [(row["field1089487"], row["field1089486"]) for row in rows],
            [("O-250959", "1  245"), ("O-250790", "10  16")],
        )

    def test_same_commitment_may_have_several_liquidations(self) -> None:
        first, second = fetch().rows
        another = {**second, "field1089487": first["field1089487"]}

        repeated = expenses.validate_grid_rows(
            expenses.LIQUIDATIONS,
            (first, another, dict(first)),
            first=date(2026, 8, 1),
            last=date(2026, 8, 31),
        )

        self.assertEqual(repeated, 1)

    def test_commitments_keep_one_row_per_key(self) -> None:
        with self.assertRaises(expenses.MunicipalExpensesContractError):
            expenses.validate_grid_rows(
                expenses.COMMITMENTS,
                (
                    {
                        expenses.FIELD_DATE: "01/08/2026",
                        expenses.FIELD_KEY: "O-1",
                        expenses.FIELD_NUMBER: "1/1",
                        expenses.FIELD_AMOUNT: "1,00",
                        expenses.FIELD_CREDITOR: "X",
                    },
                    {
                        expenses.FIELD_DATE: "01/08/2026",
                        expenses.FIELD_KEY: "O-1",
                        expenses.FIELD_NUMBER: "1/1",
                        expenses.FIELD_AMOUNT: "2,00",
                        expenses.FIELD_CREDITOR: "X",
                    },
                ),
                first=date(2026, 8, 1),
                last=date(2026, 8, 31),
            )


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


class LiquidationPersistenceTests(unittest.TestCase):
    def test_one_record_per_distinct_row_in_its_own_lane(self) -> None:
        repository = Repository()
        result = fetch()

        persisted = MunicipalCommitmentsPersistenceService(
            object_store=ObjectStore(), repository=repository
        ).persist(result)

        batch = repository.batches[0]
        self.assertTrue(
            persisted.object_key.startswith(
                "municipal-transparency/despesas-webrun/liquidacoes/sha256/"
            )
        )
        self.assertEqual(batch.page.schema_name, "municipal-liquidations-webrun-grid")
        self.assertTrue(
            batch.page.idempotency_key.startswith("municipal-liquidations:")
        )
        self.assertEqual(
            {record.record_type for record in batch.records},
            {"municipal_liquidation_webrun"},
        )
        self.assertTrue(
            batch.records[0].source_record_key.startswith(
                "prefeitura-despesas-webrun:liquidacao:O-250959:"
            )
        )

    def test_identical_repeats_are_not_duplicated_but_distinct_rows_are_kept(
        self,
    ) -> None:
        result = fetch()
        first, second = result.rows
        repeated = replace(
            result,
            rows=(first, {**second, "field1089487": first["field1089487"]}, first),
        )

        self.assertEqual(len(stage_records(repeated)), 2)


class ControlRepository:
    def __init__(self) -> None:
        self.completed = None

    def start_controlled_run(self, **values):
        return "run"

    def complete_controlled_run(self, **values):
        self.completed = values

    def fail_controlled_run(self, **values):
        raise AssertionError(values)


class ControlledLiquidationMonthTests(unittest.TestCase):
    def test_liquidation_month_is_complete_with_stage_metrics(self) -> None:
        repository = ControlRepository()
        result = fetch()
        persisted = MunicipalCommitmentsPersistenceService(
            object_store=ObjectStore(), repository=Repository()
        ).persist(result)
        control = CollectionControl(
            repository=repository,
            source_code=expenses.SOURCE_CODE,
            endpoint_code="webrun-liquidacoes",
            idempotency_key="liquidacoes-test:execution:0123456789",
            collector_version="test",
            partition_key="month:2026-08",
            period_start=date(2026, 8, 1),
            period_end=date(2026, 8, 31),
            execution_origin="manual",
        )

        outcome = execute_controlled_month(
            control=control, operation=lambda: (result, persisted)
        )

        self.assertEqual(
            (outcome.stage, outcome.outcome),
            ("liquidacoes", CollectionOutcome.COMPLETE),
        )
        self.assertEqual(repository.completed["observed_records"], 2)
        self.assertEqual(repository.completed["metrics"]["stage"], "liquidacoes")


if __name__ == "__main__":
    unittest.main()
