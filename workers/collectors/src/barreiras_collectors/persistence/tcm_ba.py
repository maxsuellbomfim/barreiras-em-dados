"""Preservação imutável do catálogo mensal do TCM-BA."""

from __future__ import annotations

import calendar
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date

from ..connectors.gazette_documents import CollectedDocument
from ..connectors.querido_diario import CollectedPage, GazettePage
from ..connectors.tcm_ba import (
    TcmBaDocument,
    TcmBaDocumentDownload,
    TcmBaInteraction,
    TcmBaMonthlyCatalog,
    validate_tcm_ba_catalog,
    validate_tcm_ba_document_download,
)
from .models import (
    ArtifactIntegrityError,
    DocumentBatch,
    PersistenceBatch,
    PersistenceContractError,
    RawRecordInput,
    TcmBaDocumentReference,
)

TCM_BA_COLLECTOR_VERSION = "tcm-ba-monthly-catalog-collector/1.0.1"
TCM_BA_PARSER_VERSION = "tcm-ba-monthly-catalog/1.0.0"
TCM_BA_DOCUMENT_COLLECTOR_VERSION = "tcm-ba-monthly-document-collector/1.0.0"


@dataclass(frozen=True)
class TcmBaDocumentPersistenceSummary:
    prepare_artifact_id: str
    pdf_artifact_id: str
    prepare_object_key: str
    pdf_object_key: str
    pdf_sha256: str
    prepare_object_created: bool
    pdf_object_created: bool
    prepare_artifact_created: bool
    pdf_artifact_created: bool


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
            media_type = self._media_type(interaction)
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
                media_type=media_type,
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
                f"{interaction.body_sha256[:2]}/{interaction.body_sha256}"
                f"{self._suffix(media_type)}"
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
                media_type = value.split(";", 1)[0].strip().casefold()
                # O JSF usa o tipo obsoleto text/xml em respostas AJAX. O bucket
                # privado aceita o equivalente registrado application/xml; os
                # headers originais continuam preservados em response_headers.
                return (
                    "application/xml"
                    if media_type == "text/xml"
                    else (media_type or "text/html")
                )
        return "text/html"

    @staticmethod
    def _suffix(media_type: str) -> str:
        return ".xml" if media_type == "application/xml" else ".html"

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


