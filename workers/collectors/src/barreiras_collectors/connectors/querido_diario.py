"""Cliente paginado e sem persistência para a API pública do Querido Diário."""

from __future__ import annotations

import hashlib
import json
import logging
import random
import time
import urllib.error
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlencode

from ..http import HttpResponse, HttpTransport, UrllibTransport, validate_https_url
from ..logging import log_event
from ..resilience import (
    CircuitBreaker,
    CircuitOpenError,
    PacedRateLimiter,
    RetryPolicy,
)

API_VERSION_OBSERVED = "0.19.0"
DEFAULT_BASE_URL = "https://api.queridodiario.ok.org.br"
DEFAULT_TERRITORY_ID = "2903201"
ALLOWED_HOSTS = frozenset({"api.queridodiario.ok.org.br"})
ALLOWED_ARTIFACT_HOSTS = frozenset(
    {
        "barreiras.ba.gov.br",
        "data.queridodiario.ok.org.br",
        "www.barreiras.ba.gov.br",
        "querido-diario.nyc3.cdn.digitaloceanspaces.com",
    }
)
RETRYABLE_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
EXPECTED_ITEM_FIELDS = frozenset(
    {
        "territory_id",
        "date",
        "scraped_at",
        "url",
        "territory_name",
        "state_code",
        "excerpts",
        "edition",
        "is_extra_edition",
        "txt_url",
    }
)


class QueridoDiarioError(RuntimeError):
    """Erro base explícito do conector."""


class SourceUnavailableError(QueridoDiarioError):
    """A fonte não respondeu com sucesso após a política de retries."""


class PermanentHttpError(QueridoDiarioError):
    """A requisição foi recusada de forma não elegível a retry."""


class SourceContractError(QueridoDiarioError):
    """A resposta não cumpre o contrato mínimo observado."""


class PartialCollectionError(QueridoDiarioError):
    """A paginação terminou antes do total declarado pela fonte."""


@dataclass(frozen=True)
class GazetteItem:
    territory_id: str
    published_date: str
    scraped_at: str
    url: str
    territory_name: str
    state_code: str
    excerpts: tuple[str, ...]
    edition: str | None
    is_extra_edition: bool | None
    txt_url: str | None
    source_extensions: Mapping[str, Any]


@dataclass(frozen=True)
class GazettePage:
    total_gazettes: int
    gazettes: tuple[GazetteItem, ...]
    source_extensions: Mapping[str, Any]


@dataclass(frozen=True)
class CollectedPage:
    schema_name: str
    schema_version: str
    source_code: str
    endpoint_code: str
    idempotency_key: str
    request_url: str
    final_url: str
    requested_at: str
    received_at: str
    attempts: int
    http_status: int
    collection_status: str
    body_sha256: str
    body_size_bytes: int
    media_type: str
    response_headers: Mapping[str, str]
    cursor: Mapping[str, int]
    raw_body: bytes
    parsed: GazettePage
    window_start: str | None = None
    window_end: str | None = None


@dataclass(frozen=True)
class _SuccessfulRequest:
    response: HttpResponse
    requested_at: str
    received_at: str
    attempts: int


