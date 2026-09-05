"""Register already-preserved FNS originals; never approve or publish a link."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime
from urllib.parse import parse_qsl, urlsplit

from ..connectors.fns_payment_evidence import parse_fns_payment_evidence
from ..connectors.querido_diario import CollectedPage
from .models import ArtifactIntegrityError, PersistenceBatch, RepositoryPersistResult

VERSION = "fns-preserved-pair/1.0.0"
BASE = "/recursos/consulta-detalhada/"


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError("Invalid captured FNS response")


def _validate(page: CollectedPage, endpoint: str, expected: dict[str, str]) -> None:
    try:
        route = (
            "detalhe-pagamento"
            if endpoint == "payment-detail"
            else "detalhe-ordem-bancaria"
        )
        allowed = (
            {
                "ano",
                "tipoConsulta",
                "estado",
                "municipio",
                "cnpj",
                "acoes",
                "page",
                "count",
            }
            if endpoint == "payment-detail"
            else {
                "anoPagamento",
                "ano",
                "mes",
                "competencia",
                "uf",
                "numeroDocumentoSiafi",
                "tipoDocumentoPagamento",
                "page",
                "count",
            }
        )
        _require(page.source_code == "fns-consulta-detalhada")
        _require(page.endpoint_code == endpoint)
        _require(type(page.http_status) is int and 200 <= page.http_status < 300)
        _require(page.media_type == "application/json")
        _require(type(page.raw_body) is bytes and bool(page.raw_body))
        _require(hashlib.sha256(page.raw_body).hexdigest() == page.body_sha256)
        _require(
            type(page.body_size_bytes) is int
            and len(page.raw_body) == page.body_size_bytes
        )
        _require(type(page.attempts) is int and page.attempts > 0)
        start, end = (
            datetime.fromisoformat(page.requested_at),
            datetime.fromisoformat(page.received_at),
        )
        _require(
            start.utcoffset() is not None
            and end.utcoffset() is not None
            and end >= start
        )
        for raw_url in (page.request_url, page.final_url):
            url = urlsplit(raw_url)
            _require(url.scheme == "https" and url.netloc == "consultafns.saude.gov.br")
            _require(url.path == BASE + route and not url.fragment)
            pairs = parse_qsl(url.query, keep_blank_values=True, strict_parsing=True)
            query = dict(pairs)
            _require(len(query) == len(pairs) and set(query) <= allowed)
            _require(all(query.get(key) == value for key, value in expected.items()))
            if "page" in query:
                _require(query["page"] == "1")
            if "count" in query:
                _require(query["count"] in ("10", "25"))
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise ArtifactIntegrityError(
            "Metadados FNS incompatíveis com o original ou com o escopo do par."
        ) from None


class FNSPairPersistenceService:
    """Verify both objects before writing raw lineage through the existing repository.

    Captures must carry their original URLs/timestamps, not import-time metadata.
    No request, upload, annual coverage, normalized bank fields or review decision
    is made here. Each artifact transaction is idempotent: if the second fails,
    replay recovers the pair without pretending the first was rolled back.
    """

    def __init__(self, *, object_store, repository) -> None:
        self.object_store = object_store
        self.repository = repository

    def persist(
        self,
        *,
        payment: CollectedPage,
        order: CollectedPage,
        action_id: int,
        payment_year: int,
        order_number: str,
    ) -> tuple[RepositoryPersistResult, RepositoryPersistResult]:
        evidence = parse_fns_payment_evidence(
            payment.raw_body,
            order.raw_body,
            action_id=action_id,
            payment_year=payment_year,
            order_number=order_number,
        )
        _validate(
            payment,
            "payment-detail",
            {
                "ano": str(payment_year),
                "acoes": str(action_id),
                "tipoConsulta": "2",
                "estado": "BA",
                "municipio": "290320",
                "cnpj": "08595187000125",
            },
        )
        _validate(
            order,
            "payment-order-detail",
            {
                "anoPagamento": str(payment_year),
                "ano": str(payment_year),
                "mes": evidence["document_date"][5:7],
                "uf": "BA",
                "numeroDocumentoSiafi": order_number,
                "tipoDocumentoPagamento": "OB",
            },
        )
        batches = []
        for capture in (payment, order):
            sha = capture.body_sha256
            key = f"fns/payments/{payment_year}/sha256/{sha[:2]}/{sha}.json"
            restored = self.object_store.read(key)
            if restored != capture.raw_body:
                raise ArtifactIntegrityError(
                    "Original FNS restaurado diverge da captura."
                )
            # The caller cannot collide keys with another source or capture.
            identity = f"{VERSION}:{capture.endpoint_code}:{sha}"
            page = replace(
                capture,
                idempotency_key=hashlib.sha256(identity.encode()).hexdigest(),
                schema_name="fns-payment-response",
                schema_version="1.0.0",
                response_headers={},
                cursor={},
                parsed=None,
                collection_status="partial",
                window_start=None,
                window_end=None,
            )
            batches.append(
                PersistenceBatch(
                    page=page,
                    object_key=key,
                    artifact_idempotency_key=hashlib.sha256(
                        f"raw:{identity}".encode()
                    ).hexdigest(),
                    collector_version=VERSION,
                    parser_version="fns-payment-evidence-v1",
                    records=(),
                )
            )
        return self.repository.persist(batches[0]), self.repository.persist(batches[1])
