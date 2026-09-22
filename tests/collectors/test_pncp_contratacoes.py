from __future__ import annotations

import json
import logging
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from barreiras_collectors.commands import collect_pncp_contratacoes as command
from barreiras_collectors.commands.collect_pncp_contratacoes import (
    PncpContratacoesCollectionSummary,
    _collect_window,
    execute_controlled_pncp_contratacoes,
    resolve_window,
)
from barreiras_collectors.connectors.pncp import (
    PncpError,
    fetch_contratacoes_page,
)
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.resilience import RetryPolicy


class DiscoveryPacingTests(unittest.TestCase):
    def test_every_http_attempt_acquires_limiter(self):
        events = []
        limiter = Mock()
        limiter.acquire.side_effect = lambda: events.append("acquire")
        transport = Mock()

        def request(*args, **kwargs):
            events.append("request")
            return HttpResponse(503, {}, b"", args[0])

        transport.get.side_effect = request
        with self.assertRaises(PncpError):
            fetch_contratacoes_page(
                since="20240315",
                until="20240315",
                modalidade=1,
                pagina=1,
                transport=transport,
                rate_limiter=limiter,
                retry_policy=RetryPolicy(max_attempts=2),
                sleep=lambda _: None,
            )
        self.assertEqual(events, ["acquire", "request", "acquire", "request"])

    def test_window_shares_ten_per_minute_limiter_across_pages_and_modalities(self):
        page = SimpleNamespace(total_paginas=2)
        service = Mock()
        service.persist.return_value = SimpleNamespace(
            inserted_records=1, existing_records=0
        )
        with (
            patch.object(command, "PacedRateLimiter") as factory,
            patch.object(command, "CONTRATACAO_MODALIDADES", (1, 2)),
            patch.object(
                command, "fetch_contratacoes_page", side_effect=[page, page, None]
            ) as fetch,
        ):
            summary = _collect_window(
                service=service,
                since="20240315",
                until="20240315",
                logger=logging.getLogger(__name__),
            )
        factory.assert_called_once_with(10)
        self.assertEqual(fetch.call_count, 3)
        self.assertTrue(
            all(
                call.kwargs["rate_limiter"] is factory.return_value
                for call in fetch.call_args_list
            )
        )
        self.assertEqual(summary.pages, 2)


class OneShotTransport:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.body = body
        self.urls: list[str] = []

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds, max_body_bytes
        self.urls.append(url)
        return HttpResponse(
            status=self.status,
            headers={},
            body=self.body,
            final_url=url,
        )


class SequenceTransport:
    def __init__(self, responses: list[HttpResponse | BaseException]) -> None:
        self.responses = list(responses)
        self.calls = 0

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds, max_body_bytes
        self.calls += 1
        result = self.responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        return HttpResponse(
            status=result.status,
            headers=result.headers,
            body=result.body,
            final_url=url,
        )


def fetch(status: int, body: bytes):
    return fetch_contratacoes_page(
        since="20260101",
        until="20260131",
        modalidade=6,
        pagina=1,
        transport=OneShotTransport(status, body),
        retry_policy=RetryPolicy(max_attempts=2),
        sleep=lambda _s: None,
    )


