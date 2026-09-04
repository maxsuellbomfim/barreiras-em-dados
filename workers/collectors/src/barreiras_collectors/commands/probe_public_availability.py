"""Sonda rotas públicas críticas sem confundir amostra com tráfego integral."""

from __future__ import annotations

import argparse
import json
import logging
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.error import HTTPError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from ..collection_control import (
    CollectionControl,
    CollectionOutcome,
    PartialCollectionFailure,
    build_execution_idempotency_key,
)
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..settings import PostgresSettings

SOURCE_CODE = "barreiras-360"
ENDPOINT_CODE = "critical-public-pages"
COLLECTOR_VERSION = "public-availability-probe/1.0.0"
PARSER_VERSION = "public-availability-contract/1.0.0"
EXECUTION_NAMESPACE = "public-availability"
MUNICIPAL_TIMEZONE = ZoneInfo("America/Bahia")
APPROVED_HOSTS = frozenset({"barreiras-em-dados.vercel.app"})
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ProbeTarget:
    slug: str
    path: str
    content_kind: str


TARGETS = (
    ProbeTarget("home", "/", "html"),
    ProbeTarget("status", "/estado", "html"),
    ProbeTarget("official-diary", "/diario", "html"),
    ProbeTarget("finance", "/financas", "html"),
    ProbeTarget("procurement", "/licitacoes", "html"),
    ProbeTarget("resources", "/recursos", "html"),
    ProbeTarget("representatives", "/representantes", "html"),
    ProbeTarget("health-api", "/api/health", "health_json"),
)


@dataclass(frozen=True, slots=True)
class ProbeResponse:
    status_code: int
    content_type: str
    body: bytes
    latency_ms: int


@dataclass(frozen=True, slots=True)
class ProbeSummary:
    targets_checked: int
    valid_targets: int
    http_5xx_count: int
    http_non_2xx_count: int
    transport_failures: int
    contract_failures: int
    health_status: str | None
    maximum_latency_ms: int

    @property
    def passed(self) -> bool:
        return (
            self.targets_checked == len(TARGETS)
            and self.valid_targets == len(TARGETS)
            and self.http_non_2xx_count == 0
            and self.transport_failures == 0
            and self.contract_failures == 0
        )


