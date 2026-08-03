"""Catálogo oficial de publicações do Diário Municipal de Barreiras.

O PDF é a evidência documental; este catálogo é a fonte estruturada que informa
edição, título, resumo e data. Os dois artefatos são preservados separadamente.
"""

from __future__ import annotations

import hashlib
import html
import logging
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from ..http import HttpTransport, UrllibTransport, validate_https_url
from ..resilience import (
    CircuitBreaker,
    CircuitOpenError,
    PacedRateLimiter,
    RetryPolicy,
)
from .querido_diario import (
    RETRYABLE_STATUSES,
    PermanentHttpError,
    SourceUnavailableError,
)

SOURCE_CODE = "barreiras-diario-oficial"
ENDPOINT_CODE = "catalogo-publicacoes"
CATALOG_URL = "https://pmbarreiras.diariomtransparente.com.br/publicacoes"
ALLOWED_HOSTS = frozenset({"pmbarreiras.diariomtransparente.com.br"})
PARSER_VERSION = "barreiras-diario-catalog/1.0.0"


@dataclass(frozen=True)
class OfficialPublication:
    edition_number: int
    title: str
    summary: str
    published_date: str
    reference: str
    publication_url: str
    summary_url: str


@dataclass(frozen=True)
class OfficialCatalogSnapshot:
    request_url: str
    final_url: str
    requested_at: str
    received_at: str
    attempts: int
    http_status: int
    body_sha256: str
    body_size_bytes: int
    media_type: str
    response_headers: Mapping[str, str]
    raw_body: bytes
    publications: tuple[OfficialPublication, ...]


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _iso_date(value: str) -> str | None:
    match = re.search(r"\b(\d{2})/(\d{2})/(\d{4})\b", value)
    if not match:
        return None
    day, month, year = match.groups()
    return f"{year}-{month}-{day}"


