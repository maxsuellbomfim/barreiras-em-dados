"""Register already-preserved FNS originals; never approve or publish a link."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime
from urllib.parse import parse_qsl, urlsplit

from ..connectors.fns_order_pages import inspect_order_captures
from ..connectors.fns_payment_evidence import parse_fns_payment_evidence
from ..connectors.querido_diario import CollectedPage
from .models import ArtifactIntegrityError, PersistenceBatch, RepositoryPersistResult

VERSION = "fns-preserved-pair/1.0.0"
BASE = "/recursos/consulta-detalhada/"


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError("Invalid captured FNS response")


def _validate(
    page: CollectedPage,
    endpoint: str,
    expected: dict[str, str],
    *,
    paginated: bool = False,
) -> None:
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
                "cpfCnpjUg",
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
            if "page" in query and not paginated:
                _require(query["page"] == "1")
            if "count" in query and not paginated:
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
                "cpfCnpjUg": "08595187000125",
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


class FNSOrderPersistenceService:
    """Register a complete captured OB, never a financial record or approval.

    All metadata and stored bytes are verified before the first write. Writes
    are individually idempotent, not one transaction; replay recovers failures.
    Even a complete OB is only partial source coverage. Rejection/absence and
    territorial conflicts are preserved as originals, not silently discarded.
    """

    def __init__(self, *, object_store, repository) -> None:
        self.object_store = object_store
        self.repository = repository

    def persist(self, *, pages: list[CollectedPage], scope: dict[str, str]):
        try:
            _require(isinstance(pages, list) and 0 < len(pages) <= 100)
            captures = [
                dict(
                    url=p.final_url,
                    body=p.raw_body,
                    sha256=p.body_sha256,
                    http_status=p.http_status,
                )
                for p in pages
            ]
            diagnostic = inspect_order_captures(captures, scope)
            _require(diagnostic["status"] not in ("invalid_capture", "invalid_pages"))
            for p in pages:
                _validate(p, "payment-order-detail", scope, paginated=True)
            requests = [
                dict(c, url=p.request_url) for c, p in zip(captures, pages, strict=True)
            ]
            _require(inspect_order_captures(requests, scope) == diagnostic)
            year = scope["anoPagamento"]
            _require(len(year) == 4 and year.isascii() and year.isdigit())
        except (ValueError, TypeError, KeyError, AttributeError):
            raise ArtifactIntegrityError("Capturas paginadas FNS invalidas.") from None

        version = "fns-preserved-order/1.0.0"
        scope_hash = hashlib.sha256(
            json.dumps(scope, sort_keys=True).encode()
        ).hexdigest()
        batches = []
        for index, capture in enumerate(pages):
            sha = capture.body_sha256
            key = f"fns/payments/{year}/sha256/{sha[:2]}/{sha}.json"
            if self.object_store.read(key) != capture.raw_body:
                raise ArtifactIntegrityError(
                    "Original FNS restaurado diverge da captura."
                )
            identity = f"{version}:{scope_hash}:{index + 1}:{sha}"
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
                    collector_version=version,
                    parser_version="fns-order-pages-v1",
                    records=(),
                )
            )
        return diagnostic, tuple(self.repository.persist(batch) for batch in batches)
