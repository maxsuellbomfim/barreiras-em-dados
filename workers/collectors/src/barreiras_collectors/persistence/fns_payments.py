"""Private FNS observations with immutable original lineage; no publication."""

import hashlib
import json
from dataclasses import replace

from ..connectors.fns_payment_pages import normalize_payment_pages
from .fns import _require, _validate
from .models import ArtifactIntegrityError, PersistenceBatch, RawRecordInput

VERSION = "fns-payment-observations/1.0.0"


class FNSPaymentPagesPersistenceService:
    """Verify a complete action before any write; replay is per-page idempotent.

    No upload, public financial row, editorial decision or annual coverage is
    produced. A rejected observation is retained for review, never dropped.
    """

    def __init__(self, *, object_store, repository):
        self.object_store = object_store
        self.repository = repository

    def persist(self, *, pages, action_id: int, payment_year: int):
        try:
            _require(isinstance(pages, list) and 0 < len(pages) <= 100)
            report = normalize_payment_pages(
                [p.raw_body for p in pages],
                action_id=action_id,
                payment_year=payment_year,
            )
            _require(report["status"] != "invalid_pages")
            for index, p in enumerate(pages):
                count = json.loads(p.raw_body)["resultado"]["itensPorPagina"]
                _validate(
                    p,
                    "payment-detail",
                    dict(
                        ano=str(payment_year),
                        tipoConsulta="2",
                        estado="BA",
                        municipio="290320",
                        cpfCnpjUg="08595187000125",
                        acoes=str(action_id),
                        page=str(index + 1),
                        count=str(count),
                    ),
                    paginated=True,
                )
        except (ValueError, TypeError, KeyError, AttributeError):
            raise ArtifactIntegrityError(
                "Capturas de pagamentos FNS invalidas."
            ) from None
        context = hashlib.sha256("\n".join(report["page_sha256"]).encode()).hexdigest()
        batches = []
        for index, capture in enumerate(pages):
            sha = capture.body_sha256
            key = f"fns/payments/{payment_year}/sha256/{sha[:2]}/{sha}.json"
            if self.object_store.read(key) != capture.raw_body:
                raise ArtifactIntegrityError(
                    "Original FNS restaurado diverge da captura."
                )
            identity = (
                f"{VERSION}:{payment_year}:{action_id}:{context}:{index + 1}:{sha}"
            )
            rows = []
            for observation in report["records"]:
                if observation["source_page"] != index + 1:
                    continue
                payload_hash = hashlib.sha256(
                    json.dumps(
                        observation,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest()
                rows.append(
                    RawRecordInput(
                        source_record_key=observation["document_key"],
                        record_type="fns_payment_observation",
                        record_index=observation["source_row"] - 1,
                        payload=observation,
                        payload_sha256=payload_hash,
                        parser_version=VERSION,
                        idempotency_key=hashlib.sha256(
                            f"{identity}:{observation['source_row']}:{payload_hash}".encode()
                        ).hexdigest(),
                    )
                )
            sanitized = replace(
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
                    page=sanitized,
                    object_key=key,
                    artifact_idempotency_key=hashlib.sha256(
                        f"raw:{identity}".encode()
                    ).hexdigest(),
                    collector_version=VERSION,
                    parser_version=VERSION,
                    records=tuple(rows),
                )
            )
        return report, tuple(self.repository.persist(batch) for batch in batches)
