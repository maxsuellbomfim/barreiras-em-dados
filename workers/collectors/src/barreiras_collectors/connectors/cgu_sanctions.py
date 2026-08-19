"""Sanções federais (CEIS/CNEP/CEPIM/leniência) por CNPJ de fornecedor.

A consulta é sempre dirigida: apenas CNPJs que já aparecem nas contratações
publicadas de Barreiras são verificados. O registro espelha o cadastro oficial
da CGU e nunca vira acusação. Pessoas físicas retornadas pela API — o CEIS
expõe CPF integral em ``sancionado.codigoFormatado`` e o CEPIM expõe
``cpfFormatado`` — jamais entram nos itens materializados; permanecem apenas
contadas e no bruto privado. O CEAF fica fora por definição: é consulta por
CPF de pessoa física, vedada pelo gate de dados pessoais do projeto.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from ..http import (
    RETRYABLE_TRANSPORT_EXCEPTIONS,
    HttpTransport,
    UrllibTransport,
)
from ..logging import log_event
from ..resilience import CircuitBreaker, RetryPolicy

SOURCE_CODE = "cgu-portal-transparencia"
ENDPOINT_CODE = "sanctions-api"
BASE_URL = "https://api.portaldatransparencia.gov.br/api-de-dados"
OFFICIAL_HOSTS = frozenset({"api.portaldatransparencia.gov.br"})
REGISTRIES = ("ceis", "cnep", "cepim", "leniencia")
# Caminho e nome do parâmetro de CNPJ variam por cadastro na API oficial.
_REGISTRY_REQUESTS = {
    "ceis": ("ceis", "codigoSancionado"),
    "cnep": ("cnep", "codigoSancionado"),
    "cepim": ("cepim", "cnpjSancionado"),
    "leniencia": ("acordos-leniencia", "cnpjSancionado"),
}
API_PAGE_SIZE = 15
MAX_PAGES_PER_QUERY = 5
TIMEOUT_SECONDS = 60.0
MAX_BODY_BYTES = 8 * 1024 * 1024
REQUEST_INTERVAL_SECONDS = 1.2
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
SAFE_RESPONSE_HEADERS = frozenset({"content-type", "date"})
_CNPJ = re.compile(r"^\d{14}$")


class CGUSanctionError(RuntimeError):
    """Falha explícita de contrato, autenticação ou disponibilidade."""


@dataclass(frozen=True)
class CGUSanctionSnapshot:
    schema_name: str
    schema_version: str
    artifact_kind: str
    source_code: str
    endpoint_code: str
    idempotency_key: str
    request_url: str
    final_url: str
    requested_at: str
    received_at: str
    window_start: str
    window_end: str
    attempts: int
    http_status: int
    collection_status: str
    body_sha256: str
    body_size_bytes: int
    media_type: str
    response_headers: dict[str, str]
    cursor: dict[str, int]
    raw_body: bytes
    items: tuple[dict[str, object], ...]
    total_pages: int
    total_items: int
    queried_cnpjs: int
    sanctioned_cnpjs: int
    skipped_natural_persons: int


def _text(value: object) -> str:
    return str(value).strip() if isinstance(value, (str, int)) else ""


def _nested(record: dict, *path: str) -> object:
    current: object = record
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _document_digits(record: dict) -> str:
    return re.sub(r"\D", "", _text(_nested(record, "sancionado", "codigoFormatado")))


def _normalize_item(registry: str, cnpj: str, record: dict) -> dict[str, object]:
    legal_basis = record.get("fundamentacao")
    codes: list[str] = []
    if isinstance(legal_basis, list):
        for entry in legal_basis:
            code = _text(entry.get("codigo")) if isinstance(entry, dict) else ""
            if code:
                codes.append(code)
    return {
        "registry": registry,
        "sanction_id": _text(record.get("id")),
        "supplier_cnpj": cnpj,
        "sanctioned_document": _document_digits(record),
        "sanctioned_name": _text(_nested(record, "sancionado", "nome")),
        "person_type": _text(_nested(record, "pessoa", "tipo")),
        "company_name": _text(_nested(record, "pessoa", "razaoSocialReceita")),
        "sanction_type": _text(
            _nested(record, "tipoSancao", "descricaoResumida")
        ),
        "sanctioning_body": _text(_nested(record, "orgaoSancionador", "nome")),
        "sanctioning_body_sphere": _text(
            _nested(record, "orgaoSancionador", "esfera")
        ),
        "sanctioning_body_uf": _text(
            _nested(record, "orgaoSancionador", "siglaUf")
        ),
        "sanction_source": _text(_nested(record, "fonteSancao", "nomeExibicao")),
        "process_number": _text(record.get("numeroProcesso")),
        "start_date_text": _text(record.get("dataInicioSancao")),
        "end_date_text": _text(record.get("dataFimSancao")),
        "publication_date_text": _text(record.get("dataPublicacaoSancao")),
        "reference_date_text": _text(record.get("dataReferencia")),
        "legal_basis_codes": codes,
    }


def _normalize_cepim_item(cnpj: str, record: dict) -> dict[str, object]:
    return {
        "registry": "cepim",
        "sanction_id": _text(record.get("id")),
        "supplier_cnpj": cnpj,
        "sanctioned_document": re.sub(
            r"\D", "", _text(_nested(record, "pessoaJuridica", "cnpjFormatado"))
        ),
        "sanctioned_name": _text(_nested(record, "pessoaJuridica", "nome"))
        or _text(_nested(record, "pessoaJuridica", "razaoSocialReceita")),
        "person_type": _text(_nested(record, "pessoaJuridica", "tipo")),
        "company_name": _text(
            _nested(record, "pessoaJuridica", "razaoSocialReceita")
        ),
        "sanction_type": _text(record.get("motivo")),
        "sanctioning_body": _text(_nested(record, "orgaoSuperior", "nome")),
        "sanctioning_body_sphere": _text(
            _nested(record, "orgaoSuperior", "descricaoPoder")
        ),
        "sanctioning_body_uf": "",
        "sanction_source": "",
        "process_number": "",
        "start_date_text": "",
        "end_date_text": "",
        "publication_date_text": "",
        "reference_date_text": _text(record.get("dataReferencia")),
        "legal_basis_codes": [],
    }


def _normalize_leniency_items(cnpj: str, record: dict) -> list[dict[str, object]]:
    """Materializa o acordo somente para a empresa com o CNPJ consultado."""
    companies = record.get("sancoes")
    if not isinstance(companies, list):
        return []
    for company in companies:
        if not isinstance(company, dict):
            continue
        digits = re.sub(
            r"\D",
            "",
            _text(company.get("cnpjFormatado")) or _text(company.get("cnpj")),
        )
        if digits != cnpj:
            continue
        return [
            {
                "registry": "leniencia",
                "sanction_id": _text(record.get("id")),
                "supplier_cnpj": cnpj,
                "sanctioned_document": digits,
                "sanctioned_name": _text(company.get("razaoSocial"))
                or _text(company.get("nomeInformadoOrgaoResponsavel"))
                or _text(company.get("nomeFantasia")),
                "person_type": "",
                "company_name": _text(company.get("razaoSocial")),
                "sanction_type": _text(record.get("situacaoAcordo")),
                "sanctioning_body": _text(record.get("orgaoResponsavel")),
                "sanctioning_body_sphere": "",
                "sanctioning_body_uf": "",
                "sanction_source": "",
                "process_number": "",
                "start_date_text": _text(record.get("dataInicioAcordo")),
                "end_date_text": _text(record.get("dataFimAcordo")),
                "publication_date_text": "",
                "reference_date_text": "",
                "legal_basis_codes": [],
            }
        ]
    return []


def _materialize_records(
    registry: str, cnpj: str, record: dict
) -> tuple[list[dict[str, object]], int]:
    """Retorna (itens materializáveis, descartados por PF ou sem o CNPJ)."""
    if registry in ("ceis", "cnep"):
        digits = _document_digits(record)
        person_type = _text(_nested(record, "pessoa", "tipo"))
        if len(digits) != 14 or person_type == "Pessoa Física":
            return [], 1
        return [_normalize_item(registry, cnpj, record)], 0
    if registry == "cepim":
        item = _normalize_cepim_item(cnpj, record)
        if (
            len(str(item["sanctioned_document"])) != 14
            or item["person_type"] == "Pessoa Física"
        ):
            return [], 1
        return [item], 0
    leniency_items = _normalize_leniency_items(cnpj, record)
    if not leniency_items:
        return [], 1
    return leniency_items, 0


def parse_cgu_sanctions_bundle(
    raw_body: bytes,
) -> tuple[tuple[dict[str, object], ...], int]:
    """Reconstrói itens do pacote preservado.

    Retorna ``(itens, descartados)``: descartados cobrem pessoa física (CEIS,
    CNEP e CEPIM nunca materializam PF) e acordos de leniência devolvidos pela
    API sem empresa correspondente ao CNPJ consultado.
    """
    try:
        bundle = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CGUSanctionError("O pacote preservado não é JSON válido.") from error
    if not isinstance(bundle, list):
        raise CGUSanctionError("O pacote preservado perdeu seu contrato.")
    items: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    skipped_natural_persons = 0
    for query in bundle:
        if not isinstance(query, dict):
            raise CGUSanctionError("Consulta preservada em formato inesperado.")
        registry = _text(query.get("registry"))
        cnpj = _text(query.get("cnpj"))
        records = query.get("records")
        if (
            registry not in REGISTRIES
            or not _CNPJ.fullmatch(cnpj)
            or not isinstance(records, list)
        ):
            raise CGUSanctionError("Consulta preservada em formato inesperado.")
        for record in records:
            if not isinstance(record, dict):
                raise CGUSanctionError("Sanção preservada em formato inesperado.")
            materialized, skipped = _materialize_records(registry, cnpj, record)
            skipped_natural_persons += skipped
            for item in materialized:
                if not item["sanction_id"]:
                    raise CGUSanctionError("Sanção preservada sem identificador.")
                identity = (registry, str(item["sanction_id"]), cnpj)
                if identity in seen:
                    raise CGUSanctionError(
                        "Sanção duplicada no pacote: "
                        f"{registry}:{item['sanction_id']}."
                    )
                seen.add(identity)
                items.append(item)
    return tuple(items), skipped_natural_persons


def fetch_cgu_supplier_sanctions(
    *,
    cnpjs: Sequence[str],
    api_key: str,
    transport: HttpTransport | None = None,
    retry_policy: RetryPolicy | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    random_value: Callable[[], float] = random.random,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
    request_interval_seconds: float = REQUEST_INTERVAL_SECONDS,
    logger: logging.Logger | None = None,
) -> CGUSanctionSnapshot:
    """Consulta CEIS e CNEP para cada CNPJ publicado, com ritmo respeitoso."""
    if not api_key or not api_key.strip():
        raise CGUSanctionError(
            "A chave da API do Portal da Transparência não foi configurada."
        )
    unique_cnpjs = sorted({cnpj.strip() for cnpj in cnpjs})
    if not unique_cnpjs:
        raise CGUSanctionError("Nenhum CNPJ de fornecedor publicado para consultar.")
    for cnpj in unique_cnpjs:
        if not _CNPJ.fullmatch(cnpj):
            raise CGUSanctionError("A consulta de sanções aceita somente CNPJ.")

    active_transport = transport or UrllibTransport(OFFICIAL_HOSTS)
    policy = retry_policy or RetryPolicy(max_attempts=4)
    breaker = circuit_breaker or CircuitBreaker(
        failure_threshold=policy.max_attempts
    )
    log = logger or logging.getLogger(__name__)
    headers = {
        "Accept": "application/json",
        "User-Agent": "Barreiras360-Collector/0.1",
        "chave-api-dados": api_key.strip(),
    }

    requested_at = now().isoformat()
    bundle: list[dict[str, object]] = []
    total_requests = 0
    for cnpj in unique_cnpjs:
        for registry in REGISTRIES:
            path, cnpj_parameter = _REGISTRY_REQUESTS[registry]
            page = 1
            while page <= MAX_PAGES_PER_QUERY:
                url = (
                    f"{BASE_URL}/{path}"
                    f"?{cnpj_parameter}={cnpj}&pagina={page}"
                )
                records = _fetch_page(
                    url,
                    headers=headers,
                    transport=active_transport,
                    policy=policy,
                    breaker=breaker,
                    random_value=random_value,
                    sleep=sleep,
                    log=log,
                    registry=registry,
                )
                total_requests += 1
                bundle.append(
                    {
                        "registry": registry,
                        "cnpj": cnpj,
                        "page": page,
                        "records": records,
                    }
                )
                if total_requests and request_interval_seconds > 0:
                    sleep(request_interval_seconds)
                if len(records) < API_PAGE_SIZE:
                    break
                page += 1
            else:
                raise CGUSanctionError(
                    f"Sanções de {registry} excederam o limite defensivo de páginas."
                )

    received_at = now().isoformat()
    raw_body = json.dumps(
        bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    items, skipped_natural_persons = parse_cgu_sanctions_bundle(raw_body)
    body_sha256 = hashlib.sha256(raw_body).hexdigest()
    sanctioned = {str(item["supplier_cnpj"]) for item in items}
    return CGUSanctionSnapshot(
        schema_name="cgu-supplier-sanctions-bundle",
        schema_version="1.1.0",
        artifact_kind="http_response",
        source_code=SOURCE_CODE,
        endpoint_code=ENDPOINT_CODE,
        idempotency_key=hashlib.sha256(
            f"cgu-sanctions:{body_sha256}".encode()
        ).hexdigest(),
        request_url=f"{BASE_URL}/ceis",
        final_url=f"{BASE_URL}/ceis",
        requested_at=requested_at,
        received_at=received_at,
        window_start=requested_at,
        window_end=received_at,
        attempts=1,
        http_status=200,
        collection_status="complete",
        body_sha256=body_sha256,
        body_size_bytes=len(raw_body),
        media_type="application/json",
        response_headers={},
        cursor={"offset": 0, "size": len(items)},
        raw_body=raw_body,
        items=items,
        total_pages=total_requests,
        total_items=len(items),
        queried_cnpjs=len(unique_cnpjs),
        sanctioned_cnpjs=len(sanctioned),
        skipped_natural_persons=skipped_natural_persons,
    )


def _fetch_page(
    url: str,
    *,
    headers: dict[str, str],
    transport: HttpTransport,
    policy: RetryPolicy,
    breaker: CircuitBreaker,
    random_value: Callable[[], float],
    sleep: Callable[[float], None],
    log: logging.Logger,
    registry: str,
) -> list[dict]:
    for attempt in range(1, policy.max_attempts + 1):
        breaker.before_request()
        try:
            response = transport.get(
                url,
                headers=headers,
                timeout_seconds=TIMEOUT_SECONDS,
                max_body_bytes=MAX_BODY_BYTES,
            )
        except RETRYABLE_TRANSPORT_EXCEPTIONS as error:
            breaker.record_failure()
            if attempt < policy.max_attempts:
                sleep(policy.delay(attempt, random_value()))
                continue
            raise CGUSanctionError(
                "A API de sanções da CGU ficou indisponível."
            ) from error
        log_event(
            log,
            logging.INFO,
            "collector_http_response",
            source=SOURCE_CODE,
            endpoint=ENDPOINT_CODE,
            registry=registry,
            status=response.status,
            attempt=attempt,
            body_size_bytes=len(response.body),
        )
        if response.status == 200:
            breaker.record_success()
            try:
                payload = json.loads(response.body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise CGUSanctionError(
                    "A API de sanções respondeu fora do contrato JSON."
                ) from error
            if not isinstance(payload, list):
                raise CGUSanctionError(
                    "A API de sanções respondeu fora do contrato de lista."
                )
            return payload
        if response.status in (401, 403):
            raise CGUSanctionError(
                "A API de sanções recusou a chave configurada."
            )
        if response.status not in RETRYABLE_HTTP_STATUSES:
            raise CGUSanctionError(
                f"A API de sanções respondeu HTTP {response.status}."
            )
        breaker.record_failure()
        if attempt < policy.max_attempts:
            sleep(policy.delay(attempt, random_value()))
    raise CGUSanctionError("A API de sanções da CGU ficou indisponível.")
