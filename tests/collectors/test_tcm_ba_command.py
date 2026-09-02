from __future__ import annotations

import json
import logging
import unittest
from datetime import date
from unittest.mock import patch

from barreiras_collectors.collection_control import CollectionOutcome
from barreiras_collectors.commands.collect_tcm_ba_monthly_catalog import (
    TcmBaMonthlyCollectionSummary,
    execute_controlled_tcm_month,
    execute_tcm_monthly_backfill,
    fetch_tcm_ba_monthly_catalog_with_contract_retry,
    main,
    month_range,
    previous_closed_month,
)
from barreiras_collectors.connectors.tcm_ba import TcmBaContractError, TcmBaError


class FakeControl:
    def __init__(self) -> None:
        self.completions = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        del exc_type, exc_value, traceback
        return False

    def complete(self, **values):
        self.completions.append(values)


def summary(*, year: int, month: int, documents: int = 1824):
    return TcmBaMonthlyCollectionSummary(
        year=year,
        month=month,
        documents=documents,
        artifacts=193,
        inserted_records=documents + 1,
        existing_records=0,
        artifact_hashes=("a" * 64,),
    )


class TcmBaMonthlyCatalogCommandTests(unittest.TestCase):
    def test_automatic_mode_targets_only_the_last_closed_month(self) -> None:
        self.assertEqual(previous_closed_month(date(2026, 9, 2)), (2026, 8))
        self.assertEqual(previous_closed_month(date(2026, 1, 1)), (2025, 12))

    def test_unpublished_month_is_recorded_as_blocked_without_false_empty(self) -> None:
        control = FakeControl()

        def unavailable_operation():
            raise TcmBaContractError(
                "Opção '08/2026' ausente no campo "
                "consultaPublicaTabPanel:consultaPublicaPCSearchForm:"
                "competenciaPCMes_input."
            )

        try:
            result = execute_controlled_tcm_month(
                control=control,
                operation=unavailable_operation,
            )
        except TcmBaContractError as error:
            self.fail(f"competência não publicada escapou como falha: {error}")

        self.assertIsNone(result)
        completion = control.completions[0]
        self.assertEqual(completion["outcome"], CollectionOutcome.BLOCKED)
        self.assertEqual(completion["observed_records"], 0)
        self.assertIn("não disponibilizou", completion["block_reason"])

    def test_retries_one_contract_failure_with_fresh_client_and_sanitized_warning(
        self,
    ) -> None:
        catalog = object()
        clients = []

        class FakeClient:
            def __init__(self, *, requests_per_minute, rate_limiter):
                clients.append((self, requests_per_minute, rate_limiter))

            def fetch_monthly_catalog(self, *, year, month):
                if len(clients) == 1:
                    raise TcmBaContractError("Página sem tabela; segredo=nao-vazar")
                return catalog

        logger = logging.getLogger("tcm-ba-contract-retry")
        with self.assertLogs(logger, level=logging.WARNING) as captured:
            with patch(
                "barreiras_collectors.commands.collect_tcm_ba_monthly_catalog.TcmBaPublicAccountsClient",
                FakeClient,
            ):
                result = fetch_tcm_ba_monthly_catalog_with_contract_retry(
                    year=2023,
                    month=8,
                    requests_per_minute=30,
                    logger=logger,
                )

        self.assertIs(result, catalog)
        self.assertEqual(len(clients), 2)
        self.assertIsNot(clients[0][0], clients[1][0])
        self.assertEqual(clients[0][1], 30)
        self.assertIs(clients[0][2], clients[1][2])
        event = json.loads(captured.records[0].getMessage())
        self.assertEqual(
            event,
            {
                "event": "collector_tcm_ba_contract_retry",
                "source": "tcm-ba",
                "competence": "08/2023",
                "next_attempt": 2,
                "error_type": "TcmBaContractError",
            },
        )

    def test_propagates_second_contract_failure_without_third_attempt(self) -> None:
        clients = []

        class FakeClient:
            def __init__(self, *, requests_per_minute, rate_limiter):
                clients.append((self, requests_per_minute, rate_limiter))

            def fetch_monthly_catalog(self, *, year, month):
                raise TcmBaContractError("contrato ausente")

        logger = logging.getLogger("tcm-ba-contract-retry-two-failures")
        with patch(
            "barreiras_collectors.commands.collect_tcm_ba_monthly_catalog.TcmBaPublicAccountsClient",
            FakeClient,
        ):
            with self.assertRaises(TcmBaContractError):
                fetch_tcm_ba_monthly_catalog_with_contract_retry(
                    year=2023,
                    month=8,
                    requests_per_minute=30,
                    logger=logger,
                )

        self.assertEqual(len(clients), 2)
        self.assertIs(clients[0][2], clients[1][2])

    def test_does_not_retry_valid_selector_without_requested_month(self) -> None:
        clients = []

        class FakeClient:
            def __init__(self, *, requests_per_minute, rate_limiter):
                clients.append((requests_per_minute, rate_limiter))

            def fetch_monthly_catalog(self, *, year, month):
                raise TcmBaContractError(
                    "Opção '08/2026' ausente no campo "
                    "consultaPublicaTabPanel:consultaPublicaPCSearchForm:"
                    "competenciaPCMes_input."
                )

        with patch(
            "barreiras_collectors.commands.collect_tcm_ba_monthly_catalog.TcmBaPublicAccountsClient",
            FakeClient,
        ):
            with self.assertRaises(TcmBaContractError):
                fetch_tcm_ba_monthly_catalog_with_contract_retry(
                    year=2026,
                    month=8,
                    requests_per_minute=30,
                    logger=logging.getLogger("tcm-ba-month-not-published"),
                )

        self.assertEqual(len(clients), 1)

    def test_does_not_retry_non_contract_tcm_error(self) -> None:
        clients = []

        class FakeClient:
            def __init__(self, *, requests_per_minute, rate_limiter):
                clients.append(self)

            def fetch_monthly_catalog(self, *, year, month):
                raise TcmBaError("HTTP 503")

        with patch(
            "barreiras_collectors.commands.collect_tcm_ba_monthly_catalog.TcmBaPublicAccountsClient",
            FakeClient,
        ):
            with self.assertRaises(TcmBaError):
                fetch_tcm_ba_monthly_catalog_with_contract_retry(
                    year=2023,
                    month=8,
                    requests_per_minute=30,
                    logger=logging.getLogger("tcm-ba-contract-no-retry"),
                )

        self.assertEqual(len(clients), 1)

    def test_rejects_requests_per_minute_above_endpoint_policy(self) -> None:
        with self.assertRaises(SystemExit):
            main(
                [
                    "--month-from",
                    "2023-08",
                    "--month-to",
                    "2023-08",
                    "--requests-per-minute",
                    "31",
                ]
            )

    def test_builds_inclusive_month_range(self) -> None:
        self.assertEqual(
            month_range("2023-11", "2024-02", collected_on=date(2026, 8, 24)),
            ((2023, 11), (2023, 12), (2024, 1), (2024, 2)),
        )
        with self.assertRaises(ValueError):
            month_range("2021-01", "2027-01", collected_on=date(2026, 8, 24))

    def test_closes_month_only_after_exact_catalog_is_persisted(self) -> None:
        control = FakeControl()
        result = execute_controlled_tcm_month(
            control=control,
            operation=lambda: summary(year=2023, month=4),
        )

        self.assertEqual(result.documents, 1824)
        completion = control.completions[0]
        self.assertEqual(completion["outcome"], CollectionOutcome.COMPLETE)
        self.assertEqual(completion["observed_records"], 1824)
        self.assertEqual(completion["checkpoint"]["competence"], "04/2023")
        self.assertEqual(completion["metrics"]["artifacts_preserved"], 193)

    def test_attempts_later_months_before_reporting_failures(self) -> None:
        attempted = []

        def operation_factory(year: int, month: int):
            def operation():
                attempted.append((year, month))
                if month == 4:
                    raise RuntimeError("fonte indisponível")
                return summary(year=year, month=month)

            return operation

        with self.assertRaisesRegex(RuntimeError, "2023-04"):
            execute_tcm_monthly_backfill(
                months=((2023, 4), (2023, 5)),
                control_factory=lambda _year, _month: FakeControl(),
                operation_factory=operation_factory,
                logger=logging.getLogger(__name__),
            )
        self.assertEqual(attempted, [(2023, 4), (2023, 5)])


if __name__ == "__main__":
    unittest.main()
