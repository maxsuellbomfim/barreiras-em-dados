"""Orquestra preservação do bruto antes de qualquer escrita derivada."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ..connectors.direct_diary import ENDPOINT_CODE, SOURCE_CODE, DirectEdition
from ..connectors.gazette_documents import CollectedDocument
from ..connectors.municipal_transparency import MunicipalTransparencyPage
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
ALBA_COLLECTOR_VERSION = "alba-collector/0.1.0"
ALBA_PARSER_VERSION = "alba-deputados/1.0.0"
TSE_COLLECTOR_VERSION = "tse-collector/0.1.0"
TSE_PARSER_VERSION = "tse-votacao-munzona/1.0.0"
VEREADORES_COLLECTOR_VERSION = "cm-barreiras-collector/0.1.0"
VEREADORES_PARSER_VERSION = "cm-barreiras-vereadores/1.0.0"
MUNICIPAL_TRANSPARENCY_COLLECTOR_VERSION = "municipal-transparency-collector/0.1.0"
MUNICIPAL_TRANSPARENCY_PARSER_VERSION = "municipal-transparency-page/1.0.0"
PNCP_ITEM_PARSER_VERSION = "pncp-item-page/1.0.0"
PNCP_RESULTADO_PARSER_VERSION = "pncp-resultado-page/1.0.0"
PNCP_CONTRATO_PARSER_VERSION = "pncp-contrato-page/1.0.0"


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


class MunicipalTransparencyPersistenceService:
    """Preserva uma página municipal antes de qualquer normalização financeira."""

    def __init__(self, *, object_store, repository) -> None:
        self.object_store = object_store
        self.repository = repository

    def persist(self, page: MunicipalTransparencyPage) -> PersistenceResult:
        actual = hashlib.sha256(page.raw_body).hexdigest()
        if actual != page.body_sha256:
            raise ArtifactIntegrityError(
                "A página da API municipal não corresponde ao hash informado."
            )
        object_key = (
            "municipal-transparency/"
            f"{page.source_code}/{page.resource}/sha256/"
            f"{page.body_sha256[:2]}/{page.body_sha256}.json"
        )
        records = tuple(
            self.record_input(page, index=index, item=item)
            for index, item in enumerate(page.items)
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
            or len(restored) != page.body_size_bytes
            or stored.sha256 != page.body_sha256
        ):
            raise ArtifactIntegrityError(
                "A resposta municipal restaurada diverge da coletada."
            )
        persisted = self.repository.persist(
            PersistenceBatch(
                page=page,  # type: ignore[arg-type]
                object_key=object_key,
                artifact_idempotency_key=self._digest(
                    f"raw-artifact:{page.idempotency_key}"
                ),
                collector_version=MUNICIPAL_TRANSPARENCY_COLLECTOR_VERSION,
                parser_version=MUNICIPAL_TRANSPARENCY_PARSER_VERSION,
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

    def record_input(
        self,
        page: MunicipalTransparencyPage,
        *,
        index: int,
        item: dict,
    ) -> RawRecordInput:
        """Retorna a identidade bruta usada também pelos artefatos filhos."""

        payload_hash = self._payload_hash(item)
        return RawRecordInput(
            source_record_key=self._record_key(page, item),
            record_type=f"municipal_transparency_{page.resource}",
            record_index=index,
            payload=item,
            payload_sha256=payload_hash,
            parser_version=MUNICIPAL_TRANSPARENCY_PARSER_VERSION,
            idempotency_key=self._record_idempotency(
                page,
                index=index,
                payload=item,
            ),
        )

    def persist_document(
        self,
        *,
        page_result: PersistenceResult,
        record: RawRecordInput,
        document: CollectedDocument,
        source_code: str,
        endpoint_code: str,
    ) -> DocumentPersistResult:
        """Preserva um PDF municipal como artefato filho da resposta JSON."""

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
                "O documento financeiro nao corresponde ao hash informado."
            )
        object_key = (
            "municipal-transparency/documents/sha256/"
            f"{document.body_sha256[:2]}/{document.body_sha256}.{extension}"
        )
        idempotency_key = self._digest(
            ":".join(
                (
                    "municipal-transparency-document",
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
        restored = self.object_store.read(object_key)
        if (
            hashlib.sha256(restored).hexdigest() != document.body_sha256
            or len(restored) != document.body_size_bytes
            or stored.sha256 != document.body_sha256
        ):
            raise ArtifactIntegrityError(
                "O documento financeiro restaurado diverge do baixado."
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
                collector_version=MUNICIPAL_TRANSPARENCY_COLLECTOR_VERSION,
                document_schema_name="municipal-transparency-document",
                document_object_prefix="municipal-transparency/documents",
            )
        )
        return DocumentPersistResult(
            raw_artifact_id=persisted.raw_artifact_id,
            object_key=object_key,
            sha256=document.body_sha256,
            object_created=stored.created,
            artifact_created=persisted.created,
        )

    @classmethod
    def _record_key(cls, page: MunicipalTransparencyPage, item: dict) -> str:
        return ":".join(
            (
                "municipal-transparency",
                page.source_code,
                page.resource,
                cls._payload_hash(item)[:24],
            )
        )

    @staticmethod
    def _payload_hash(item: dict) -> str:
        return hashlib.sha256(
            json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    @classmethod
    def _record_idempotency(
        cls,
        page: MunicipalTransparencyPage,
        *,
        index: int,
        payload: dict,
    ) -> str:
        return cls._digest(
            ":".join(
                (
                    "municipal-transparency-record",
                    page.idempotency_key,
                    page.resource,
                    str(index),
                    cls._payload_hash(payload),
                )
            )
        )

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


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

    def persist_contratos(self, page, *, control: str) -> PersistenceResult:
        """Preserva contratos/empenhos sem convertê-los em valores financeiros."""
        records = []
        for index, item in enumerate(page.items):
            numero_controle = item.get("numeroControlePNCP")
            compra_controle = item.get("numeroControlePNCPCompra")
            if not isinstance(numero_controle, str) or not numero_controle:
                raise PersistenceContractError(
                    f"Contrato {index} da contrataÃ§Ã£o {control} sem "
                    "numeroControlePNCP."
                )
            if compra_controle != control:
                raise PersistenceContractError(
                    f"Contrato {numero_controle} nÃ£o referencia a "
                    "contrataÃ§Ã£o esperada."
                )
            records.append(
                self._record(
                    page,
                    item,
                    index=index,
                    source_record_key=f"pncp:contrato:{numero_controle}",
                    record_type="pncp_contrato",
                    parser_version=PNCP_CONTRATO_PARSER_VERSION,
                )
            )
        return self._persist(
            page,
            kind="contratos",
            parser_version=PNCP_CONTRATO_PARSER_VERSION,
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


class AlbaPersistenceService:
    """Preserva a composição da Assembleia Legislativa da Bahia."""

    def __init__(self, *, object_store, repository) -> None:
        self.object_store = object_store
        self.repository = repository

    def persist(self, page) -> PersistenceResult:
        actual = hashlib.sha256(page.raw_body).hexdigest()
        if actual != page.body_sha256:
            raise ArtifactIntegrityError(
                "A listagem da Assembleia não corresponde ao hash informado."
            )
        object_key = (
            "alba/deputados/sha256/"
            f"{page.body_sha256[:2]}/{page.body_sha256}.html"
        )
        records = []
        for index, item in enumerate(page.items):
            identifier = item.get("id_alba")
            if not isinstance(identifier, str) or not identifier.isdigit():
                raise PersistenceContractError(
                    f"Deputado {index} sem identificador da Assembleia."
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
                    source_record_key=f"alba:deputado:{identifier}",
                    record_type="alba_deputado_estadual",
                    record_index=index,
                    payload=item,
                    payload_sha256=payload_sha256,
                    parser_version=ALBA_PARSER_VERSION,
                    idempotency_key=hashlib.sha256(
                        ":".join(
                            (
                                "alba-deputado",
                                page.idempotency_key,
                                ALBA_PARSER_VERSION,
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
                "A listagem restaurada do Storage diverge da coletada."
            )

        artifact_key = hashlib.sha256(
            f"raw-artifact:{page.idempotency_key}".encode()
        ).hexdigest()
        persisted = self.repository.persist(
            PersistenceBatch(
                page=page,
                object_key=object_key,
                artifact_idempotency_key=artifact_key,
                collector_version=ALBA_COLLECTOR_VERSION,
                parser_version=ALBA_PARSER_VERSION,
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


class TseVotesPersistenceService:
    """Preserva o recorte municipal da votação nominal (ADR 0014)."""

    def __init__(self, *, object_store, repository) -> None:
        self.object_store = object_store
        self.repository = repository

    def persist(self, page) -> PersistenceResult:
        actual = hashlib.sha256(page.raw_body).hexdigest()
        if actual != page.body_sha256:
            raise ArtifactIntegrityError(
                "O recorte do TSE não corresponde ao hash informado."
            )
        year = page.cursor.get("ano")
        object_key = (
            "tse/votacao/sha256/"
            f"{page.body_sha256[:2]}/{page.body_sha256}.json"
        )
        records = []
        for index, item in enumerate(page.items):
            sequential = item.get("sq_candidato")
            turn = item.get("turno")
            if not isinstance(sequential, str) or not sequential:
                raise PersistenceContractError(
                    f"Candidatura {index} sem sequencial do TSE."
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
                    # Identificador oficial do TSE: nunca o nome (ADR 0014).
                    source_record_key=(
                        f"tse:votacao:{year}:{sequential}:{turn}"
                    ),
                    record_type="tse_votacao_barreiras",
                    record_index=index,
                    payload=item,
                    payload_sha256=payload_sha256,
                    parser_version=TSE_PARSER_VERSION,
                    idempotency_key=hashlib.sha256(
                        ":".join(
                            (
                                "tse-votacao",
                                page.idempotency_key,
                                TSE_PARSER_VERSION,
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
                "O recorte restaurado do Storage diverge do coletado."
            )

        artifact_key = hashlib.sha256(
            f"raw-artifact:{page.idempotency_key}".encode()
        ).hexdigest()
        persisted = self.repository.persist(
            PersistenceBatch(
                page=page,
                object_key=object_key,
                artifact_idempotency_key=artifact_key,
                collector_version=TSE_COLLECTOR_VERSION,
                parser_version=TSE_PARSER_VERSION,
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
        document_schema_name: str = "gazette-document",
        document_object_prefix: str = "querido-diario/gazettes/documents",
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
            f"{document_object_prefix.rstrip('/')}/sha256/"
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
                document_schema_name=document_schema_name,
                document_object_prefix=document_object_prefix,
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
