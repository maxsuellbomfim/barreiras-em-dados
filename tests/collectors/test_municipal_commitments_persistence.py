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
    previous_closed_month,
    resolve_months,
)
from barreiras_collectors.connectors import municipal_expenses as expenses
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.persistence.models import (
    ArtifactIntegrityError,
    RepositoryPersistResult,
    StoredObject,
)
from barreiras_collectors.persistence.municipal_commitments import (
    RECORD_TYPE,
    MunicipalCommitmentsPersistenceService,
)

FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "sources"
    / "prefeitura-despesas-webrun"
)
GRID = (FIXTURES / "empenhos-grid-2026-08-sample.txt").read_bytes()
RULE = (FIXTURES / "period-rule-2026-08.txt").read_bytes()
TODAY = date(2026, 9, 23)


class SessionTransport:
    def reset_session(self) -> None:
        return None

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds, max_body_bytes
        body = GRID if "/navigate.do?" in url else b"<html></html>"
        return HttpResponse(
            status=200,
            headers={
                "Content-Type": "text/html;charset=ISO-8859-1",
                "Set-Cookie": "JSESSIONID=segredo",
            },
            body=body,
            final_url=url,
        )

    def post(self, url, *, form, headers, timeout_seconds, max_body_bytes):
        del form, headers, timeout_seconds, max_body_bytes
        return HttpResponse(status=200, headers={}, body=RULE, final_url=url)


def fetch(year: int = 2026, month: int = 8) -> expenses.MonthlyCommitments:
    return expenses.fetch_monthly_commitments(
        year, month, today=TODAY, transport=SessionTransport()
    )


class ObjectStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_if_absent(self, *, object_key, body, content_type, expected_sha256):
        del content_type
        created = object_key not in self.objects
        self.objects.setdefault(object_key, body)
        return StoredObject(
            object_key=object_key,
            sha256=expected_sha256,
            byte_size=len(body),
            created=created,
        )


class Repository:
    def __init__(self) -> None:
        self.batches = []

    def persist(self, batch):
        self.batches.append(batch)
        return RepositoryPersistResult(
            collection_run_id="run",
            raw_artifact_id="artifact",
            inserted_records=len(batch.records),
            existing_records=0,
        )


class ControlRepository:
    def __init__(self) -> None:
        self.completed: dict | None = None
        self.failed: dict | None = None

    def start_controlled_run(self, **values):
        return "controlled-run"

    def complete_controlled_run(self, **values):
        self.completed = values

    def fail_controlled_run(self, **values):
        self.failed = values


def control(repository: ControlRepository, *, start: date, end: date):
    return CollectionControl(
        repository=repository,
        source_code=expenses.SOURCE_CODE,
        endpoint_code=expenses.ENDPOINT_CODE,
        idempotency_key="commitments-test:execution:0123456789abcdef",
        collector_version="test",
        partition_key=f"month:{start:%Y-%m}",
        period_start=start,
        period_end=end,
        execution_origin="manual",
    )


class PersistenceServiceTests(unittest.TestCase):
    def test_preserves_grid_and_one_record_per_official_key(self) -> None:
        store, repository = ObjectStore(), Repository()
        result = fetch()

        persisted = MunicipalCommitmentsPersistenceService(
            object_store=store, repository=repository
        ).persist(result)

        batch = repository.batches[0]
        self.assertEqual(
            persisted.object_key,
            "municipal-transparency/despesas-webrun/empenhos/sha256/"
            f"{result.grid_sha256[:2]}/{result.grid_sha256}.js",
        )
        self.assertEqual(store.objects[persisted.object_key], GRID)
        self.assertEqual(
            [(r.source_record_key, r.record_index) for r in batch.records],
            [
                ("prefeitura-despesas-webrun:empenho:O-250760", 0),
                ("prefeitura-despesas-webrun:empenho:E-57409", 2),
            ],
        )
        self.assertTrue(all(r.record_type == RECORD_TYPE for r in batch.records))
        self.assertEqual(batch.records[0].payload, result.rows[0])
        page = batch.page
        self.assertEqual(page.body_sha256, result.grid_sha256)
        self.assertEqual(page.window_start, "2026-08-01")
        self.assertEqual(page.window_end, "2026-08-31")
        self.assertIn(result.grid_sha256, page.idempotency_key)
        self.assertEqual(
            page.response_headers, {"content-type": "text/html;charset=ISO-8859-1"}
        )

    def test_rejects_body_that_does_not_match_hash(self) -> None:
        result = replace(fetch(), grid_body=GRID + b" ")

        with self.assertRaises(ArtifactIntegrityError):
            MunicipalCommitmentsPersistenceService(
                object_store=ObjectStore(), repository=Repository()
            ).persist(result)