class QueridoDiarioClient:
    """Adquire páginas de metadados de diários; não baixa nem interpreta PDFs."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        territory_id: str = DEFAULT_TERRITORY_ID,
        requests_per_minute: int = 30,
        timeout_seconds: float = 35.0,
        max_body_bytes: int = 10 * 1024 * 1024,
        retry_policy: RetryPolicy | None = None,
        transport: HttpTransport | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        rate_limiter: PacedRateLimiter | None = None,
        sleep: Callable[[float], None] = time.sleep,
        random_value: Callable[[], float] = random.random,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        logger: logging.Logger | None = None,
    ) -> None:
        validate_https_url(base_url, ALLOWED_HOSTS)
        if not (territory_id.isdigit() and len(territory_id) == 7):
            raise ValueError("territory_id deve ser um código IBGE de 7 dígitos.")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds deve ser positivo.")
        if max_body_bytes < 1:
            raise ValueError("max_body_bytes deve ser pelo menos 1.")
        if not 1 <= requests_per_minute <= 60:
            raise ValueError("requests_per_minute deve estar entre 1 e 60.")

        self.base_url = base_url.rstrip("/")
        self.territory_id = territory_id
        self.timeout_seconds = timeout_seconds
        self.max_body_bytes = max_body_bytes
        self.retry_policy = retry_policy or RetryPolicy()
        self.transport = transport or UrllibTransport(ALLOWED_HOSTS)
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.rate_limiter = rate_limiter or PacedRateLimiter(requests_per_minute)
        self.sleep = sleep
        self.random_value = random_value
        self.now = now
        self.logger = logger or logging.getLogger(__name__)

    def iter_gazette_pages(
        self,
        *,
        published_since: date | None = None,
        published_until: date | None = None,
        page_size: int = 100,
        querystring: str = "",
        sort_by: str = "ascending_date",
    ) -> Iterator[CollectedPage]:
        """Percorre todas as páginas e preserva bytes/metadados de cada resposta."""
        if published_since and published_until and published_since > published_until:
            raise ValueError(
                "published_since não pode ser posterior a published_until."
            )
        if not 1 <= page_size <= 1000:
            raise ValueError("page_size deve estar entre 1 e 1000.")
        if sort_by not in {"ascending_date", "descending_date", "relevance"}:
            raise ValueError("sort_by inválido.")

        offset = 0
        observed = 0

        while True:
            request_url = self._build_url(
                published_since=published_since,
                published_until=published_until,
                page_size=page_size,
                offset=offset,
                querystring=querystring,
                sort_by=sort_by,
            )
            result = self._get_with_retries(request_url)
            parsed = self._parse_page(result.response.body)
            page_count = len(parsed.gazettes)

            if page_count == 0 and observed < parsed.total_gazettes:
                raise PartialCollectionError(
                    "A fonte retornou página vazia antes do total declarado: "
                    f"observados={observed}, total={parsed.total_gazettes}, "
                    f"offset={offset}."
                )

            observed += page_count
            status = "empty" if parsed.total_gazettes == 0 else "success"
            body_hash = hashlib.sha256(result.response.body).hexdigest()
            idempotency_key = self._idempotency_key(
                request_url=request_url,
                offset=offset,
                body_sha256=body_hash,
            )

            yield CollectedPage(
                schema_name="collection-page",
                schema_version="1.0.0",
                source_code="querido-diario",
                endpoint_code="gazettes-api",
                idempotency_key=idempotency_key,
                request_url=request_url,
                final_url=result.response.final_url,
                requested_at=result.requested_at,
                received_at=result.received_at,
                attempts=result.attempts,
                http_status=result.response.status,
                collection_status=status,
                body_sha256=body_hash,
                body_size_bytes=len(result.response.body),
                media_type=self._media_type(result.response.headers),
                response_headers=self._safe_response_headers(result.response.headers),
                cursor={"offset": offset, "size": page_size},
                raw_body=result.response.body,
                parsed=parsed,
                window_start=(
                    published_since.isoformat() if published_since else None
                ),
                window_end=(
                    published_until.isoformat() if published_until else None
                ),
            )

            if observed >= parsed.total_gazettes:
                break
            offset += page_size

    def _build_url(
        self,
        *,
        published_since: date | None,
        published_until: date | None,
        page_size: int,
        offset: int,
        querystring: str,
        sort_by: str,
    ) -> str:
        params: list[tuple[str, str]] = [
            ("territory_ids", self.territory_id),
            ("querystring", querystring),
            ("size", str(page_size)),
            ("offset", str(offset)),
            ("sort_by", sort_by),
            ("excerpt_size", "500"),
            ("number_of_excerpts", "1"),
        ]
        if published_since:
            params.append(("published_since", published_since.isoformat()))
        if published_until:
            params.append(("published_until", published_until.isoformat()))
        return f"{self.base_url}/gazettes?{urlencode(params)}"

    def _get_with_retries(self, request_url: str) -> _SuccessfulRequest:
        try:
            self.circuit_breaker.before_request()
        except CircuitOpenError:
            log_event(
                self.logger,
                logging.WARNING,
                "collector_circuit_open",
                source="querido-diario",
                endpoint="gazettes",
            )
            raise

        last_error: BaseException | None = None
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            self.rate_limiter.acquire()
            requested_at = self.now().isoformat()
            try:
                response = self.transport.get(
                    request_url,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "BarreirasEmDados-Collector/0.1",
                    },
                    timeout_seconds=self.timeout_seconds,
                    max_body_bytes=self.max_body_bytes,
                )
            except (OSError, TimeoutError, urllib.error.URLError) as error:
                last_error = error
                if attempt == self.retry_policy.max_attempts:
                    break
                self._backoff(attempt, retry_after=None)
                continue

            received_at = self.now().isoformat()
            log_event(
                self.logger,
                logging.INFO,
                "collector_http_response",
                source="querido-diario",
                endpoint="gazettes",
                status=response.status,
                attempt=attempt,
                body_size_bytes=len(response.body),
            )

            if response.status == 200:
                self.circuit_breaker.record_success()
                return _SuccessfulRequest(
                    response=response,
                    requested_at=requested_at,
                    received_at=received_at,
                    attempts=attempt,
                )

            if response.status not in RETRYABLE_STATUSES:
                self.circuit_breaker.record_success()
                raise PermanentHttpError(
                    f"Querido Diário respondeu HTTP {response.status}."
                )

            last_error = SourceUnavailableError(
                f"Querido Diário respondeu HTTP {response.status}."
            )
            if attempt < self.retry_policy.max_attempts:
                self._backoff(
                    attempt,
                    retry_after=self._retry_after_seconds(response.headers),
                )

        self.circuit_breaker.record_failure()
        log_event(
            self.logger,
            logging.ERROR,
            "collector_source_unavailable",
            source="querido-diario",
            endpoint="gazettes",
            attempts=self.retry_policy.max_attempts,
            error_type=type(last_error).__name__ if last_error else "unknown",
        )
        raise SourceUnavailableError(
            "Querido Diário indisponível após "
            f"{self.retry_policy.max_attempts} tentativas."
        ) from last_error

    def _backoff(self, attempt: int, retry_after: float | None) -> None:
        policy_delay = self.retry_policy.delay(attempt, self.random_value())
        delay = max(policy_delay, retry_after or 0.0)
        self.sleep(delay)

    def _parse_page(self, body: bytes) -> GazettePage:
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SourceContractError("Resposta não é JSON UTF-8 válido.") from error
        if not isinstance(payload, dict):
            raise SourceContractError("Raiz da resposta deve ser objeto.")

        required_root = {"total_gazettes", "gazettes"}
        missing_root = required_root - payload.keys()
        if missing_root:
            raise SourceContractError(
                f"Campos obrigatórios ausentes: {sorted(missing_root)}."
            )
        total = payload["total_gazettes"]
        items = payload["gazettes"]
        if isinstance(total, bool) or not isinstance(total, int) or total < 0:
            raise SourceContractError("total_gazettes deve ser inteiro não negativo.")
        if not isinstance(items, list):
            raise SourceContractError("gazettes deve ser uma lista.")

        gazettes = tuple(
            self._parse_item(item, index) for index, item in enumerate(items)
        )
        extensions = {
            key: value for key, value in payload.items() if key not in required_root
        }
        if extensions:
            log_event(
                self.logger,
                logging.WARNING,
                "collector_contract_additive_change",
                source="querido-diario",
                endpoint="gazettes",
                fields=sorted(extensions),
                api_version_observed=API_VERSION_OBSERVED,
            )
        return GazettePage(
            total_gazettes=total,
            gazettes=gazettes,
            source_extensions=extensions,
        )

    def _parse_item(self, item: object, index: int) -> GazetteItem:
        if not isinstance(item, dict):
            raise SourceContractError(f"gazettes[{index}] deve ser objeto.")
        missing = EXPECTED_ITEM_FIELDS - item.keys()
        if missing:
            raise SourceContractError(
                f"gazettes[{index}] sem campos: {sorted(missing)}."
            )

        self._require_string(item, "territory_id", index)
        self._require_string(item, "date", index)
        self._require_string(item, "scraped_at", index)
        self._require_string(item, "url", index)
        self._require_string(item, "territory_name", index)
        self._require_string(item, "state_code", index)
        if item["territory_id"] != self.territory_id:
            raise SourceContractError(
                f"gazettes[{index}] pertence a território inesperado."
            )
        try:
            date.fromisoformat(item["date"])
            datetime.fromisoformat(item["scraped_at"].replace("Z", "+00:00"))
        except ValueError as error:
            raise SourceContractError(
                f"gazettes[{index}] contém data inválida."
            ) from error
        if item["state_code"] != "BA":
            raise SourceContractError(f"gazettes[{index}] tem UF inesperada.")
        self._validate_artifact_url(item["url"], index=index, field="url")

        excerpts = item["excerpts"]
        if not isinstance(excerpts, list) or not all(
            isinstance(excerpt, str) for excerpt in excerpts
        ):
            raise SourceContractError(f"gazettes[{index}].excerpts deve ser lista.")
        if item["edition"] is not None and not isinstance(item["edition"], str):
            raise SourceContractError(f"gazettes[{index}].edition inválida.")
        if item["is_extra_edition"] is not None and not isinstance(
            item["is_extra_edition"], bool
        ):
            raise SourceContractError(f"gazettes[{index}].is_extra_edition inválida.")
        if item["txt_url"] is not None:
            self._require_string(item, "txt_url", index)
            self._validate_artifact_url(
                item["txt_url"],
                index=index,
                field="txt_url",
            )

        extensions = {
            key: value for key, value in item.items() if key not in EXPECTED_ITEM_FIELDS
        }
        return GazetteItem(
            territory_id=item["territory_id"],
            published_date=item["date"],
            scraped_at=item["scraped_at"],
            url=item["url"],
            territory_name=item["territory_name"],
            state_code=item["state_code"],
            excerpts=tuple(excerpts),
            edition=item["edition"],
            is_extra_edition=item["is_extra_edition"],
            txt_url=item["txt_url"],
            source_extensions=extensions,
        )

    @staticmethod
    def _validate_artifact_url(url: str, *, index: int, field: str) -> None:
        try:
            validate_https_url(url, ALLOWED_ARTIFACT_HOSTS)
        except ValueError as error:
            raise SourceContractError(
                f"gazettes[{index}].{field} aponta para URL não permitida."
            ) from error

    @staticmethod
    def _require_string(item: Mapping[str, Any], field: str, index: int) -> None:
        value = item[field]
        if not isinstance(value, str) or not value:
            raise SourceContractError(f"gazettes[{index}].{field} deve ser string.")

    def _idempotency_key(
        self,
        *,
        request_url: str,
        offset: int,
        body_sha256: str,
    ) -> str:
        material = json.dumps(
            {
                "source": "querido-diario",
                "endpoint": "gazettes",
                "territory_id": self.territory_id,
                "request_url": request_url,
                "offset": offset,
                "body_sha256": body_sha256,
                "schema_version": "1.0.0",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(material).hexdigest()

    def _retry_after_seconds(self, headers: Mapping[str, str]) -> float | None:
        raw = self._header(headers, "retry-after")
        if not raw:
            return None
        try:
            return max(0.0, float(raw))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(raw)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                return max(0.0, (retry_at - self.now()).total_seconds())
            except (TypeError, ValueError, OverflowError):
                return None

    @staticmethod
    def _media_type(headers: Mapping[str, str]) -> str:
        content_type = QueridoDiarioClient._header(headers, "content-type")
        return (content_type or "application/octet-stream").split(";", 1)[0].strip()

    @staticmethod
    def _safe_response_headers(headers: Mapping[str, str]) -> dict[str, str]:
        allowed = {"content-type", "etag", "last-modified", "retry-after"}
        return {
            key.lower(): value
            for key, value in headers.items()
            if key.lower() in allowed
        }

    @staticmethod
    def _header(headers: Mapping[str, str], name: str) -> str | None:
        wanted = name.lower()
        return next(
            (value for key, value in headers.items() if key.lower() == wanted),
            None,
        )
