"""Orquestra preservação do bruto antes de qualquer escrita derivada."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ..connectors.gazette_documents import CollectedDocument
from ..connectors.querido_diario import CollectedPage
from .models import (
    ArtifactIntegrityError,
    DocumentBatch,
    DocumentPersistResult,
    PersistenceBatch,
    PersistenceContractError,
    PersistenceResult,
    RawRecordInput,
)
from .ports import ArtifactObjectStore, CollectionRepository

COLLECTOR_VERSION = "querido-diario-collector/0.1.0"
PARSER_VERSION = "querido-diario-gazette-page/1.0.0"
RECORD_TYPE = "querido_diario_gazette"
DOCUMENT_EXTENSIONS = {"pdf": "pdf", "txt": "txt"}


class QueridoDiarioPersistenceService:
    """Preserva uma página JSON e registra suas linhas exatas de origem."""

    def __init__(
        self,
        *,
        object_store: ArtifactObjectStore,
        repository: CollectionRepository,
        collector_version: str = COLLECTOR_VERSION,
        parser_version: str = PARSER_VERSION,
    ) -> None:
        if not collector_version.strip() or not parser_version.strip():
            raise ValueError("Versões de coletor e parser são obrigatórias.")
        self.object_store = object_store
        self.repository = repository
        self.collector_version = collector_version
        self.parser_version = parser_version

    def persist(self, page: CollectedPage) -> PersistenceResult:
        self._verify_page_bytes(page)
        object_key = self._object_key(page.body_sha256)
        records = self._raw_records(page)
        stored = self.object_store.put_if_absent(
            object_key=object_key,
            body=page.raw_body,
            content_type=page.media_type,
            expected_sha256=page.body_sha256,
        )
        self._verify_stored_metadata(page, object_key, stored.sha256, stored.byte_size)

        restored = self.object_store.read(object_key)
        restored_hash = hashlib.sha256(restored).hexdigest()
        if restored_hash != page.body_sha256 or len(restored) != page.body_size_bytes:
            raise ArtifactIntegrityError(
                "O artefato restaurado do Storage diverge do bruto coletado."
            )

        artifact_idempotency_key = self._digest(f"raw-artifact:{page.idempotency_key}")
        persisted = self.repository.persist(
            PersistenceBatch(
                page=page,
                object_key=object_key,
                artifact_idempotency_key=artifact_idempotency_key,
                collector_version=self.collector_version,
                parser_version=self.parser_version,
                records=records,
            )
        )
        return PersistenceResult(
            collection_run_id=persisted.collection_run_id,
            raw_artifact_id=persisted.raw_artifact_id,
            object_key=object_key,
            sha256=page.body_sha256,
            object_created=stored.created,
            inserted_records=persisted.inserted_records,
            existing_records=persisted.existing_records,
        )

    def gazette_records(self, page: CollectedPage) -> tuple[RawRecordInput, ...]:
        """Expõe os registros validados da página para coleta de documentos."""
        return self._raw_records(page)

    def persist_document(
        self,
        *,
        page_result: PersistenceResult,
        record: RawRecordInput,
        document: CollectedDocument,
        source_code: str,
        endpoint_code: str,
    ) -> DocumentPersistResult:
        extension = DOCUMENT_EXTENSIONS.get(document.role)
        if extension is None:
            raise PersistenceContractError(
                f"Papel de documento desconhecido: {document.role}."
            )
        actual_hash = hashlib.sha256(document.raw_body).hexdigest()
        if (
            actual_hash != document.body_sha256
            or len(document.raw_body) != document.body_size_bytes
        ):
            raise ArtifactIntegrityError(
                "O documento baixado não corresponde aos metadados informados."
            )

        object_key = (
            "querido-diario/gazettes/documents/sha256/"
            f"{document.body_sha256[:2]}/{document.body_sha256}.{extension}"
        )
        idempotency_key = self._digest(
            ":".join(
                (
                    "gazette-document",
                    record.source_record_key,
                    document.role,
                    document.body_sha256,
                )
            )
        )
        stored = self.object_store.put_if_absent(
            object_key=object_key,
            body=document.raw_body,
            content_type=document.media_type,
            expected_sha256=document.body_sha256,
        )
        if (
            stored.sha256 != document.body_sha256
            or stored.byte_size != document.body_size_bytes
        ):
            raise ArtifactIntegrityError(
                f"Metadados do objeto {object_key} divergem do documento."
            )

        restored = self.object_store.read(object_key)
        restored_hash = hashlib.sha256(restored).hexdigest()
        if (
            restored_hash != document.body_sha256
            or len(restored) != document.body_size_bytes
        ):
            raise ArtifactIntegrityError(
                "O documento restaurado do Storage diverge do baixado."
            )

        persisted = self.repository.persist_document(
            DocumentBatch(
                source_code=source_code,
                endpoint_code=endpoint_code,
                collection_run_id=page_result.collection_run_id,
                parent_artifact_id=page_result.raw_artifact_id,
                source_record_key=record.source_record_key,
                document=document,
                object_key=object_key,
                idempotency_key=idempotency_key,
                collector_version=self.collector_version,
            )
        )
        return DocumentPersistResult(
            raw_artifact_id=persisted.raw_artifact_id,
            object_key=object_key,
            sha256=document.body_sha256,
            object_created=stored.created,
            artifact_created=persisted.created,
        )

    def _raw_records(self, page: CollectedPage) -> tuple[RawRecordInput, ...]:
        try:
            payload = json.loads(page.raw_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PersistenceContractError(
                "O bruto validado deixou de ser JSON UTF-8 válido."
            ) from error
        if not isinstance(payload, dict) or not isinstance(
            payload.get("gazettes"),
            list,
        ):
            raise PersistenceContractError(
                "O bruto não contém a lista de diários esperada."
            )

        items = payload["gazettes"]
        if len(items) != len(page.parsed.gazettes):
            raise PersistenceContractError(
                "A quantidade no bruto diverge da representação validada."
            )

        records: list[RawRecordInput] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise PersistenceContractError(
                    f"O registro bruto {index} não é um objeto."
                )
            canonical_payload = self._canonical_json(item)
            payload_sha256 = hashlib.sha256(canonical_payload).hexdigest()
            source_record_key = self._source_record_key(item)
            record_idempotency = self._digest(
                ":".join(
                    (
                        "raw-record",
                        page.idempotency_key,
                        self.parser_version,
                        str(index),
                        payload_sha256,
                    )
                )
            )
            records.append(
                RawRecordInput(
                    source_record_key=source_record_key,
                    record_type=RECORD_TYPE,
                    record_index=index,
                    payload=item,
                    payload_sha256=payload_sha256,
                    parser_version=self.parser_version,
                    idempotency_key=record_idempotency,
                )
            )
        return tuple(records)

    @classmethod
    def _source_record_key(cls, item: dict[str, Any]) -> str:
        identity = {
            "territory_id": item.get("territory_id"),
            "date": item.get("date"),
            "edition": item.get("edition"),
            "is_extra_edition": item.get("is_extra_edition"),
            "url": item.get("url"),
        }
        identity_hash = hashlib.sha256(cls._canonical_json(identity)).hexdigest()
        return f"querido-diario:gazette:{identity_hash}"

    @staticmethod
    def _canonical_json(value: object) -> bytes:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    @staticmethod
    def _object_key(body_sha256: str) -> str:
        return f"querido-diario/gazettes/sha256/{body_sha256[:2]}/{body_sha256}.json"

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _verify_page_bytes(page: CollectedPage) -> None:
        actual_hash = hashlib.sha256(page.raw_body).hexdigest()
        if actual_hash != page.body_sha256:
            raise ArtifactIntegrityError(
                "O SHA-256 informado não corresponde ao bruto."
            )
        if len(page.raw_body) != page.body_size_bytes:
            raise ArtifactIntegrityError(
                "O tamanho informado não corresponde ao bruto."
            )

    @staticmethod
    def _verify_stored_metadata(
        page: CollectedPage,
        object_key: str,
        stored_hash: str,
        stored_size: int,
    ) -> None:
        if stored_hash != page.body_sha256 or stored_size != page.body_size_bytes:
            raise ArtifactIntegrityError(
                f"Metadados do objeto {object_key} divergem da coleta."
            )
