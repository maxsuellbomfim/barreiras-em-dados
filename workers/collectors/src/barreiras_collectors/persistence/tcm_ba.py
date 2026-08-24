"""Preservação imutável do catálogo mensal do TCM-BA."""

from __future__ import annotations

import calendar
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date

from ..connectors.querido_diario import CollectedPage, GazettePage
from ..connectors.tcm_ba import (
    TcmBaInteraction,
    TcmBaMonthlyCatalog,
    validate_tcm_ba_catalog,
)
from .models import (
    ArtifactIntegrityError,
    PersistenceBatch,
    RawRecordInput,
)

TCM_BA_COLLECTOR_VERSION = "tcm-ba-monthly-catalog-collector/1.0.0"
TCM_BA_PARSER_VERSION = "tcm-ba-monthly-catalog/1.0.0"


@dataclass(frozen=True)
class TcmBaCatalogPersistenceSummary:
    artifacts: int
    inserted_records: int
    existing_records: int
    object_keys: tuple[str, ...]
    artifact_hashes: tuple[str, ...]


class TcmBaCatalogPersistenceService:
    """Preserva cada resposta JSF antes de emitir o catálogo normalizado."""

    def __init__(self, *, object_store, repository) -> None:
        self.object_store = object_store
        self.repository = repository

    def persist(self, catalog: TcmBaMonthlyCatalog) -> TcmBaCatalogPersistenceSummary:
        validate_tcm_ba_catalog(catalog)
        month, year = (int(part) for part in catalog.competence.split("/"))
        period_start = date(year, month, 1)
        period_end = date(year, month, calendar.monthrange(year, month)[1])
        inserted_records = 0
        existing_records = 0
        object_keys: list[str] = []
        artifact_hashes: list[str] = []

        for stage_index, interaction in enumerate(catalog.interactions):
            records = self._records_for_interaction(catalog, interaction)
            page_number = self._page_number(interaction.stage)
            page = CollectedPage(
                schema_name="tcm-ba-monthly-public-accounts-interaction",
                schema_version="1.0.0",
                source_code=catalog.source_code,
                endpoint_code=catalog.endpoint_code,
                idempotency_key=self._digest(
                    "\x1f".join(
                        (
                            "tcm-ba-interaction",
                            catalog.competence,
                            interaction.stage,
                            interaction.body_sha256,
                        )
                    )
                ),
                request_url=interaction.request_url,
                final_url=interaction.final_url,
                requested_at=interaction.received_at,
                received_at=interaction.received_at,
                attempts=1,
                http_status=interaction.http_status,
                collection_status="succeeded",
                body_sha256=interaction.body_sha256,
                body_size_bytes=len(interaction.raw_body),
                media_type=self._media_type(interaction),
                response_headers=interaction.response_headers,
                cursor={"stage_index": stage_index, "page": page_number},
                raw_body=interaction.raw_body,
                parsed=GazettePage(
                    total_gazettes=len(records),
                    gazettes=(),
                    source_extensions={
                        "competence": catalog.competence,
                        "stage": interaction.stage,
                    },
                ),
                window_start=period_start.isoformat(),
                window_end=period_end.isoformat(),
            )
            object_key = (
                f"tcm-ba/monthly/{year}/{month:02d}/sha256/"
                f"{interaction.body_sha256[:2]}/{interaction.body_sha256}.html"
            )
            stored = self.object_store.put_if_absent(
                object_key=object_key,
                body=interaction.raw_body,
                content_type=page.media_type,
                expected_sha256=interaction.body_sha256,
            )
            restored = self.object_store.read(object_key)
            if (
                hashlib.sha256(restored).hexdigest() != interaction.body_sha256
                or len(restored) != len(interaction.raw_body)
                or stored.sha256 != interaction.body_sha256
                or stored.byte_size != len(interaction.raw_body)
            ):
                raise ArtifactIntegrityError(
                    "A resposta TCM-BA restaurada diverge da coletada."
                )
            persisted = self.repository.persist(
                PersistenceBatch(
                    page=page,
                    object_key=object_key,
                    artifact_idempotency_key=self._digest(
                        f"raw-artifact:{page.idempotency_key}"
                    ),
                    collector_version=TCM_BA_COLLECTOR_VERSION,
                    parser_version=TCM_BA_PARSER_VERSION,
                    records=records,
                )
            )
            inserted_records += persisted.inserted_records
            existing_records += persisted.existing_records
            object_keys.append(object_key)
            artifact_hashes.append(interaction.body_sha256)

        return TcmBaCatalogPersistenceSummary(
            artifacts=len(catalog.interactions),
            inserted_records=inserted_records,
            existing_records=existing_records,
            object_keys=tuple(object_keys),
            artifact_hashes=tuple(artifact_hashes),
        )

    def _records_for_interaction(
        self,
        catalog: TcmBaMonthlyCatalog,
        interaction: TcmBaInteraction,
    ) -> tuple[RawRecordInput, ...]:
        payloads: list[tuple[str, str, dict[str, object]]] = []
        if interaction.stage == "search-submission":
            submission = catalog.submission
            payloads.append(
                (
                    f"tcm-ba:submission:{catalog.competence}",
                    "tcm_ba_monthly_submission",
                    {
                        "competence": submission.competence,
                        "type": submission.type,
                        "unit": submission.unit,
                        "sent_at": submission.sent_at,
                        "status": submission.status,
                        "source_url": catalog.source_url,
                    },
                )
            )
        page_number = self._page_number(interaction.stage)
        if page_number:
            for document in catalog.documents:
                if document.page_number != page_number:
                    continue
                identity = self._digest(
                    "\x1f".join(
                        (
                            catalog.competence,
                            document.download_form_id,
                            document.name,
                            document.inserted_at,
                        )
                    )
                )
                payloads.append(
                    (
                        f"tcm-ba:document:{catalog.competence}:{identity[:32]}",
                        "tcm_ba_monthly_document",
                        {
                            "competence": catalog.competence,
                            "unit": catalog.submission.unit,
                            "category": document.category,
                            "name": document.name,
                            "inserted_at": document.inserted_at,
                            "page_number": document.page_number,
                            "download_form_id": document.download_form_id,
                            "source_url": catalog.source_url,
                        },
                    )
                )

        records: list[RawRecordInput] = []
        for index, (source_key, record_type, payload) in enumerate(payloads):
            canonical = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            payload_sha256 = hashlib.sha256(canonical).hexdigest()
            records.append(
                RawRecordInput(
                    source_record_key=source_key,
                    record_type=record_type,
                    record_index=index,
                    payload=payload,
                    payload_sha256=payload_sha256,
                    parser_version=TCM_BA_PARSER_VERSION,
                    idempotency_key=self._digest(
                        "\x1f".join(
                            (
                                "tcm-ba-record",
                                interaction.body_sha256,
                                source_key,
                                payload_sha256,
                            )
                        )
                    ),
                )
            )
        return tuple(records)

    @staticmethod
    def _page_number(stage: str) -> int:
        if stage == "select-submission":
            return 1
        match = re.fullmatch(r"documents-page-(\d+)", stage)
        return int(match.group(1)) if match else 0

    @staticmethod
    def _media_type(interaction: TcmBaInteraction) -> str:
        for key, value in interaction.response_headers.items():
            if key.casefold() == "content-type":
                return value.split(";", 1)[0].strip() or "text/html"
        return "text/html"

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