def _validate_base_url(base_url: str) -> str:
    parsed = urlparse(base_url.strip())
    if (
        parsed.scheme != "https"
        or parsed.hostname not in APPROVED_HOSTS
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.path not in ("", "/")
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("PUBLIC_SITE_BASE_URL deve usar o host público autorizado.")
    return f"https://{parsed.hostname}"


def _is_approved_target_url(url: str) -> bool:
    parsed = urlparse(url)
    return bool(
        parsed.scheme == "https"
        and parsed.hostname in APPROVED_HOSTS
        and not parsed.username
        and not parsed.password
        and parsed.port in (None, 443)
    )


def _valid_health_contract(response: ProbeResponse) -> tuple[bool, str | None]:
    if not response.content_type.lower().startswith("application/json"):
        return False, None
    try:
        payload = json.loads(response.body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False, None
    if not isinstance(payload, dict):
        return False, None
    status = payload.get("status")
    checks = payload.get("checks")
    if (
        payload.get("service") != "barreiras-em-dados-web"
        or status not in {"ok", "degraded"}
        or payload.get("httpStatus") != response.status_code
        or not isinstance(checks, list)
        or len(checks) != 3
    ):
        return False, None
    expected_keys = {"diary", "finance", "representatives"}
    actual_keys: set[str] = set()
    for check in checks:
        if not isinstance(check, dict):
            return False, None
        key = check.get("key")
        check_status = check.get("status")
        if key not in expected_keys or check_status not in {
            "available",
            "empty",
            "unavailable",
        }:
            return False, None
        actual_keys.add(key)
    return actual_keys == expected_keys, str(status)


def _valid_html_contract(response: ProbeResponse) -> bool:
    if not response.content_type.lower().startswith("text/html"):
        return False
    try:
        text = response.body.decode("utf-8", errors="strict").lower()
    except UnicodeDecodeError:
        return False
    return "<html" in text and "barreiras 360" in text


def probe_public_site(
    *,
    base_url: str,
    fetcher: Callable[[str], ProbeResponse],
) -> ProbeSummary:
    approved_base_url = _validate_base_url(base_url)
    checked = valid = http_5xx = non_2xx = transport = contract = 0
    health_status: str | None = None
    latencies: list[int] = []

    for target in TARGETS:
        checked += 1
        try:
            target_url = urljoin(
                f"{approved_base_url}/",
                target.path.lstrip("/"),
            )
            response = fetcher(target_url)
        except Exception:
            transport += 1
            continue
        latencies.append(max(0, response.latency_ms))
        if not 200 <= response.status_code <= 299:
            non_2xx += 1
            if 500 <= response.status_code <= 599:
                http_5xx += 1
            continue
        if target.content_kind == "health_json":
            contract_valid, health_status = _valid_health_contract(response)
        else:
            contract_valid = _valid_html_contract(response)
        if not contract_valid:
            contract += 1
            if target.content_kind == "health_json":
                health_status = None
            continue
        valid += 1

    return ProbeSummary(
        targets_checked=checked,
        valid_targets=valid,
        http_5xx_count=http_5xx,
        http_non_2xx_count=non_2xx,
        transport_failures=transport,
        contract_failures=contract,
        health_status=health_status,
        maximum_latency_ms=max(latencies, default=0),
    )


def run_public_availability_probe(
    *,
    repository: object,
    fetcher: Callable[[str], ProbeResponse],
    now: datetime,
    base_url: str,
    execution_origin: str,
    workflow_event: str,
    environment: Mapping[str, str] | None = None,
) -> int:
    approved_base_url = _validate_base_url(base_url)
    observed_on = now.astimezone(MUNICIPAL_TIMEZONE).date()
    control = CollectionControl(
        repository=repository,
        source_code=SOURCE_CODE,
        endpoint_code=ENDPOINT_CODE,
        idempotency_key=build_execution_idempotency_key(
            EXECUTION_NAMESPACE,
            environment=environment,
        ),
        collector_version=COLLECTOR_VERSION,
        parser_version=PARSER_VERSION,
        partition_key=f"day:{observed_on.isoformat()}",
        period_start=observed_on,
        period_end=observed_on,
        execution_origin=execution_origin,
        clock=lambda: now,
    )
    with control:
        summary = probe_public_site(base_url=approved_base_url, fetcher=fetcher)
        metrics = {
            "workflow_event": workflow_event,
            "target_count": len(TARGETS),
            "targets_checked": summary.targets_checked,
            "http_5xx_count": summary.http_5xx_count,
            "http_non_2xx_count": summary.http_non_2xx_count,
            "transport_failures": summary.transport_failures,
            "contract_failures": summary.contract_failures,
            "health_status": summary.health_status,
            "maximum_latency_ms": summary.maximum_latency_ms,
        }
        control.complete(
            outcome=(
                CollectionOutcome.COMPLETE
                if summary.passed
                else CollectionOutcome.PARTIAL
            ),
            observed_records=summary.valid_targets,
            checkpoint={"target_slugs": [target.slug for target in TARGETS]},
            metrics=metrics,
            partial_failure=(
                None
                if summary.passed
                else PartialCollectionFailure(
                    error_type="PublicAvailabilityGateFailure",
                    error_detail=(
                        "Uma ou mais rotas públicas críticas não responderam "
                        "com HTTP 2xx e contrato válido."
                    ),
                    retryable=True,
                )
            ),
        )
    return 0 if summary.passed else 1


def _fetch_response(url: str, *, timeout_seconds: float) -> ProbeResponse:
    request = Request(  # noqa: S310 - URL já restrita ao host HTTPS autorizado.
        url,
        headers={
            "Accept": "application/json,text/html;q=0.9",
            "User-Agent": "Barreiras360-PublicAvailability/1.0",
        },
        method="GET",
    )
    started_at = datetime.now(UTC)
    try:
        response = urlopen(  # noqa: S310 - Request restrita ao host HTTPS autorizado.
            request,
            timeout=timeout_seconds,
        )
    except HTTPError as error:
        response = error
    with response:
        if not _is_approved_target_url(response.geturl()):
            raise ValueError("A rota pública redirecionou para host não autorizado.")
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise ValueError("Resposta pública excede o limite do monitor.")
        latency_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
        return ProbeResponse(
            status_code=int(response.status),
            content_type=response.headers.get("Content-Type", ""),
            body=body,
            latency_ms=max(0, latency_ms),
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sonda rotas públicas críticas e registra o resultado auditável."
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get(
            "PUBLIC_SITE_BASE_URL",
            "https://barreiras-em-dados.vercel.app",
        ),
    )
    parser.add_argument(
        "--execution-origin",
        choices=("manual", "github_actions", "windows_scheduler"),
        default="manual",
    )
    parser.add_argument(
        "--workflow-event",
        choices=("schedule", "workflow_dispatch", "local"),
        default="local",
    )
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    args = parser.parse_args(argv)
    if not 1 <= args.timeout_seconds <= 60:
        parser.error("--timeout-seconds deve estar entre 1 e 60.")

    settings = PostgresSettings.from_env()
    repository = PostgresCollectionRepository.from_dsn(settings.database_url)
    result = run_public_availability_probe(
        repository=repository,
        fetcher=lambda url: _fetch_response(
            url,
            timeout_seconds=args.timeout_seconds,
        ),
        now=datetime.now(UTC),
        base_url=args.base_url,
        execution_origin=args.execution_origin,
        workflow_event=args.workflow_event,
    )
    logging.basicConfig(level=logging.INFO, format="%(message)s", force=True)
    log_event(
        logging.getLogger(__name__),
        logging.INFO if result == 0 else logging.ERROR,
        "public_availability_probe_completed",
        result="pass" if result == 0 else "block",
        target_count=len(TARGETS),
    )
    return result


if __name__ == "__main__":
    raise SystemExit(main())