class _CatalogParser(HTMLParser):
    """Extrai linhas da tabela sem depender da ordem visual dos campos."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._row_depth = 0
        self._cell_depth = 0
        self._row_text: list[str] = []
        self._cells: list[str] = []
        self._cell_text: list[str] = []
        self._hrefs: list[str] = []
        self.rows: list[tuple[list[str], list[str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "tr":
            self._row_depth += 1
            if self._row_depth == 1:
                self._row_text, self._cells, self._hrefs = [], [], []
        elif self._row_depth and tag in {"td", "th"}:
            self._cell_depth += 1
            if self._cell_depth == 1:
                self._cell_text = []
        if self._row_depth and tag == "a":
            href = dict(attrs).get("href")
            if href:
                self._hrefs.append(href)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._row_depth and tag in {"td", "th"} and self._cell_depth:
            self._cell_depth -= 1
            if self._cell_depth == 0:
                self._cells.append(_clean(" ".join(self._cell_text)))
        elif tag == "tr" and self._row_depth:
            self._row_depth -= 1
            if self._row_depth == 0:
                self.rows.append((self._cells, self._hrefs))

    def handle_data(self, data: str) -> None:
        if not self._row_depth:
            return
        self._row_text.append(data)
        if self._cell_depth:
            self._cell_text.append(data)


def parse_catalog_html(
    body: bytes, *, base_url: str = CATALOG_URL
) -> tuple[OfficialPublication, ...]:
    """Valida e normaliza o catálogo oficial, sem inferir dados do PDF."""
    parser = _CatalogParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    parsed: list[OfficialPublication] = []
    seen: set[tuple[int, str]] = set()
    for cells, hrefs in parser.rows:
        text = _clean(" ".join(cells))
        ref_match = next(
            (
                match
                for href in hrefs
                if (match := re.search(r"[?&]referencia=([0-9]+)", href))
            ),
            None,
        )
        if ref_match is None:
            continue
        reference = ref_match.group(1)
        edition_match = re.search(
            r"(?:Edi[cç][aã]o|EdiÃ§Ã£o)\s*[:#-]?\s*(\d+)",
            text,
            re.I,
        )
        if edition_match is None:
            edition_match = re.search(r"\b(\d{3,6})\b", text)
        published_date = _iso_date(text)
        if edition_match is None or published_date is None:
            continue
        edition = int(edition_match.group(1))
        title_match = re.search(
            r"Di[aá]rio Oficial\s*[-–—]\s*Edi[cç][aã]o\s*\d+",
            text,
            re.I,
        )
        title = (
            title_match.group(0)
            if title_match
            else f"Diário Oficial - Edição {edition}"
        )
        summary = next(
            (
                cell
                for cell in cells
                if len(cell) >= 24
                and cell != title
                and _iso_date(cell) is None
                and not re.fullmatch(r"\d{3,6}", cell)
                and "Diário Oficial" not in cell
            ),
            "Resumo oficial ainda não informado no catálogo.",
        )
        key = (edition, published_date)
        if key in seen:
            continue
        seen.add(key)
        publication_url = urljoin(base_url, f"/publicacao?referencia={reference}")
        summary_url = urljoin(base_url, f"/_core/_ajax/resumo.php?id={reference}")
        validate_https_url(publication_url, ALLOWED_HOSTS)
        validate_https_url(summary_url, ALLOWED_HOSTS)
        parsed.append(
            OfficialPublication(
                edition_number=edition,
                title=title,
                summary=summary,
                published_date=published_date,
                reference=reference,
                publication_url=publication_url,
                summary_url=summary_url,
            )
        )
    if not parsed:
        raise ValueError(
            "O catálogo oficial não contém publicações reconhecíveis."
        )
    return tuple(parsed)


class OfficialDiaryCatalogClient:
    """Cliente com retry, rate limit e circuit breaker para o catálogo oficial."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 30,
        max_body_bytes: int = 8 * 1024 * 1024,
        retry_policy: RetryPolicy | None = None,
        transport: HttpTransport | None = None,
        rate_limiter: PacedRateLimiter | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        random_value: Callable[[], float] = lambda: 0.5,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_body_bytes = max_body_bytes
        self.retry_policy = retry_policy or RetryPolicy(max_attempts=5)
        self.transport = transport or UrllibTransport(ALLOWED_HOSTS)
        self.rate_limiter = rate_limiter or PacedRateLimiter(10)
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.sleep = sleep
        self.now = now
        self.random_value = random_value

    def fetch(self) -> OfficialCatalogSnapshot:
        try:
            self.circuit_breaker.before_request()
        except CircuitOpenError:
            raise
        last_error: BaseException | None = None
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            self.rate_limiter.acquire()
            requested_at = self.now().isoformat()
            try:
                response = self.transport.get(
                    CATALOG_URL,
                    headers={"User-Agent": "Barreiras360-Collector/1.0"},
                    timeout_seconds=self.timeout_seconds,
                    max_body_bytes=self.max_body_bytes,
                )
            except (OSError, TimeoutError) as error:
                last_error = error
                if attempt < self.retry_policy.max_attempts:
                    self.sleep(self.retry_policy.delay(attempt, self.random_value()))
                continue
            received_at = self.now().isoformat()
            if response.status == 200:
                self.circuit_breaker.record_success()
                publications = parse_catalog_html(
                    response.body, base_url=response.final_url
                )
                return OfficialCatalogSnapshot(
                    request_url=CATALOG_URL,
                    final_url=response.final_url,
                    requested_at=requested_at,
                    received_at=received_at,
                    attempts=attempt,
                    http_status=response.status,
                    body_sha256=hashlib.sha256(response.body).hexdigest(),
                    body_size_bytes=len(response.body),
                    media_type="text/html; charset=utf-8",
                    response_headers=dict(response.headers),
                    raw_body=response.body,
                    publications=publications,
                )
            if response.status not in RETRYABLE_STATUSES:
                self.circuit_breaker.record_success()
                raise PermanentHttpError(
                    f"Catálogo oficial respondeu HTTP {response.status}.",
                    status_code=response.status,
                )
            last_error = SourceUnavailableError(
                f"Catálogo oficial respondeu HTTP {response.status}."
            )
            if attempt < self.retry_policy.max_attempts:
                self.sleep(self.retry_policy.delay(attempt, self.random_value()))
        self.circuit_breaker.record_failure()
        raise SourceUnavailableError(
            "Catálogo oficial indisponível após retries."
        ) from last_error
