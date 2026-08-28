"""Consulta auditável das prestações mensais publicadas pelo TCM-BA.

O e-TCM usa uma sessão JSF com campos dependentes. Este conector reproduz a
sequência observada na consulta pública e preserva cada resposta recebida. Ele
apenas cataloga os documentos; valores financeiros só podem ser reconciliados
depois que o PDF correspondente for preservado e validado.
"""

from __future__ import annotations

import hashlib
import http.cookiejar
import random
import re
import ssl
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import urljoin

from ..http import (
    RETRYABLE_TRANSPORT_EXCEPTIONS,
    HttpResponse,
    ResponseTooLargeError,
    validate_https_url,
)
from ..resilience import CircuitBreaker, PacedRateLimiter, RetryPolicy

SOURCE_CODE = "tcm-ba"
ENDPOINT_CODE = "prestacoes-contas-mensais"
BASE_URL = "https://e.tcm.ba.gov.br/epp/ConsultaPublica/listView.seam"
DOWNLOAD_URL = "https://e.tcm.ba.gov.br/epp/PdfReadOnly/downloadDocumento.seam"
ALLOWED_HOSTS = frozenset({"e.tcm.ba.gov.br"})
FORM_ID = "consultaPublicaTabPanel:consultaPublicaPCSearchForm"
TABLE_ID = "consultaPublicaTabPanel:tabelaDocumentos"
PAGE_SIZE = 10
SAFE_RESPONSE_HEADERS = frozenset(
    {"content-type", "content-length", "date", "etag", "last-modified"}
)
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
MAX_DOCUMENT_PAGES_PER_SESSION = 60
MAX_SESSION_RENEWAL_ATTEMPTS = 3
DEFAULT_MAX_DOCUMENT_BYTES = 64 * 1024 * 1024


class TcmBaError(RuntimeError):
    """Falha explícita na consulta pública do TCM-BA."""


class TcmBaContractError(TcmBaError):
    """A página recebida diverge do contrato observado e não é confiável."""


class TcmBaSessionTransport(Protocol):
    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_seconds: float,
        max_body_bytes: int,
    ) -> HttpResponse: ...

    def post(
        self,
        url: str,
        *,
        form: Mapping[str, str],
        headers: Mapping[str, str],
        timeout_seconds: float,
        max_body_bytes: int,
    ) -> HttpResponse: ...
    def reset_session(self) -> None: ...


class _RestrictedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts: frozenset[str]) -> None:
        super().__init__()
        self.allowed_hosts = allowed_hosts

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> urllib.request.Request | None:
        target = urljoin(req.full_url, newurl)
        validate_https_url(target, self.allowed_hosts)
        return super().redirect_request(req, fp, code, msg, headers, target)


class UrllibSessionTransport:
    """Transporte com cookies de sessão e redirects restritos ao e-TCM."""

    def __init__(self, allowed_hosts: frozenset[str] = ALLOWED_HOSTS) -> None:
        self.allowed_hosts = allowed_hosts
        cookie_jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cookie_jar),
            _RestrictedRedirectHandler(allowed_hosts),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        )

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_seconds: float,
        max_body_bytes: int,
    ) -> HttpResponse:
        return self._request(
            url,
            method="GET",
            headers=headers,
            timeout_seconds=timeout_seconds,
            max_body_bytes=max_body_bytes,
        )

    def post(
        self,
        url: str,
        *,
        form: Mapping[str, str],
        headers: Mapping[str, str],
        timeout_seconds: float,
        max_body_bytes: int,
    ) -> HttpResponse:
        encoded = urllib.parse.urlencode(form).encode("utf-8")
        return self._request(
            url,
            method="POST",
            headers={
                **dict(headers),
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
            data=encoded,
            timeout_seconds=timeout_seconds,
            max_body_bytes=max_body_bytes,
        )

    def _request(
        self,
        url: str,
        *,
        method: str,
        headers: Mapping[str, str],
        timeout_seconds: float,
        max_body_bytes: int,
        data: bytes | None = None,
    ) -> HttpResponse:
        if timeout_seconds <= 0 or max_body_bytes < 1:
            raise ValueError("timeout_seconds e max_body_bytes devem ser positivos.")
        validate_https_url(url, self.allowed_hosts)
        request = urllib.request.Request(  # noqa: S310 - HTTPS sob allowlist.
            url,
            data=data,
            headers=dict(headers),
            method=method,
        )
        try:
            with self._opener.open(request, timeout=timeout_seconds) as response:
                body = response.read(max_body_bytes + 1)
                if len(body) > max_body_bytes:
                    raise ResponseTooLargeError(
                        f"Resposta excede o limite de {max_body_bytes} bytes."
                    )
                final_url = response.geturl()
                validate_https_url(final_url, self.allowed_hosts)
                return HttpResponse(
                    status=response.status,
                    headers=dict(response.headers.items()),
                    body=body,
                    final_url=final_url,
                )
        except urllib.error.HTTPError as error:
            final_url = error.geturl()
            validate_https_url(final_url, self.allowed_hosts)
            body = error.read(max_body_bytes + 1)
            if len(body) > max_body_bytes:
                raise ResponseTooLargeError(
                    f"Resposta de erro excede {max_body_bytes} bytes."
                ) from error
            return HttpResponse(
                status=error.code,
                headers=dict(error.headers.items()) if error.headers else {},
                body=body,
                final_url=final_url,
            )

    def reset_session(self) -> None:
        """Descarta cookies JSF para iniciar uma sessão oficial limpa."""
        cookie_jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cookie_jar),
            _RestrictedRedirectHandler(self.allowed_hosts),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        )