class TcmBaDocumentPersistenceService:
    """Preserva XML preparatório e PDF como filhos do registro do catálogo."""

    def __init__(self, *, object_store, repository) -> None:
        self.object_store = object_store
        self.repository = repository

    def persist(
        self,
        download: TcmBaDocumentDownload,
        *,
        reference: TcmBaDocumentReference,
        collection_run_id: str,
    ) -> TcmBaDocumentPersistenceSummary:
        validate_tcm_ba_document_download(download)
        self._validate_reference(download, reference)
        if not collection_run_id.strip():
            raise ValueError("collection_run_id é obrigatório.")

        year = int(download.competence[3:])
        month = int(download.competence[:2])
        prepare = self._as_document(
            download.prepare_interaction,
            role="download-prepare",
            media_type="application/xml",
        )
        pdf = self._as_document(
            download.pdf_interaction,
            role="pdf",
            media_type="application/pdf",
        )
        prepare_key = (
            f"tcm-ba/monthly-documents/{year}/{month:02d}/prepare/sha256/"
            f"{prepare.body_sha256[:2]}/{prepare.body_sha256}.xml"
        )
        pdf_key = (
            f"tcm-ba/monthly-documents/{year}/{month:02d}/pdf/sha256/"
            f"{pdf.body_sha256[:2]}/{pdf.body_sha256}.pdf"
        )

        prepare_object, prepare_artifact = self._persist_child(
            document=prepare,
            object_key=prepare_key,
            collection_run_id=collection_run_id,
            parent_artifact_id=reference.parent_artifact_id,
            source_record_key=reference.source_record_key,
            idempotency_key=self._digest(
                "\x1f".join(
                    (
                        "tcm-ba-document-prepare",
                        reference.source_record_key,
                        prepare.body_sha256,
                    )
                )
            ),
            schema_name="tcm-ba-document-download-prepare",
            object_prefix="tcm-ba/monthly-documents/prepare",
        )
        pdf_object, pdf_artifact = self._persist_child(
            document=pdf,
            object_key=pdf_key,
            collection_run_id=collection_run_id,
            parent_artifact_id=prepare_artifact.raw_artifact_id,
            source_record_key=reference.source_record_key,
            idempotency_key=self._digest(
                "\x1f".join(
                    (
                        "tcm-ba-monthly-document",
                        reference.source_record_key,
                        pdf.body_sha256,
                    )
                )
            ),
            schema_name="tcm-ba-monthly-document",
            object_prefix="tcm-ba/monthly-documents/pdf",
        )
        return TcmBaDocumentPersistenceSummary(
            prepare_artifact_id=prepare_artifact.raw_artifact_id,
            pdf_artifact_id=pdf_artifact.raw_artifact_id,
            prepare_object_key=prepare_key,
            pdf_object_key=pdf_key,
            pdf_sha256=pdf.body_sha256,
            prepare_object_created=prepare_object.created,
            pdf_object_created=pdf_object.created,
            prepare_artifact_created=prepare_artifact.created,
            pdf_artifact_created=pdf_artifact.created,
        )

    def _persist_child(
        self,
        *,
        document: CollectedDocument,
        object_key: str,
        collection_run_id: str,
        parent_artifact_id: str,
        source_record_key: str,
        idempotency_key: str,
        schema_name: str,
        object_prefix: str,
    ):
        stored = self.object_store.put_if_absent(
            object_key=object_key,
            body=document.raw_body,
            content_type=document.media_type,
            expected_sha256=document.body_sha256,
        )
        restored = self.object_store.read(object_key)
        if (
            hashlib.sha256(restored).hexdigest() != document.body_sha256
            or len(restored) != document.body_size_bytes
            or stored.sha256 != document.body_sha256
            or stored.byte_size != document.body_size_bytes
        ):
            raise ArtifactIntegrityError(
                "Artefato documental TCM-BA restaurado diverge do coletado."
            )
        artifact = self.repository.persist_document(
            DocumentBatch(
                source_code="tcm-ba",
                endpoint_code="prestacoes-contas-mensais",
                collection_run_id=collection_run_id,
                parent_artifact_id=parent_artifact_id,
                source_record_key=source_record_key,
                document=document,
                object_key=object_key,
                idempotency_key=idempotency_key,
                collector_version=TCM_BA_DOCUMENT_COLLECTOR_VERSION,
                document_schema_name=schema_name,
                document_object_prefix=object_prefix,
            )
        )
        return stored, artifact

    @staticmethod
    def _validate_reference(
        download: TcmBaDocumentDownload,
        reference: TcmBaDocumentReference,
    ) -> None:
        expected = TcmBaDocument(
            category=reference.category,
            name=reference.name,
            inserted_at=reference.inserted_at,
            page_number=reference.page_number,
            download_form_id=reference.download_form_id,
        )
        if (
            download.competence != reference.competence
            or download.total_documents != reference.expected_total_documents
            or download.document_position != reference.document_position
            or download.document != expected
        ):
            raise PersistenceContractError(
                "Download TCM-BA diverge da referência bruta do catálogo."
            )
        if not reference.source_record_key.startswith(
            f"tcm-ba:document:{reference.competence}:"
        ):
            raise PersistenceContractError(
                "Chave oficial da referência TCM-BA é incompatível."
            )
        if not reference.parent_artifact_id.strip():
            raise PersistenceContractError("Artefato pai TCM-BA é obrigatório.")

    @staticmethod
    def _as_document(
        interaction: TcmBaInteraction,
        *,
        role: str,
        media_type: str,
    ) -> CollectedDocument:
        return CollectedDocument(
            role=role,
            source_url=interaction.request_url,
            final_url=interaction.final_url,
            requested_at=interaction.received_at,
            received_at=interaction.received_at,
            attempts=1,
            http_status=interaction.http_status,
            body_sha256=interaction.body_sha256,
            body_size_bytes=len(interaction.raw_body),
            media_type=media_type,
            response_headers=interaction.response_headers,
            raw_body=interaction.raw_body,
        )

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
