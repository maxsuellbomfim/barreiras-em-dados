"""Orquestra preservação do bruto antes de qualquer escrita derivada."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ..connectors.direct_diary import ENDPOINT_CODE, SOURCE_CODE, DirectEdition
from ..connectors.gazette_documents import CollectedDocument
from ..connectors.querido_diario import CollectedPage
from .models import (
    ArtifactIntegrityError,
    DirectEditionBatch,
    DocumentBatch,
    DocumentPersistResult,
    PersistenceBatch,
    PersistenceContractError,
    PersistenceResult,
    RawRecordInput,
    RepositoryDirectEditionResult,
)
from .ports import ArtifactObjectStore, CollectionRepository

COLLECTOR_VERSION = "querido-diario-collector/0.1.0"
PARSER_VERSION = "querido-diario-gazette-page/1.0.0"
RECORD_TYPE = "querido_diario_gazette"
DOCUMENT_EXTENSIONS = {"pdf": "pdf", "txt": "txt"}
DIRECT_COLLECTOR_VERSION = "barreiras-diario-collector/0.1.0"
PNCP_COLLECTOR_VERSION = "pncp-registry-collector/0.1.0"
PNCP_CONTRATACAO_PARSER_VERSION = "pncp-contratacao-page/1.0.0"
CAMARA_COLLECTOR_VERSION = "camara-federal-collector/0.1.0"
VEREADORES_COLLECTOR_VERSION = "cm-barreiras-collector/0.1.0"
VEREADORES_PARSER_VERSION = "cm-barreiras-vereadores/1.0.0"
PNCP_ITEM_PARSER_VERSION = "pncp-item-page/1.0.0"
PNCP_RESULTADO_PARSER_VERSION = "pncp-resultado-page/1.0.0"


class PncpContratacoesPersistenceService:
    """Preserva páginas de contratações reutilizando o repositório padrão."""

    def __init__(self, *, object_store, repository) -> None:
        self.object_store = object_store
        self.repository = repository

    def persist(self, page) -> PersistenceResult:
        actual = hashlib.sha256(page.raw_body).hexdigest()
        if actual != page.body_sha256:
            raise ArtifactIntegrityError(
                "A página de contratações não corresponde ao hash informado."
            )
        object_key = (
            "pncp/procurement/contratacoes/sha256/"
            f"{page.body_sha256[:2]}/{page.body_sha256}.json"
        )
        records = []
        for index, item in enumerate(page.items):
            control_number = item.get("numeroControlePNCP")
            if not isinstance(control_number, str) or not control_number:
                raise PersistenceContractError(
                    f"Contratação {index} sem numeroControlePNCP."
                )
            canonical = json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            payload_sha256 = hashlib.sha256(canonical).hexdigest()
            records.append(
                RawRecordInput(
                    source_record_key=f"pncp:contratacao:{control_number}",
                    record_type="pncp_contratacao",
                    record_index=index,
                    payload=item,
                    payload_sha256=payload_sha256,
                    parser_version=PNCP_CONTRATACAO_PARSER_VERSION,
                    idempotency_key=hashlib.sha256(
                        ":".join(
                            (
                                "pncp-contratacao",
                                page.idempotency_key,
                                PNCP_CONTRATACAO_PARSER_VERSION,
                                str(index),
                                payload_sha256,
                            )
                        ).encode("utf-8")
                    ).hexdigest(),
                )
            )

        stored = self.object_store.put_if_absent(
            object_key=object_key,
            body=page.raw_body,
            content_type=page.media_type,
            expected_sha256=page.body_sha256,
        )
        restored = self.object_store.read(object_key)
        if (
            hashlib.sha256(restored).hexdigest() != page.body_sha256
            or stored.sha256 != page.body_sha256
        ):
            raise ArtifactIntegrityError(
                "A página restaurada do Storage diverge da coletada."
            )

        artifact_key = hashlib.sha256(
            f"raw-artifact:{page.idempotency_key}".encode()
        ).hexdigest()
        persisted = self.repository.persist(
            PersistenceBatch(
                page=page,
                object_key=object_key,
                artifact_idempotency_key=artifact_key,
                collector_version=PNCP_COLLECTOR_VERSION,
                parser_version=PNCP_CONTRATACAO_PARSER_VERSION,
                records=tuple(records),
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


class PncpComprasPersistenceService:
    """Preserva itens e resultados de contratações no repositório padrão."""

    def __init__(self, *, object_store, repository) -> None:
        self.object_store = object_store
        self.repository = repository

    def persist_itens(self, page, *, control: str) -> PersistenceResult:
        records = []
        for index, item in enumerate(page.items):
            numero_item = item.get("numeroItem")
            if not isinstance(numero_item, int):
                raise PersistenceContractError(
                    f"Item {index} da contratação {control} sem numeroItem."
                )
            records.append(
                self._record(
                    page,
                    item,
                    index=index,
                    source_record_key=f"pncp:item:{control}:{numero_item}",
                    record_type="pncp_item",
                    parser_version=PNCP_ITEM_PARSER_VERSION,
                )
            )
        return self._persist(
            page,
            kind="itens",
            parser_version=PNCP_ITEM_PARSER_VERSION,
            records=records,
        )

    def persist_resultados(
        self, page, *, control: str, numero_item: int
    ) -> PersistenceResult:
        records = []
        for index, item in enumerate(page.items):
            sequencial = item.get("sequencialResultado")
            if not isinstance(sequencial, int):
                raise PersistenceContractError(
                    f"Resultado {index} do item {numero_item} da contratação "
                    f"{control} sem sequencialResultado."
                )
            records.append(
                self._record(
                    page,
                    item,
                    index=index,
                    source_record_key=(
                        f"pncp:resultado:{control}:{numero_item}:{sequencial}"
                    ),
                    record_type="pncp_resultado",
                    parser_version=PNCP_RESULTADO_PARSER_VERSION,
                )
            )
        return self._persist(
            page,
            kind="resultados",
            parser_version=PNCP_RESULTADO_PARSER_VERSION,
            records=records,
        )

    @staticmethod
    def _record(
        page,
        item,
        *,
        index: int,
        source_record_key: str,
        record_type: str,
        parser_version: str,
    ) -> RawRecordInput:
        canonical = json.dumps(
            item,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        payload_sha256 = hashlib.sha256(canonical).hexdigest()
        return RawRecordInput(
            source_record_key=source_record_key,
            record_type=record_type,
            record_index=index,
            payload=item,
            payload_sha256=payload_sha256,
            parser_version=parser_version,
            idempotency_key=hashlib.sha256(
                ":".join(
                    (
                        record_type,
                        page.idempotency_key,
                        parser_version,
                        str(index),
                        payload_sha256,
                    )
                ).encode("utf-8")
            ).hexdigest(),
        )

    def _persist(
        self,
        page,
        *,
        kind: str,
        parser_version: str,
        records: list,
    ) -> PersistenceResult:
        actual = hashlib.sha256(page.raw_body).hexdigest()
        if actual != page.body_sha256:
            raise ArtifactIntegrityError(
                f"A página de {kind} não corresponde ao hash informado."
            )
        object_key = (
            f"pncp/procurement/{kind}/sha256/"
            f"{page.body_sha256[:2]}/{page.body_sha256}.json"
        )
        stored = self.object_store.put_if_absent(
            object_key=object_key,
            body=page.raw_body,
            content_type=page.media_type,
            expected_sha256=page.body_sha256,
        )
        restored = self.object_store.read(object_key)
        if (
            hashlib.sha256(restored).hexdigest() != page.body_sha256
            or stored.sha256 != page.body_sha256
        ):
            raise ArtifactIntegrityError(
                f"A página de {kind} restaurada do Storage diverge da coletada."
            )

        artifact_key = hashlib.sha256(
            f"raw-artifact:{page.idempotency_key}".encode()
        ).hexdigest()
        persisted = self.repository.persist(
            PersistenceBatch(
                page=page,
                object_key=object_key,
                artifact_idempotency_key=artifact_key,
                collector_version=PNCP_COLLECTOR_VERSION,
                parser_version=parser_version,
                records=tuple(records),
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


class VereadoresPersistenceService:
    """Preserva a lista de vereadores como bruto verificável por hash."""

    def __init__(self, *, object_store, repository) -> None:
        self.object_store = object_store
        self.repository = repository

    def persist(self, page) -> PersistenceResult:
        actual = hashlib.sha256(page.raw_body).hexdigest()
        if actual != page.body_sha256:
            raise ArtifactIntegrityError(
                "A página de vereadores não corresponde ao hash informado."
            )
        object_key = (
            "camara-municipal/vereadores/sha256/"
            f"{page.body_sha256[:2]}/{page.body_sha256}.html"
        )
        parser_version = VEREADORES_PARSER_VERSION
        records = []
        for index, item in enumerate(page.items):
            name = item.get("nome")
            if not isinstance(name, str) or not name.strip():
                raise PersistenceContractError(
                    f"Vereador {index} sem nome."
                )
            canonical = json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            payload_sha256 = hashlib.sha256(canonical).hexdigest()
            # A fonte não publica identificador: a chave é o nome
            # normalizado dentro desta fonte, nunca cruzado com outra
            # (ADR 0014 — homônimo não vira a mesma pessoa).
            slug = hashlib.sha256(
                name.strip().casefold().encode("utf-8")
            ).hexdigest()[:16]
            records.append(
                RawRecordInput(
                    source_record_key=f"cm-barreiras:vereador:{slug}",
                    record_type="cm_barreiras_vereador",
                    record_index=index,
                    payload=item,
                    payload_sha256=payload_sha256,
                    parser_version=parser_version,
                    idempotency_key=hashlib.sha256(
                        ":".join(
                            (
                                "cm-barreiras-vereador",
                                page.idempotency_key,
                                parser_version,
                                str(index),
                                payload_sha256,
                            )
                        ).encode("utf-8")
                    ).hexdigest(),
                )
            )

        stored = self.object_store.put_if_absent(
            object_key=object_key,
            body=page.raw_body,
            content_type=page.media_type,
            expected_sha256=page.body_sha256,
        )
        restored = self.object_store.read(object_key)
        if (
            hashlib.sha256(restored).hexdigest() != page.body_sha256
            or stored.sha256 != page.body_sha256
        ):
            raise ArtifactIntegrityError(
                "A página restaurada do Storage diverge da coletada."
            )

        artifact_key = hashlib.sha256(
            f"raw-artifact:{page.idempotency_key}".encode()
        ).hexdigest()
        persisted = self.repository.persist(
            PersistenceBatch(
                page=page,
                object_key=object_key,
                artifact_idempotency_key=artifact_key,
                collector_version=VEREADORES_COLLECTOR_VERSION,
                parser_version=parser_version,
                records=tuple(records),
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


class CamaraPersistenceService:
    """Preserva respostas da Câmara reusando o repositório padrão."""

    def __init__(self, *, object_store, repository) -> None:
        self.object_store = object_store
        self.repository = repository

    def persist(self, page, *, record_type: str) -> PersistenceResult:
        actual = hashlib.sha256(page.raw_body).hexdigest()
        if actual != page.body_sha256:
            raise ArtifactIntegrityError(
                "A resposta da Câmara não corresponde ao hash informado."
            )
        object_key = (
            "camara-federal/deputados/sha256/"
            f"{page.body_sha256[:2]}/{page.body_sha256}.json"
        )
        parser_version = f"{record_type}/1.0.0"
        records = []
        for index, item in enumerate(page.items):
            deputy_id = item.get("id")
            if not isinstance(deputy_id, int):
                raise PersistenceContractError(
                    f"Registro {index} da Câmara sem id numérico."
                )
            canonical = json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            payload_sha256 = hashlib.sha256(canonical).hexdigest()
            records.append(
                RawRecordInput(
                    source_record_key=f"camara:deputado:{deputy_id}",
                    record_type=record_type,
                    record_index=index,
                    payload=item,
                    payload_sha256=payload_sha256,
                    parser_version=parser_version,
                    idempotency_key=hashlib.sha256(
                        ":".join(
                            (
                                record_type,
                                page.idempotency_key,
                                parser_version,
                                str(index),
                                payload_sha256,
                            )
                        ).encode("utf-8")
                    ).hexdigest(),
                )
            )

        stored = self.object_store.put_if_absent(
            object_key=object_key,
            body=page.raw_body,
            content_type=page.media_type,
            expected_sha256=page.body_sha256,
        )
        restored = self.object_store.read(object_key)
        if (
            hashlib.sha256(restored).hexdigest() != page.body_sha256
            or stored.sha256 != page.body_sha256
        ):
            raise ArtifactIntegrityError(
                "A resposta restaurada do Storage diverge da coletada."
            )

        artifact_key = hashlib.sha256(
            f"raw-artifact:{page.idempotency_key}".encode()
        ).hexdigest()
        persisted = self.repository.persist(
            PersistenceBatch(
                page=page,
                object_key=object_key,
                artifact_idempotency_key=artifact_key,
                collector_version=CAMARA_COLLECTOR_VERSION,
                parser_version=parser_version,
                records=tuple(records),
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


class PncpRegistryPersistenceService:
    """Preserva um snapshot do cadastro PNCP como artefato raiz por hash."""

    def __init__(self, *, object_store, repository) -> None:
        self.object_store = object_store
        self.repository = repository

    def persist(self, snapshot) -> RepositoryDirectEditionResult:
        actual = hashlib.sha256(snapshot.body).hexdigest()
        if actual != snapshot.body_sha256:
            raise ArtifactIntegrityError(
                "O snapshot baixado não corresponde ao hash informado."
            )
        object_key = (
            "pncp/procurement/registry/sha256/"
            f"{snapshot.body_sha256[:2]}/{snapshot.body_sha256}.json"
        )
        artifact_key = hashlib.sha256(
            ":".join(
                (
                    "pncp-registry",
                    snapshot.resource,
                    snapshot.body_sha256,
                )
            ).encode("utf-8")
        ).hexdigest()
        run_key = hashlib.sha256(
            f"pncp-registry-run:{artifact_key}".encode()
        ).hexdigest()

        stored = self.object_store.put_if_absent(
            object_key=object_key,
            body=snapshot.body,
            content_type=snapshot.media_type,
            expected_sha256=snapshot.body_sha256,
        )
        restored = self.object_store.read(object_key)
        if (
            hashlib.sha256(restored).hexdigest() != snapshot.body_sha256
            or stored.sha256 != snapshot.body_sha256
        ):
            raise ArtifactIntegrityError(
                "O snapshot restaurado do Storage diverge do baixado."
            )

        return self.repository.persist_registry_snapshot(
            snapshot,
            object_key=object_key,
            artifact_idempotency_key=artifact_key,
            run_idempotency_key=run_key,
            collector_version=PNCP_COLLECTOR_VERSION,
        )


class DirectDiaryPersistenceService:
    """Preserva uma edição direta como artefato raiz verificado por hash."""

    def __init__(self, *, object_store, repository) -> None:
        self.object_store = object_store
        self.repository = repository

    def persist(self, edition: DirectEdition) -> RepositoryDirectEditionResult:
        document = edition.document
        actual_hash = hashlib.sha256(document.raw_body).hexdigest()
        if (
            actual_hash != document.body_sha256
            or len(document.raw_body) != document.body_size_bytes
        ):
            raise ArtifactIntegrityError(
                "A edição baixada não corresponde aos metadados informados."
            )

        object_key = (
            "barreiras-diario/gazettes/documents/sha256/"
            f"{document.body_sha256[:2]}/{document.body_sha256}.pdf"
        )
        artifact_key = hashlib.sha256(
            ":".join(
                (
                    "direct-gazette",
                    str(edition.edition_number),
                    str(edition.year),
                    document.body_sha256,
                )
            ).encode("utf-8")
        ).hexdigest()
        run_key = hashlib.sha256(
            f"direct-diary-run:{artifact_key}".encode()
        ).hexdigest()

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
        ):
            raise ArtifactIntegrityError(
                "A edição restaurada do Storage diverge da baixada."
            )

        return self.repository.persist_direct_edition(
            DirectEditionBatch(
                source_code=SOURCE_CODE,
                endpoint_code=ENDPOINT_CODE,
                edition_number=edition.edition_number,
                edition_year=edition.year,
                document=document,
                object_key=object_key,
                artifact_idempotency_key=artifact_key,
                run_idempotency_key=run_key,
                collector_version=DIRECT_COLLECTOR_VERSION,
            )
        )


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