@dataclass(frozen=True)
class TcmBaInteraction:
    stage: str
    request_url: str
    final_url: str
    http_status: int
    received_at: str
    response_headers: Mapping[str, str]
    body_sha256: str
    raw_body: bytes


@dataclass(frozen=True)
class TcmBaSubmission:
    competence: str
    type: str
    unit: str
    sent_at: str
    status: str


@dataclass(frozen=True)
class TcmBaDocument:
    category: str
    name: str
    inserted_at: str
    page_number: int
    download_form_id: str


@dataclass(frozen=True)
class TcmBaDocumentDownload:
    schema_name: str
    schema_version: str
    source_code: str
    endpoint_code: str
    source_url: str
    download_url: str
    competence: str
    total_documents: int
    document_position: int
    document: TcmBaDocument
    prepare_interaction: TcmBaInteraction
    pdf_interaction: TcmBaInteraction


@dataclass(frozen=True)
class TcmBaMonthlyCatalog:
    schema_name: str
    schema_version: str
    source_code: str
    endpoint_code: str
    source_url: str
    competence: str
    submission: TcmBaSubmission
    total_documents: int
    documents: tuple[TcmBaDocument, ...]
    interactions: tuple[TcmBaInteraction, ...]


def validate_tcm_ba_catalog(catalog: TcmBaMonthlyCatalog) -> None:
    """Recompõe o catálogo somente a partir das respostas brutas preservadas."""
    if catalog.schema_name != "tcm-ba-monthly-public-accounts-catalog":
        raise TcmBaContractError("Schema inesperado para o catálogo do e-TCM.")
    if catalog.source_code != SOURCE_CODE or catalog.endpoint_code != ENDPOINT_CODE:
        raise TcmBaContractError("Origem inesperada para o catálogo do e-TCM.")

    interactions: dict[str, TcmBaInteraction] = {}
    for interaction in catalog.interactions:
        if interaction.stage in interactions:
            raise TcmBaContractError("Etapa duplicada na captura do e-TCM.")
        if hashlib.sha256(interaction.raw_body).hexdigest() != interaction.body_sha256:
            raise TcmBaContractError("Resposta bruta do e-TCM diverge do hash.")
        validate_https_url(interaction.request_url, ALLOWED_HOSTS)
        validate_https_url(interaction.final_url, ALLOWED_HOSTS)
        interactions[interaction.stage] = interaction

    search = interactions.get("search-submission")
    detail = interactions.get("select-submission")
    if search is None or detail is None:
        raise TcmBaContractError("Captura do e-TCM sem busca ou detalhamento.")
    submission, _form_id = _parse_submission(search.raw_body, catalog.competence)
    if submission != catalog.submission:
        raise TcmBaContractError("Prestação estruturada diverge da resposta bruta.")

    total_documents = _parse_total_documents(detail.raw_body)
    if total_documents != catalog.total_documents:
        raise TcmBaContractError("Total estruturado diverge da resposta bruta.")
    documents = list(_parse_documents(detail.raw_body, page_number=1))
    total_pages = max(1, (total_documents + PAGE_SIZE - 1) // PAGE_SIZE)
    for page_number in range(2, total_pages + 1):
        page = interactions.get(f"documents-page-{page_number}")
        if page is None:
            raise TcmBaContractError("Captura do e-TCM está sem página documental.")
        documents.extend(_parse_documents(page.raw_body, page_number=page_number))
    if tuple(documents) != catalog.documents or len(documents) != total_documents:
        raise TcmBaContractError("Documentos estruturados divergem do bruto do e-TCM.")


def validate_tcm_ba_document_download(download: TcmBaDocumentDownload) -> None:
    """Confirma metadados, sessão preparatória e bytes do PDF oficial."""

    if download.schema_name != "tcm-ba-monthly-document":
        raise TcmBaContractError("Schema inesperado para documento do e-TCM.")
    if (
        download.source_code != SOURCE_CODE
        or download.endpoint_code != ENDPOINT_CODE
        or download.source_url != BASE_URL
        or download.download_url != DOWNLOAD_URL
    ):
        raise TcmBaContractError("Origem inesperada para documento do e-TCM.")
    if not 1 <= download.document_position <= download.total_documents:
        raise TcmBaContractError("Posição documental fora do catálogo mensal.")
    expected_page = (download.document_position - 1) // PAGE_SIZE + 1
    if download.document.page_number != expected_page:
        raise TcmBaContractError("Página do documento diverge da posição no catálogo.")
    if not download.document.name.casefold().endswith(".pdf"):
        raise TcmBaContractError("Nome documental sem extensão PDF verificável.")

    for interaction in (download.prepare_interaction, download.pdf_interaction):
        if hashlib.sha256(interaction.raw_body).hexdigest() != interaction.body_sha256:
            raise TcmBaContractError("Resposta documental diverge do hash calculado.")
        validate_https_url(interaction.request_url, ALLOWED_HOSTS)
        validate_https_url(interaction.final_url, ALLOWED_HOSTS)
        if interaction.http_status != 200:
            raise TcmBaContractError("Resposta documental não concluiu com HTTP 200.")

    if _parse_download_url(download.prepare_interaction.raw_body) != DOWNLOAD_URL:
        raise TcmBaContractError(
            "Preparação do download apontou para endereço inesperado."
        )
    pdf = download.pdf_interaction
    if pdf.request_url != DOWNLOAD_URL or pdf.final_url != DOWNLOAD_URL:
        raise TcmBaContractError("PDF foi recebido fora do endpoint oficial esperado.")
    if _response_media_type(pdf.response_headers) != "application/pdf":
        raise TcmBaContractError("Endpoint de download não declarou application/pdf.")
    if not pdf.raw_body.startswith(b"%PDF-"):
        raise TcmBaContractError("O corpo retornado pelo e-TCM não é PDF.")
    if b"%%EOF" not in pdf.raw_body[-8192:]:
        raise TcmBaContractError("PDF do e-TCM não contém marcador final verificável.")


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str]
    parent: _Node | None = None
    children: list[_Node] = field(default_factory=list)
    text_parts: list[str] = field(default_factory=list)

    def text(self) -> str:
        content = "".join(self.text_parts)
        for child in self.children:
            content += " " + child.text()
        return " ".join(content.split())

    def descendants(self, tag: str | None = None) -> list[_Node]:
        found: list[_Node] = []
        for child in self.children:
            if tag is None or child.tag == tag:
                found.append(child)
            found.extend(child.descendants(tag))
        return found