class ControlledMonthTests(unittest.TestCase):
    def run_month(self, result):
        repository = ControlRepository()
        first, last = expenses.month_bounds(result.year, result.month)
        persisted = MunicipalCommitmentsPersistenceService(
            object_store=ObjectStore(), repository=Repository()
        ).persist(result)
        outcome = execute_controlled_month(
            control=control(repository, start=first, end=last),
            operation=lambda: (result, persisted),
        )
        return outcome, repository

    def test_month_since_2024_is_complete_with_unique_count(self) -> None:
        outcome, repository = self.run_month(fetch())

        self.assertIs(outcome.outcome, CollectionOutcome.COMPLETE)
        self.assertEqual(repository.completed["observed_records"], 2)
        self.assertEqual(repository.completed["metrics"]["repeated_rows"], 1)
        self.assertEqual(repository.completed["metrics"]["extra_budget_rows"], 1)
        self.assertIsNone(repository.completed["partial_failure"])

    def test_month_before_2024_is_partial_not_complete(self) -> None:
        result = replace(fetch(), year=2023, month=8, coverage="partial_x")

        outcome, repository = self.run_month(result)

        self.assertIs(outcome.outcome, CollectionOutcome.PARTIAL)
        failure = repository.completed["partial_failure"]
        self.assertEqual(failure["error_type"], "SourceHistoryUnavailable")
        self.assertFalse(failure["retryable"])

    def test_source_failure_is_recorded_not_empty(self) -> None:
        repository = ControlRepository()

        def operation():
            raise expenses.MunicipalExpensesError("A fonte recusou a consulta.")

        with self.assertRaises(expenses.MunicipalExpensesError):
            execute_controlled_month(
                control=control(
                    repository, start=date(2026, 8, 1), end=date(2026, 8, 31)
                ),
                operation=operation,
            )

        self.assertIsNone(repository.completed)
        self.assertEqual(repository.failed["error_type"], "MunicipalExpensesError")


class MonthWindowTests(unittest.TestCase):
    def test_defaults_to_previous_closed_month(self) -> None:
        self.assertEqual(
            resolve_months(
                month=None,
                start_month=None,
                end_month=None,
                max_months=1,
                today=TODAY,
            ),
            (date(2026, 8, 1),),
        )
        self.assertEqual(previous_closed_month(date(2027, 1, 5)), date(2026, 12, 1))

    def test_window_is_bounded_and_newest_first(self) -> None:
        self.assertEqual(
            resolve_months(
                month=None,
                start_month="2026-06",
                end_month="2026-08",
                max_months=3,
                today=TODAY,
            ),
            (date(2026, 8, 1), date(2026, 7, 1), date(2026, 6, 1)),
        )
        with self.assertRaises(ValueError):
            resolve_months(
                month=None,
                start_month="2026-01",
                end_month="2026-08",
                max_months=3,
                today=TODAY,
            )

    def test_rejects_open_month_and_before_2021(self) -> None:
        for month in ("2026-09", "2020-12"):
            with self.assertRaises(ValueError):
                resolve_months(
                    month=month,
                    start_month=None,
                    end_month=None,
                    max_months=1,
                    today=TODAY,
                )


if __name__ == "__main__":
    unittest.main()