class ContratacoesFetchTests(unittest.TestCase):
    def test_exhausted_rate_limit_defers_other_modalities(self):
        from barreiras_collectors.connectors.pncp import PncpRateLimitError

        transport = OneShotTransport(429, b"rate limited")
        sleeps = []
        with self.assertRaises(PncpRateLimitError):
            fetch_contratacoes_page(
                since="20240315",
                until="20240413",
                modalidade=7,
                pagina=1,
                transport=transport,
                retry_policy=RetryPolicy(max_attempts=2),
                sleep=sleeps.append,
            )
        self.assertEqual(len(transport.urls), 2)
        self.assertEqual(len(sleeps), 1)
        with (
            patch.object(command, "CONTRATACAO_MODALIDADES", (1, 7, 8)),
            patch.object(
                command,
                "fetch_contratacoes_page",
                side_effect=[None, PncpRateLimitError("limited")],
            ) as request,
        ):
            summary = _collect_window(
                service=Mock(),
                since="20240315",
                until="20240413",
                logger=logging.getLogger(__name__),
            )
        self.assertEqual(request.call_count, 2)
        self.assertEqual(summary.failed_modalities, (7,))
        self.assertEqual(summary.deferred_modalities, (8,))

    def test_page_with_items_preserves_bytes_and_cursor(self) -> None:
        body = json.dumps(
            {
                "totalRegistros": 23,
                "totalPaginas": 3,
                "data": [
                    {
                        "numeroControlePNCP": "13654405000195-1-000001/2026",
                        "objetoCompra": "Fornecimento de alimentos",
                    }
                ],
            }
        ).encode()

        page = fetch(200, body)

        assert page is not None
        self.assertEqual(page.total_paginas, 3)
        self.assertEqual(len(page.items), 1)
        self.assertEqual(page.cursor["modalidade"], 6)
        self.assertEqual(page.raw_body, body)

    def test_http_200_with_error_root_is_failure(self) -> None:
        body = json.dumps({"error": "parametro invalido"}).encode()

        with self.assertRaises(PncpError):
            fetch(200, body)

    def test_204_and_empty_data_mean_no_content(self) -> None:
        self.assertIsNone(fetch(204, b""))
        self.assertIsNone(
            fetch(
                200,
                json.dumps(
                    {"totalRegistros": 0, "totalPaginas": 0, "data": []}
                ).encode(),
            )
        )

    def test_non_json_is_explicit_failure(self) -> None:
        with self.assertRaises(PncpError):
            fetch(200, b"<html>bloqueio</html>")

    def test_timeout_is_retried_before_success(self) -> None:
        body = json.dumps(
            {
                "totalRegistros": 1,
                "totalPaginas": 1,
                "data": [{"numeroControlePNCP": "controle"}],
            }
        ).encode()
        transport = SequenceTransport(
            [
                TimeoutError("tempo esgotado"),
                HttpResponse(200, {}, body, "unused"),
            ]
        )
        sleeps: list[float] = []

        page = fetch_contratacoes_page(
            since="20260101",
            until="20260131",
            modalidade=6,
            pagina=1,
            transport=transport,
            retry_policy=RetryPolicy(
                max_attempts=2,
                base_delay_seconds=1,
                max_delay_seconds=2,
            ),
            sleep=sleeps.append,
        )

        assert page is not None
        self.assertEqual(page.attempts, 2)
        self.assertEqual(transport.calls, 2)
        self.assertEqual(sleeps, [0.5])

    def test_respects_retry_after_for_rate_limited_response(self) -> None:
        body = json.dumps(
            {
                "totalRegistros": 1,
                "totalPaginas": 1,
                "data": [{"numeroControlePNCP": "controle"}],
            }
        ).encode()
        transport = SequenceTransport(
            [
                HttpResponse(429, {"Retry-After": "7"}, b"rate limited", "unused"),
                HttpResponse(200, {}, body, "unused"),
            ]
        )
        sleeps: list[float] = []

        page = fetch_contratacoes_page(
            since="20260101",
            until="20260131",
            modalidade=6,
            pagina=1,
            transport=transport,
            retry_policy=RetryPolicy(
                max_attempts=2,
                base_delay_seconds=1,
                max_delay_seconds=2,
            ),
            sleep=sleeps.append,
        )

        assert page is not None
        self.assertEqual(page.attempts, 2)
        self.assertEqual(transport.calls, 2)
        self.assertEqual(sleeps, [7.0])

    def test_uses_conservative_floor_when_rate_limit_omits_retry_after(self) -> None:
        body = json.dumps(
            {
                "totalRegistros": 1,
                "totalPaginas": 1,
                "data": [{"numeroControlePNCP": "controle"}],
            }
        ).encode()
        transport = SequenceTransport(
            [
                HttpResponse(429, {}, b"rate limited", "unused"),
                HttpResponse(200, {}, body, "unused"),
            ]
        )
        sleeps: list[float] = []

        page = fetch_contratacoes_page(
            since="20260101",
            until="20260131",
            modalidade=6,
            pagina=1,
            transport=transport,
            retry_policy=RetryPolicy(max_attempts=2),
            sleep=sleeps.append,
        )

        assert page is not None
        self.assertEqual(sleeps, [10.0])

    def test_persistent_transport_failure_raises_domain_error(self) -> None:
        transport = SequenceTransport([TimeoutError("um"), TimeoutError("dois")])

        with self.assertRaises(PncpError) as captured:
            fetch_contratacoes_page(
                since="20260101",
                until="20260131",
                modalidade=6,
                pagina=1,
                transport=transport,
                retry_policy=RetryPolicy(max_attempts=2),
                sleep=lambda _seconds: None,
            )

        self.assertIn("indisponível", str(captured.exception))
        self.assertEqual(transport.calls, 2)