class _DomParser(HTMLParser):
    _VOID = frozenset(
        {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("root", {})
        self.current = self.root

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(
            tag.lower(),
            {key: value or "" for key, value in attrs},
            parent=self.current,
        )
        self.current.children.append(node)
        if tag.lower() not in self._VOID:
            self.current = node

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in self._VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        target = tag.lower()
        node = self.current
        while node.parent is not None:
            if node.tag == target:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data: str) -> None:
        self.current.text_parts.append(data)


class TcmBaPublicAccountsClient:
    """Navega pelo catálogo mensal do e-TCM sem inferir valores."""

    def __init__(
        self,
        *,
        transport: TcmBaSessionTransport | None = None,
        requests_per_minute: int = 10,
        timeout_seconds: float = 30.0,
        max_body_bytes: int = 16 * 1024 * 1024,
        max_document_bytes: int = DEFAULT_MAX_DOCUMENT_BYTES,
        rate_limiter: PacedRateLimiter | None = None,
        retry_policy: RetryPolicy | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        sleep: Callable[[float], None] = time.sleep,
        random_value: Callable[[], float] = random.random,
    ) -> None:
        if timeout_seconds <= 0 or max_body_bytes < 1 or max_document_bytes < 1:
            raise ValueError(
                "timeout_seconds, max_body_bytes e max_document_bytes "
                "devem ser positivos."
            )
        self.transport = transport or UrllibSessionTransport()
        self.timeout_seconds = timeout_seconds
        self.max_body_bytes = max_body_bytes
        self.max_document_bytes = max_document_bytes
        self.rate_limiter = rate_limiter or PacedRateLimiter(requests_per_minute)
        self.retry_policy = retry_policy or RetryPolicy(max_attempts=4)
        self.circuit_breaker = circuit_breaker or CircuitBreaker(
            failure_threshold=self.retry_policy.max_attempts
        )
        self.sleep = sleep
        self.random_value = random_value
        self.max_document_pages_per_session = MAX_DOCUMENT_PAGES_PER_SESSION

    def fetch_monthly_catalog(self, *, year: int, month: int) -> TcmBaMonthlyCatalog:
        current_year = datetime.now(UTC).year
        if not 2015 <= year <= current_year:
            raise ValueError(
                "year deve estar no intervalo público de 2015 ao ano atual."
            )
        if not 1 <= month <= 12:
            raise ValueError("month deve estar entre 1 e 12.")

        competence = f"{month:02d}/{year}"
        interactions: list[TcmBaInteraction] = []
        (
            submission,
            detail,
            total_documents,
            pagination_form_id,
        ) = self._open_monthly_catalog_session(
            year=year,
            competence=competence,
            interactions=interactions,
            stage_suffix="",
        )
        documents = list(_parse_documents(detail.raw_body, page_number=1))

        current = detail
        first_page_documents = tuple(documents)
        total_pages = max(1, (total_documents + PAGE_SIZE - 1) // PAGE_SIZE)
        for page_number in range(2, total_pages + 1):
            if (page_number - 1) % self.max_document_pages_per_session == 0:
                current, pagination_form_id = self._renew_monthly_catalog_session(
                    year=year,
                    competence=competence,
                    interactions=interactions,
                    submission=submission,
                    total_documents=total_documents,
                    first_page_documents=first_page_documents,
                    page_number=page_number,
                    reason="resume",
                )
            page_attempt = 1
            while True:
                pagination = {
                    "javax.faces.partial.ajax": "true",
                    "javax.faces.source": TABLE_ID,
                    "javax.faces.partial.execute": TABLE_ID,
                    "javax.faces.partial.render": TABLE_ID,
                    TABLE_ID: TABLE_ID,
                    f"{TABLE_ID}_pagination": "true",
                    f"{TABLE_ID}_first": str((page_number - 1) * PAGE_SIZE),
                    f"{TABLE_ID}_rows": str(PAGE_SIZE),
                    f"{TABLE_ID}_encodeFeature": "true",
                    pagination_form_id: pagination_form_id,
                    "javax.faces.ViewState": _view_state(current.raw_body),
                }
                current = self._post(
                    f"documents-page-{page_number}",
                    BASE_URL,
                    pagination,
                    interactions,
                )
                try:
                    page_documents = _parse_documents(
                        current.raw_body,
                        page_number=page_number,
                    )
                except TcmBaContractError as error:
                    interactions[-1] = replace(
                        interactions[-1],
                        stage=(
                            f"documents-page-{page_number}-contract-failure-"
                            f"{page_attempt}"
                        ),
                    )
                    if page_attempt > MAX_SESSION_RENEWAL_ATTEMPTS:
                        raise TcmBaContractError(
                            "O e-TCM não devolveu a tabela esperada para a página "
                            f"{page_number} após recuperação de sessão."
                        ) from error
                    current, pagination_form_id = self._renew_monthly_catalog_session(
                        year=year,
                        competence=competence,
                        interactions=interactions,
                        submission=submission,
                        total_documents=total_documents,
                        first_page_documents=first_page_documents,
                        page_number=page_number,
                        reason="recover",
                    )
                    page_attempt += 1
                    continue
                documents.extend(page_documents)
                break
        if len(documents) != total_documents:
            raise TcmBaContractError(
                "O total de documentos extraídos diverge do informado pelo e-TCM."
            )
        return TcmBaMonthlyCatalog(
            schema_name="tcm-ba-monthly-public-accounts-catalog",
            schema_version="1.0.0",
            source_code=SOURCE_CODE,
            endpoint_code=ENDPOINT_CODE,
            source_url=BASE_URL,
            competence=competence,
            submission=submission,
            total_documents=total_documents,
            documents=tuple(documents),
            interactions=tuple(interactions),
        )

    def fetch_monthly_document(
        self,
        *,
        year: int,
        month: int,
        document_position: int,
        expected_total_documents: int | None = None,
        expected_document: TcmBaDocument | None = None,
    ) -> TcmBaDocumentDownload:
        """Baixa um PDF exato após recompor a página correspondente do catálogo."""

        current_year = datetime.now(UTC).year
        if not 2015 <= year <= current_year:
            raise ValueError(
                "year deve estar no intervalo público de 2015 ao ano atual."
            )
        if not 1 <= month <= 12:
            raise ValueError("month deve estar entre 1 e 12.")
        if document_position < 1:
            raise ValueError("document_position deve ser pelo menos 1.")
        if expected_total_documents is not None and expected_total_documents < 1:
            raise ValueError("expected_total_documents deve ser positivo.")

        competence = f"{month:02d}/{year}"
        interactions: list[TcmBaInteraction] = []
        (
            _submission,
            detail,
            total_documents,
            pagination_form_id,
        ) = self._open_monthly_catalog_session(
            year=year,
            competence=competence,
            interactions=interactions,
            stage_suffix="-document-download",
        )
        if (
            expected_total_documents is not None
            and total_documents != expected_total_documents
        ):
            raise TcmBaContractError(
                "Total mensal do e-TCM divergiu do catálogo preservado."
            )
        if document_position > total_documents:
            raise TcmBaContractError("Posição solicitada excede o catálogo mensal.")

        target_page = (document_position - 1) // PAGE_SIZE + 1
        page_interaction = detail
        if target_page > 1:
            pagination = {
                "javax.faces.partial.ajax": "true",
                "javax.faces.source": TABLE_ID,
                "javax.faces.partial.execute": TABLE_ID,
                "javax.faces.partial.render": TABLE_ID,
                TABLE_ID: TABLE_ID,
                f"{TABLE_ID}_pagination": "true",
                f"{TABLE_ID}_first": str((target_page - 1) * PAGE_SIZE),
                f"{TABLE_ID}_rows": str(PAGE_SIZE),
                f"{TABLE_ID}_encodeFeature": "true",
                pagination_form_id: pagination_form_id,
                "javax.faces.ViewState": _view_state(detail.raw_body),
            }
            page_interaction = self._post(
                f"document-download-page-{target_page}",
                BASE_URL,
                pagination,
                interactions,
            )
        page_documents = _parse_documents(
            page_interaction.raw_body,
            page_number=target_page,
        )
        local_index = (document_position - 1) % PAGE_SIZE
        if local_index >= len(page_documents):
            raise TcmBaContractError(
                "Página documental não contém a posição anunciada pelo e-TCM."
            )
        document = page_documents[local_index]
        if expected_document is not None and document != expected_document:
            raise TcmBaContractError(
                "Documento atual divergiu do catálogo preservado; download bloqueado."
            )

        component = f"{document.download_form_id}:downloadDocBinario"
        prepare_form = {
            document.download_form_id: document.download_form_id,
            "javax.faces.ViewState": _view_state(page_interaction.raw_body),
            **_ajax_click_fields(component),
        }
        prepare = self._post(
            f"prepare-document-{document_position}",
            BASE_URL,
            prepare_form,
            interactions,
        )
        download_url = _parse_download_url(prepare.raw_body)
        pdf = self._get(
            f"download-document-{document_position}",
            download_url,
            interactions,
            max_body_bytes=self.max_document_bytes,
        )
        result = TcmBaDocumentDownload(
            schema_name="tcm-ba-monthly-document",
            schema_version="1.0.0",
            source_code=SOURCE_CODE,
            endpoint_code=ENDPOINT_CODE,
            source_url=BASE_URL,
            download_url=download_url,
            competence=competence,
            total_documents=total_documents,
            document_position=document_position,
            document=document,
            prepare_interaction=prepare,
            pdf_interaction=pdf,
        )
        validate_tcm_ba_document_download(result)
        return result

    def _renew_monthly_catalog_session(
        self,
        *,
        year: int,
        competence: str,
        interactions: list[TcmBaInteraction],
        submission: TcmBaSubmission,
        total_documents: int,
        first_page_documents: tuple[TcmBaDocument, ...],
        page_number: int,
        reason: str,
    ) -> tuple[TcmBaInteraction, str]:
        last_renewal_error: TcmBaContractError | None = None
        for renewal_attempt in range(1, MAX_SESSION_RENEWAL_ATTEMPTS + 1):
            self.transport.reset_session()
            try:
                (
                    resumed_submission,
                    resumed_detail,
                    resumed_total_documents,
                    resumed_pagination_form_id,
                ) = self._open_monthly_catalog_session(
                    year=year,
                    competence=competence,
                    interactions=interactions,
                    stage_suffix=(f"-{reason}-{page_number}-attempt-{renewal_attempt}"),
                )
                resumed_first_page = _parse_documents(
                    resumed_detail.raw_body,
                    page_number=1,
                )
            except TcmBaContractError as error:
                last_renewal_error = error
                continue
            if (
                resumed_submission == submission
                and resumed_total_documents == total_documents
                and resumed_first_page == first_page_documents
            ):
                return resumed_detail, resumed_pagination_form_id
            last_renewal_error = TcmBaContractError(
                "A sessão renovada divergiu do snapshot mensal fixado."
            )
        raise TcmBaContractError(
            "O catálogo do e-TCM divergiu do snapshot durante todas as "
            "tentativas de renovação da sessão."
        ) from last_renewal_error

    def _open_monthly_catalog_session(
        self,
        *,
        year: int,
        competence: str,
        interactions: list[TcmBaInteraction],
        stage_suffix: str,
    ) -> tuple[TcmBaSubmission, TcmBaInteraction, int, str]:
        initial = self._get(f"initial-form{stage_suffix}", BASE_URL, interactions)
        state = _parse_form_state(initial.raw_body)
        state = self._change_select(
            state,
            f"{FORM_ID}:PeriodicidadePC_input",
            "Mensal",
            f"select-periodicity{stage_suffix}",
            interactions,
        )
        state = self._change_select(
            state,
            f"{FORM_ID}:competenciaPCAno_input",
            str(year),
            f"select-year{stage_suffix}",
            interactions,
        )
        state = self._change_select(
            state,
            f"{FORM_ID}:municipio_input",
            "BARREIRAS",
            f"select-municipality{stage_suffix}",
            interactions,
        )
        state = self._change_select(
            state,
            f"{FORM_ID}:unidadeJurisdicionada_input",
            "Prefeitura Municipal de BARREIRAS",
            f"select-accounting-unit{stage_suffix}",
            interactions,
        )

        form = dict(state.values)
        form[f"{FORM_ID}:municipio_input"] = _option_value(
            state.form,
            f"{FORM_ID}:municipio_input",
            "Clique para selecionar",
            allow_placeholder=True,
        )
        form[f"{FORM_ID}:competenciaPCMes_input"] = _option_value(
            state.form,
            f"{FORM_ID}:competenciaPCMes_input",
            competence,
        )
        form[f"{FORM_ID}:tipoPC_input"] = _option_value(
            state.form,
            f"{FORM_ID}:tipoPC_input",
            "Gestão",
        )
        search_button = f"{FORM_ID}:searchButton"
        form.update(_ajax_click_fields(search_button))
        form[f"{FORM_ID}:j_idt87"] = "1"
        search = self._post(
            f"search-submission{stage_suffix}",
            state.action_url,
            form,
            interactions,
        )
        submission, submission_form = _parse_submission(
            search.raw_body,
            competence,
        )
        selection_button = f"{submission_form}:selecionarPrestacao"
        selection_form = {
            submission_form: submission_form,
            "javax.faces.ViewState": _view_state(search.raw_body),
            **_ajax_click_fields(selection_button),
        }
        detail = self._post(
            f"select-submission{stage_suffix}",
            BASE_URL,
            selection_form,
            interactions,
        )
        return (
            submission,
            detail,
            _parse_total_documents(detail.raw_body),
            _parse_pagination_form_id(detail.raw_body),
        )

    def _change_select(
        self,
        state: _FormState,
        component: str,
        label: str,
        stage: str,
        interactions: list[TcmBaInteraction],
    ) -> _FormState:
        selected_value = _option_value(state.form, component, label)
        form = dict(state.values)
        form[component] = selected_value
        ajax_fields = _ajax_change_fields(component)
        preflight_fields = dict(ajax_fields)
        preflight_fields.pop("javax.faces.partial.render")
        preflight_form = {**form, **preflight_fields}
        preflight = self._post(
            f"{stage}-preflight",
            state.action_url,
            preflight_form,
            interactions,
        )
        form["javax.faces.ViewState"] = _view_state(preflight.raw_body)
        form.update(ajax_fields)
        response = self._post(stage, state.action_url, form, interactions)
        return _parse_form_state(response.raw_body)

    def _get(
        self,
        stage: str,
        url: str,
        interactions: list[TcmBaInteraction],
        *,
        max_body_bytes: int | None = None,
    ) -> TcmBaInteraction:
        response_limit = (
            self.max_body_bytes if max_body_bytes is None else max_body_bytes
        )
        return self._request(
            stage,
            url,
            lambda: self.transport.get(
                url,
                headers=_request_headers(),
                timeout_seconds=self.timeout_seconds,
                max_body_bytes=response_limit,
            ),
            interactions,
        )

    def _post(
        self,
        stage: str,
        url: str,
        form: Mapping[str, str],
        interactions: list[TcmBaInteraction],
    ) -> TcmBaInteraction:
        return self._request(
            stage,
            url,
            lambda: self.transport.post(
                url,
                form=form,
                headers=_request_headers(ajax=True),
                timeout_seconds=self.timeout_seconds,
                max_body_bytes=self.max_body_bytes,
            ),
            interactions,
        )

    def _request(
        self,
        stage: str,
        url: str,
        operation: Callable[[], HttpResponse],
        interactions: list[TcmBaInteraction],
    ) -> TcmBaInteraction:
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            self.circuit_breaker.before_request()
            self.rate_limiter.acquire()
            try:
                response = operation()
            except RETRYABLE_TRANSPORT_EXCEPTIONS as error:
                self.circuit_breaker.record_failure()
                if attempt == self.retry_policy.max_attempts:
                    raise TcmBaError(
                        f"Falha de transporte no e-TCM em {stage} após {attempt} "
                        "tentativas."
                    ) from error
                self._backoff(attempt)
                continue

            if response.status == 200:
                self.circuit_breaker.record_success()
                return self._record(stage, url, response, interactions)

            self._record(f"{stage}-attempt-{attempt}", url, response, interactions)
            self.circuit_breaker.record_failure()
            if (
                response.status not in RETRYABLE_HTTP_STATUSES
                or attempt == self.retry_policy.max_attempts
            ):
                raise TcmBaError(
                    f"O e-TCM respondeu HTTP {response.status} em {stage}."
                )
            self._backoff(attempt)

        raise AssertionError("Loop de tentativas do e-TCM terminou sem resultado.")

    def _backoff(self, attempt: int) -> None:
        self.sleep(self.retry_policy.delay(attempt, self.random_value()))

    @staticmethod
    def _record(
        stage: str,
        request_url: str,
        response: HttpResponse,
        interactions: list[TcmBaInteraction],
    ) -> TcmBaInteraction:
        validate_https_url(response.final_url, ALLOWED_HOSTS)
        interaction = TcmBaInteraction(
            stage=stage,
            request_url=request_url,
            final_url=response.final_url,
            http_status=response.status,
            received_at=datetime.now(UTC).isoformat(),
            response_headers=_safe_headers(response.headers),
            body_sha256=hashlib.sha256(response.body).hexdigest(),
            raw_body=response.body,
        )
        interactions.append(interaction)
        return interaction


@dataclass(frozen=True)
class _FormState:
    form: _Node
    action_url: str
    values: Mapping[str, str]


def _parse_form_state(body: bytes) -> _FormState:
    root = _parse_dom(body)
    form = _find_by_id(root, FORM_ID)
    if form is None or form.tag != "form":
        raise TcmBaContractError("Formulário principal do e-TCM não encontrado.")
    action = urljoin(BASE_URL, form.attrs.get("action", BASE_URL))
    validate_https_url(action, ALLOWED_HOSTS)
    values: dict[str, str] = {}
    for node in form.descendants():
        name = node.attrs.get("name")
        if not name:
            continue
        if node.tag == "input":
            if node.attrs.get("type", "text").lower() in {"submit", "image"}:
                continue
            values[name] = node.attrs.get("value", "")
        elif node.tag == "select":
            options = [child for child in node.descendants("option")]
            selected = next(
                (option for option in options if "selected" in option.attrs),
                options[0] if options else None,
            )
            values[name] = (
                selected.attrs.get("value", selected.text()) if selected else ""
            )
    values[FORM_ID] = FORM_ID
    values["javax.faces.ViewState"] = _view_state(body)
    return _FormState(form=form, action_url=action, values=values)


def _option_value(
    form: _Node,
    select_name: str,
    expected_label: str,
    *,
    allow_placeholder: bool = False,
) -> str:
    select = next(
        (
            node
            for node in [form, *form.descendants("select")]
            if node.tag == "select" and node.attrs.get("name") == select_name
        ),
        None,
    )
    if select is None:
        raise TcmBaContractError(f"Campo dependente ausente: {select_name}.")
    expected = _normalize(expected_label)
    for option in select.descendants("option"):
        if _normalize(option.text()) == expected:
            value = option.attrs.get("value", option.text())
            if value and (
                allow_placeholder
                or _normalize(value) != _normalize("Clique para selecionar")
            ):
                return value
    raise TcmBaContractError(
        f"Opção {expected_label!r} ausente no campo {select_name}."
    )


def _parse_submission(
    body: bytes, expected_competence: str
) -> tuple[TcmBaSubmission, str]:
    root = _parse_dom(body)
    tbody = _find_by_id(root, "consultaPublicaTabPanel:consultaPublicaDataTable:tb")
    if tbody is None:
        raise TcmBaContractError("Tabela de prestações do e-TCM não encontrada.")
    matches: list[tuple[TcmBaSubmission, str]] = []
    for row in _direct_children(tbody, "tr"):
        cells = _direct_children(row, "td")
        if len(cells) < 6:
            continue
        competence = cells[1].text()
        if competence != expected_competence:
            continue
        forms = cells[0].descendants("form")
        form_id = forms[0].attrs.get("id", "") if forms else ""
        if not form_id:
            raise TcmBaContractError("Prestação sem identificador de seleção.")
        matches.append(
            (
                TcmBaSubmission(
                    competence=competence,
                    type=cells[2].text(),
                    unit=cells[3].text(),
                    sent_at=cells[4].text(),
                    status=cells[5].text(),
                ),
                form_id,
            )
        )
    if len(matches) != 1:
        raise TcmBaContractError(
            "A consulta não devolveu exatamente uma prestação para a competência."
        )
    submission, form_id = matches[0]
    if _normalize(submission.unit) != _normalize("Prefeitura Municipal de BARREIRAS"):
        raise TcmBaContractError("A unidade retornada não é a Prefeitura de Barreiras.")
    return submission, form_id


def _parse_total_documents(body: bytes) -> int:
    text = _decode_partial(body)
    match = re.search(r"rowCount\s*:\s*(\d+)", text)
    if match is None:
        raise TcmBaContractError("Quantidade total de documentos não encontrada.")
    return int(match.group(1))


def _parse_pagination_form_id(body: bytes) -> str:
    root = _parse_dom(body)
    for form in root.descendants("form"):
        form_id = form.attrs.get("id", "")
        if not form_id or TABLE_ID in form_id:
            continue
        if any(node.attrs.get("name") == form_id for node in form.descendants("input")):
            return form_id
    raise TcmBaContractError("Formulário da paginação de documentos não encontrado.")


def _parse_documents(body: bytes, *, page_number: int) -> tuple[TcmBaDocument, ...]:
    root = _parse_dom(body)
    tbody = _find_by_id(root, f"{TABLE_ID}_data")
    if tbody is not None:
        rows = _direct_children(tbody, "tr")
    elif _contains_partial_update(body, TABLE_ID):
        # Nas páginas seguintes, o PrimeFaces devolve somente os <tr> que
        # substituem o corpo da tabela, sem repetir o <tbody>.
        rows = _direct_children(root, "tr")
        if not rows:
            raise TcmBaContractError(
                "Atualização da tabela de documentos veio sem linhas."
            )
    else:
        raise TcmBaContractError("Página sem tabela de documentos do e-TCM.")
    documents: list[TcmBaDocument] = []
    for row in rows:
        cells = _direct_children(row, "td")
        if len(cells) < 5:
            continue
        forms = cells[0].descendants("form")
        form_id = forms[0].attrs.get("id", "") if forms else ""
        name = cells[2].text()
        if not form_id or not name.lower().endswith(".pdf"):
            raise TcmBaContractError(
                "Documento sem formulário ou nome PDF verificável."
            )
        documents.append(
            TcmBaDocument(
                category=cells[1].text(),
                name=name,
                inserted_at=cells[4].text(),
                page_number=page_number,
                download_form_id=form_id,
            )
        )
    return tuple(documents)


def _parse_download_url(body: bytes) -> str:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise TcmBaContractError(
            "Preparação do download não veio como XML UTF-8."
        ) from error
    matches = re.findall(
        r"window\.open\(\s*(['\"])([^'\"]+)\1\s*\)",
        text,
    )
    if len(matches) != 1:
        raise TcmBaContractError(
            "Preparação do download não contém um único endereço verificável."
        )
    target = urljoin(BASE_URL, matches[0][1])
    validate_https_url(target, ALLOWED_HOSTS)
    if target != DOWNLOAD_URL:
        raise TcmBaContractError("Endpoint inesperado na preparação do download.")
    return target


def _response_media_type(headers: Mapping[str, str]) -> str:
    for key, value in headers.items():
        if key.casefold() == "content-type":
            return value.split(";", 1)[0].strip().casefold()
    return ""


def _contains_partial_update(body: bytes, update_id: str) -> bool:
    text = body.decode("utf-8", errors="replace")
    return (
        re.search(
            rf"<update\b[^>]*\bid=[\"']{re.escape(update_id)}[\"']",
            text,
        )
        is not None
    )


def _parse_dom(body: bytes) -> _Node:
    parser = _DomParser()
    parser.feed(_decode_partial(body))
    parser.close()
    return parser.root


def _decode_partial(body: bytes) -> str:
    text = body.decode("utf-8", errors="replace")
    cdata = re.findall(r"<!\[CDATA\[(.*?)\]\]>", text, flags=re.DOTALL)
    return "\n".join(cdata) if cdata else text


def _view_state(body: bytes) -> str:
    text = body.decode("utf-8", errors="replace")
    matches = re.findall(
        r"(?:name|id)=[\"']javax\.faces\.ViewState[\"'][^>]*"
        r"(?:value=[\"']([^\"']*)[\"'])?|"
        r"<update[^>]+id=[\"']javax\.faces\.ViewState[\"'][^>]*>"
        r"(?:<!\[CDATA\[)?([^<\]]+)",
        text,
        flags=re.DOTALL,
    )
    for attribute_value, update_value in reversed(matches):
        value = (attribute_value or update_value).strip()
        if value:
            return value
    root = _parse_dom(body)
    for node in root.descendants("input"):
        if node.attrs.get("name") == "javax.faces.ViewState":
            value = node.attrs.get("value", "")
            if value:
                return value
    raise TcmBaContractError("javax.faces.ViewState ausente na resposta do e-TCM.")


def _find_by_id(root: _Node, node_id: str) -> _Node | None:
    return next(
        (
            node
            for node in [root, *root.descendants()]
            if node.attrs.get("id") == node_id
        ),
        None,
    )


def _direct_children(node: _Node, tag: str) -> list[_Node]:
    return [child for child in node.children if child.tag == tag]


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return " ".join(
        "".join(char for char in decomposed if not unicodedata.combining(char))
        .casefold()
        .split()
    )


def _ajax_change_fields(component: str) -> dict[str, str]:
    source = component.removesuffix("_input")
    return {
        "javax.faces.partial.ajax": "true",
        "javax.faces.source": source,
        "javax.faces.partial.event": "change",
        "javax.faces.behavior.event": "change",
        "javax.faces.partial.execute": source,
        "javax.faces.partial.render": FORM_ID,
        source: source,
    }


def _ajax_click_fields(component: str) -> dict[str, str]:
    return {
        "javax.faces.partial.ajax": "true",
        "javax.faces.source": component,
        "javax.faces.partial.event": "click",
        "javax.faces.partial.execute": f"{component} @component",
        "javax.faces.partial.render": "@component",
        "org.richfaces.ajax.component": component,
        component: component,
        "rfExt": "null",
        "AJAX:EVENTS_COUNT": "1",
    }


def _request_headers(*, ajax: bool = False) -> dict[str, str]:
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "User-Agent": "Barreiras360-Collector/0.1 (+public-data-audit)",
    }
    if ajax:
        headers.update(
            {
                "Accept": "application/xml, text/xml, */*; q=0.01",
                "Faces-Request": "partial/ajax",
                "Origin": "https://e.tcm.ba.gov.br",
                "Referer": BASE_URL,
                "X-Requested-With": "XMLHttpRequest",
            }
        )
    return headers


def _safe_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        str(key).lower(): str(value)
        for key, value in headers.items()
        if str(key).lower() in SAFE_RESPONSE_HEADERS
    }
