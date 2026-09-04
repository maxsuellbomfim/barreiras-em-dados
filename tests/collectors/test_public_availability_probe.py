from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from unittest.mock import patch

try:
    from barreiras_collectors.commands import probe_public_availability as probe
except ImportError:
    probe = None


class FakeControlRepository:
    def __init__(self) -> None:
        self.started: list[dict[str, object]] = []
        self.completed: list[dict[str, object]] = []
        self.failed: list[dict[str, object]] = []

    def start_controlled_run(self, **values: object) -> str:
        self.started.append(values)
        return "public-probe-run"

    def complete_controlled_run(self, **values: object) -> None:
        self.completed.append(values)

    def fail_controlled_run(self, **values: object) -> None:
        self.failed.append(values)


def health_body(*, status: str = "ok") -> bytes:
    return json.dumps(
        {
            "status": status,
            "service": "barreiras-em-dados-web",
            "stage": "pre-launch",
            "checkedAt": "2026-09-04T12:00:00.000Z",
            "checks": [
                {
                    "key": "diary",
                    "label": "Diário Oficial",
                    "status": "available",
                    "records": 4706,
                },
                {
                    "key": "finance",
                    "label": "Finanças municipais",
                    "status": "available",
                    "records": 60,
                },
                {
                    "key": "representatives",
                    "label": "Representação política",
                    "status": "available",
                    "records": 19,
                },
            ],
            "httpStatus": 200,
        },
        ensure_ascii=False,
    ).encode("utf-8")


class PublicAvailabilityProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertIsNotNone(probe, "probe público ainda não implementado")
        self.repository = FakeControlRepository()
        self.now = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
        self.environment = {
            "GITHUB_REPOSITORY": "maxsuellbomfim/barreiras-em-dados",
            "GITHUB_WORKFLOW": "Verificações",
            "GITHUB_RUN_ID": "987654",
            "GITHUB_RUN_ATTEMPT": "1",
        }

    def response_for(self, url: str):
        self.assertEqual(len(self.repository.started), 1)
        if url.endswith("/api/health"):
            return probe.ProbeResponse(
                status_code=200,
                content_type="application/json; charset=utf-8",
                body=health_body(),
                latency_ms=125,
            )
        return probe.ProbeResponse(
            status_code=200,
            content_type="text/html; charset=utf-8",
            body=b"<!doctype html><html><title>Barreiras 360</title></html>",
            latency_ms=80,
        )

    def run_probe(self, fetcher=None) -> int:
        return probe.run_public_availability_probe(
            repository=self.repository,
            fetcher=fetcher or self.response_for,
            now=self.now,
            base_url="https://barreiras-em-dados.vercel.app",
            execution_origin="github_actions",
            workflow_event="schedule",
            environment=self.environment,
        )

    def test_starts_control_before_checking_all_critical_routes(self) -> None:
        result = self.run_probe()

        self.assertEqual(result, 0)
        self.assertEqual(len(self.repository.started), 1)
        self.assertEqual(self.repository.failed, [])
        completed = self.repository.completed[0]
        self.assertEqual(completed["outcome"], "complete")
        self.assertEqual(completed["observed_records"], 8)
        self.assertEqual(
            completed["checkpoint"]["target_slugs"],
            [
                "home",
                "status",
                "official-diary",
                "finance",
                "procurement",
                "resources",
                "representatives",
                "health-api",
            ],
        )
        self.assertEqual(
            completed["metrics"],
            {
                "workflow_event": "schedule",
                "target_count": 8,
                "targets_checked": 8,
                "http_5xx_count": 0,
                "http_non_2xx_count": 0,
                "transport_failures": 0,
                "contract_failures": 0,
                "health_status": "ok",
                "maximum_latency_ms": 125,
            },
        )
        self.assertNotIn("body", json.dumps(completed, default=str).lower())

    def test_a_5xx_is_persisted_as_partial_and_fails_the_job(self) -> None:
        def fetcher(url: str):
            if url.endswith("/recursos"):
                return probe.ProbeResponse(
                    status_code=500,
                    content_type="text/html",
                    body=b"internal error token=must-not-be-persisted",
                    latency_ms=220,
                )
            return self.response_for(url)

        result = self.run_probe(fetcher)

        self.assertEqual(result, 1)
        completed = self.repository.completed[0]
        self.assertEqual(completed["outcome"], "partial")
        self.assertEqual(completed["metrics"]["http_5xx_count"], 1)
        self.assertEqual(completed["metrics"]["http_non_2xx_count"], 1)
        self.assertEqual(
            completed["partial_failure"]["error_type"],
            "PublicAvailabilityGateFailure",
        )
        self.assertNotIn(
            "must-not-be-persisted",
            json.dumps(completed, default=str),
        )

    def test_invalid_health_contract_fails_closed_without_calling_it_zero(self) -> None:
        def fetcher(url: str):
            if url.endswith("/api/health"):
                return probe.ProbeResponse(
                    status_code=200,
                    content_type="application/json",
                    body=b'{"status":"ok","checks":[]}',
                    latency_ms=90,
                )
            return self.response_for(url)

        result = self.run_probe(fetcher)

        self.assertEqual(result, 1)
        metrics = self.repository.completed[0]["metrics"]
        self.assertEqual(metrics["http_5xx_count"], 0)
        self.assertEqual(metrics["contract_failures"], 1)
        self.assertIsNone(metrics["health_status"])

    def test_transport_failure_is_distinct_from_an_http_response(self) -> None:
        def fetcher(url: str):
            if url.endswith("/licitacoes"):
                raise TimeoutError("password=must-not-be-persisted")
            return self.response_for(url)

        result = self.run_probe(fetcher)

        self.assertEqual(result, 1)
        metrics = self.repository.completed[0]["metrics"]
        self.assertEqual(metrics["transport_failures"], 1)
        self.assertEqual(metrics["http_non_2xx_count"], 0)
        self.assertNotIn(
            "must-not-be-persisted",
            json.dumps(self.repository.completed[0], default=str),
        )

    def test_rejects_unapproved_host_before_any_request_or_run(self) -> None:
        fetched: list[str] = []

        with self.assertRaisesRegex(ValueError, "host público autorizado"):
            probe.run_public_availability_probe(
                repository=self.repository,
                fetcher=lambda url: fetched.append(url),
                now=self.now,
                base_url="https://example.org",
                execution_origin="github_actions",
                workflow_event="schedule",
                environment=self.environment,
            )

        self.assertEqual(fetched, [])
        self.assertEqual(self.repository.started, [])

    def test_rejects_redirect_outside_the_public_host(self) -> None:
        class RedirectedResponse:
            status = 200

            def __init__(self) -> None:
                self.headers = {"Content-Type": "text/html"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def geturl(self) -> str:
                return "https://example.org/captured"

            def read(self, _limit: int) -> bytes:
                return b"<!doctype html><html>Barreiras 360</html>"

        with patch.object(probe, "urlopen", return_value=RedirectedResponse()):
            with self.assertRaisesRegex(ValueError, "redirecionou"):
                probe._fetch_response(
                    "https://barreiras-em-dados.vercel.app/diario",
                    timeout_seconds=5,
                )


if __name__ == "__main__":
    unittest.main()