class WindowTests(unittest.TestCase):
    def test_explicit_window_is_formatted_for_the_api(self) -> None:
        self.assertEqual(
            resolve_window("2026-01-01", "2026-01-31"),
            ("20260101", "20260131"),
        )

    def test_partial_or_oversized_window_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            resolve_window("2026-01-01", "")
        with self.assertRaises(ValueError):
            resolve_window("2026-01-01", "2026-03-15")


class ControlledPncpContratacoesTests(unittest.TestCase):
    def test_truncated_modality_marks_window_partial(self) -> None:
        completed: dict[str, object] = {}

        class ControlProbe:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                del exc_type, exc_value, traceback
                return False

            def complete(self, **values):
                completed.update(values)

        execute_controlled_pncp_contratacoes(
            control=ControlProbe(),  # type: ignore[arg-type]
            operation=lambda: PncpContratacoesCollectionSummary(
                pages=30,
                inserted_records=450,
                existing_records=0,
                truncated_modalities=(6,),
            ),
        )

        self.assertEqual(completed["outcome"].value, "partial")
        self.assertEqual(
            completed["checkpoint"],
            {
                "truncated_modalities": [6],
                "failed_modalities": [],
                "deferred_modalities": [],
            },
        )

    def test_failed_modality_preserves_other_results_and_marks_partial(self) -> None:
        requested: list[int] = []

        def fetch_page(**values):
            modalidade = values["modalidade"]
            requested.append(modalidade)
            if modalidade == 2:
                raise PncpError("fonte indisponivel")
            return SimpleNamespace(total_paginas=1)

        class ServiceProbe:
            def persist(self, _page):
                return SimpleNamespace(inserted_records=1, existing_records=0)

        with (
            patch.object(command, "CONTRATACAO_MODALIDADES", (1, 2, 3)),
            patch.object(command, "fetch_contratacoes_page", side_effect=fetch_page),
        ):
            summary = _collect_window(
                service=ServiceProbe(),  # type: ignore[arg-type]
                since="20260101",
                until="20260131",
                logger=logging.getLogger("test-pncp-partial"),
            )

        self.assertEqual(requested, [1, 2, 3])
        self.assertEqual(summary.pages, 2)
        self.assertEqual(summary.inserted_records, 2)
        self.assertEqual(summary.failed_modalities, (2,))
        self.assertEqual(summary.deferred_modalities, ())
        self.assertEqual(summary.outcome.value, "partial")

    def test_consecutive_failures_defer_remaining_modalities(self) -> None:
        requested: list[int] = []

        def fetch_page(**values):
            requested.append(values["modalidade"])
            raise PncpError("fonte indisponivel")

        class ServiceProbe:
            def persist(self, _page):
                raise AssertionError("nenhuma pagina deveria ser persistida")

        with (
            patch.object(command, "CONTRATACAO_MODALIDADES", (1, 2, 3, 4)),
            patch.object(command, "fetch_contratacoes_page", side_effect=fetch_page),
        ):
            summary = _collect_window(
                service=ServiceProbe(),  # type: ignore[arg-type]
                since="20260101",
                until="20260131",
                logger=logging.getLogger("test-pncp-circuit"),
            )

        self.assertEqual(requested, [1, 2])
        self.assertEqual(summary.failed_modalities, (1, 2))
        self.assertEqual(summary.deferred_modalities, (3, 4))
        self.assertEqual(summary.outcome.value, "partial")

    def test_control_starts_before_external_setup(self) -> None:
        events: list[str] = []

        class ControlProbe:
            def __enter__(self):
                events.append("started")
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                del exc_type, exc_value, traceback
                events.append("closed")
                return False

            def complete(self, **values):
                events.append(f"completed:{values['outcome'].value}")

        def operation() -> PncpContratacoesCollectionSummary:
            self.assertEqual(events, ["started"])
            events.append("external-setup")
            return PncpContratacoesCollectionSummary(
                pages=0,
                inserted_records=0,
                existing_records=0,
                truncated_modalities=(),
            )

        execute_controlled_pncp_contratacoes(
            control=ControlProbe(),  # type: ignore[arg-type]
            operation=operation,
        )

        self.assertEqual(
            events,
            ["started", "external-setup", "completed:empty", "closed"],
        )


