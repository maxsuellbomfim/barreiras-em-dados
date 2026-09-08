"""Append-only private documentary comparisons; never approve a payment."""

import hashlib
import json
from dataclasses import replace

from ..connectors.fns_document_link import inspect_document_link
from .fns import FNSOrderPersistenceService, _require
from .fns_payments import FNSPaymentPagesPersistenceService
from .models import ArtifactIntegrityError, RawRecordInput

VERSION = "fns-document-comparison/1.0.0"


class _ValidationRepository:
    """Reuse acquisition validation without writing intermediate observations."""

    def persist(self, batch):
        return batch


class FNSComparisonPersistenceService:
    """Read both complete originals before one immutable private write.

    The caller preserves originals first. Existing observations/decisions are
    never updated. A compatible pair is not financial execution or authorship.
    """

    def __init__(self, *, object_store, repository):
        self.object_store = object_store
        self.repository = repository

    def persist(
        self, *, payment_pages, order_pages, action_id, payment_year, order_number
    ):
        validation = _ValidationRepository()
        normalized, batches = FNSPaymentPagesPersistenceService(
            object_store=self.object_store, repository=validation
        ).persist(pages=payment_pages, action_id=action_id, payment_year=payment_year)
        try:
            candidates = [
                r
                for r in normalized["records"]
                if r["order_scope"]["numeroDocumentoSiafi"] == order_number
            ]
            _require(len(candidates) == 1)
            observation = candidates[0]
            FNSOrderPersistenceService(
                object_store=self.object_store, repository=validation
            ).persist(pages=order_pages, scope=observation["order_scope"])
            result = inspect_document_link(
                [p.raw_body for p in payment_pages],
                [
                    dict(
                        body=p.raw_body,
                        sha256=p.body_sha256,
                        http_status=p.http_status,
                        url=p.final_url,
                    )
                    for p in order_pages
                ],
                action_id=action_id,
                payment_year=payment_year,
                order_number=order_number,
            )
            _require(result.get("document_key") == observation["document_key"])
            _require(
                result["status"]
                in {
                    "consistent_documentary_pair",
                    "review_required",
                    "document_conflict",
                    "order_not_found",
                    "order_ambiguous",
                    "order_territory_conflict",
                }
            )
        except (ValueError, TypeError, KeyError, AttributeError, IndexError):
            raise ArtifactIntegrityError(
                "Comparacao documental FNS invalida."
            ) from None

        def evidence(pages):
            return [
                dict(
                    sha256=p.body_sha256,
                    request_url=p.request_url,
                    final_url=p.final_url,
                )
                for p in pages
            ]

        payload = dict(
            result,
            action_id=action_id,
            payment_year=payment_year,
            order_scope=observation["order_scope"],
            methodology_version=VERSION,
            payment_evidence=evidence(payment_pages),
            order_evidence=evidence(order_pages),
        )
        payload_hash = hashlib.sha256(
            json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        identity = hashlib.sha256(f"{VERSION}:{payload_hash}".encode()).hexdigest()
        original = batches[result["payment_page"] - 1]
        record = RawRecordInput(
            source_record_key=result["document_key"],
            record_type="fns_document_comparison",
            record_index=result["payment_row"] - 1,
            payload=payload,
            payload_sha256=payload_hash,
            parser_version=VERSION,
            idempotency_key=identity,
        )
        batch = replace(
            original,
            page=replace(original.page, idempotency_key=identity),
            artifact_idempotency_key=hashlib.sha256(
                f"raw:{identity}".encode()
            ).hexdigest(),
            collector_version=VERSION,
            parser_version=VERSION,
            records=(record,),
        )
        return payload, self.repository.persist(batch)