class PncpContratacoesMainExitTests(unittest.TestCase):
    def run_main(self, summary, *, horizon_reached=False):
        events = []
        repository = SimpleNamespace(
            start_controlled_run=Mock(
                side_effect=lambda **_values: events.append("started") or "run-test"
            ),
            complete_controlled_run=Mock(
                side_effect=lambda **_values: events.append("checkpoint")
            ),
            fail_controlled_run=Mock(),
            pncp_backfill_anchor=Mock(return_value=command.BACKFILL_HORIZON),
        )
        with (
            patch.object(
                command.CollectorSettings,
                "from_env",
                return_value=SimpleNamespace(log_level="INFO"),
            ),
            patch.object(
                command.PersistenceSettings,
                "from_env",
                return_value=SimpleNamespace(
                    mode="postgres-supabase", database_url="test-dsn"
                ),
            ),
            patch.object(
                command.PostgresCollectionRepository,
                "from_dsn",
                return_value=repository,
            ),
            patch.object(command.logging, "basicConfig"),
            patch.object(
                command,
                "_build_cloud_service",
                side_effect=lambda **_values: events.append("setup"),
            ) as cloud,
            patch.object(
                command,
                "_collect_window",
                side_effect=lambda **_values: events.append("collected") or summary,
            ) as collect,
            patch.object(
                command,
                "log_event",
                side_effect=lambda *_args, **_values: events.append("logged"),
            ) as log,
        ):
            result = command.main(
                ["--backfill"]
                if horizon_reached
                else ["--since", "2026-09-07", "--until", "2026-09-14"]
            )
            events.append("returned")
        return result, repository, events, log, cloud, collect

    def test_partial_exits_nonzero_after_recording_checkpoint_and_summary(self):
        for partial_fields in (
            {"failed_modalities": (1, 2), "deferred_modalities": tuple(range(3, 14))},
            {"failed_modalities": (2,)},
            {"deferred_modalities": (3,)},
            {"truncated_modalities": (6,)},
        ):
            with self.subTest(partial_fields=partial_fields):
                fields = {"truncated_modalities": (), **partial_fields}
                summary = PncpContratacoesCollectionSummary(
                    pages=0, inserted_records=0, existing_records=0, **fields
                )
                result, repository, events, log, _, _ = self.run_main(summary)
                self.assertEqual(
                    events,
                    [
                        "started",
                        "setup",
                        "collected",
                        "checkpoint",
                        "logged",
                        "returned",
                    ],
                )
                values = repository.complete_controlled_run.call_args.kwargs
                self.assertEqual(
                    values["partition_key"], "published:2026-09-07:2026-09-14"
                )
                self.assertEqual(values["outcome"], "partial")
                self.assertEqual(
                    values["checkpoint"],
                    {
                        "truncated_modalities": list(summary.truncated_modalities),
                        "failed_modalities": list(summary.failed_modalities),
                        "deferred_modalities": list(summary.deferred_modalities),
                    },
                )
                self.assertEqual(values["observed_records"], 0)
                self.assertEqual(log.call_args.kwargs["coverage_status"], "partial")
                repository.fail_controlled_run.assert_not_called()
                self.assertNotEqual(result, 0)

    def test_partial_keeps_preserved_records_and_still_exits_nonzero(self):
        summary = PncpContratacoesCollectionSummary(
            pages=2,
            inserted_records=3,
            existing_records=4,
            truncated_modalities=(),
            failed_modalities=(2,),
        )
        result, repository, _, log, _, _ = self.run_main(summary)
        self.assertEqual(
            repository.complete_controlled_run.call_args.kwargs["observed_records"], 7
        )
        self.assertEqual(log.call_args.kwargs["coverage_status"], "partial")
        self.assertNotEqual(result, 0)

    def test_complete_and_officially_empty_keep_zero_exit(self):
        for records, expected in ((2, "complete"), (0, "empty")):
            with self.subTest(expected=expected):
                summary = PncpContratacoesCollectionSummary(
                    pages=int(records > 0),
                    inserted_records=records,
                    existing_records=0,
                    truncated_modalities=(),
                )
                result, repository, _, log, _, _ = self.run_main(summary)
                self.assertEqual(
                    repository.complete_controlled_run.call_args.kwargs["outcome"],
                    expected,
                )
                self.assertEqual(log.call_args.kwargs["coverage_status"], expected)
                self.assertEqual(result, 0)

    def test_backfill_horizon_noop_does_not_open_collection_and_returns_zero(self):
        result, repository, events, log, cloud, collect = self.run_main(
            None,
            horizon_reached=True,
        )
        self.assertEqual(result, 0)
        self.assertEqual(events, ["logged", "returned"])
        self.assertEqual(log.call_args.args[2], "collector_pncp_backfill_complete")
        repository.start_controlled_run.assert_not_called()
        repository.complete_controlled_run.assert_not_called()
        cloud.assert_not_called()
        collect.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class BackfillWindowTests(unittest.TestCase):
    def test_walks_back_thirty_days_from_anchor(self) -> None:
        from datetime import date

        from barreiras_collectors.commands.collect_pncp_contratacoes import (
            resolve_backfill_window,
        )

        window = resolve_backfill_window(
            anchor=date(2026, 7, 1),
            today=date(2026, 8, 1),
        )

        self.assertEqual(window, ("20260601", "20260630"))

    def test_first_run_starts_from_today(self) -> None:
        from datetime import date

        from barreiras_collectors.commands.collect_pncp_contratacoes import (
            resolve_backfill_window,
        )

        window = resolve_backfill_window(
            anchor=None,
            today=date(2026, 8, 1),
        )

        assert window is not None
        self.assertEqual(window[1], "20260801")

    def test_horizon_reached_is_explicit_none(self) -> None:
        from datetime import date

        from barreiras_collectors.commands.collect_pncp_contratacoes import (
            resolve_backfill_window,
        )

        self.assertIsNone(
            resolve_backfill_window(
                anchor=date(2021, 7, 1),
                today=date(2026, 8, 1),
            )
        )

    def test_last_window_clamps_at_horizon(self) -> None:
        from datetime import date

        from barreiras_collectors.commands.collect_pncp_contratacoes import (
            resolve_backfill_window,
        )

        window = resolve_backfill_window(
            anchor=date(2021, 7, 10),
            today=date(2026, 8, 1),
        )

        self.assertEqual(window, ("20210701", "20210709"))
