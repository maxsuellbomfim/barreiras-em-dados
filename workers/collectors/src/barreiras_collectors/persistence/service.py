"""Orquestra preservação do bruto antes de qualquer escrita derivada."""

from __future__ import annotations

import hashlib
import json
from typing import Any, ClassVar

from ..connectors.bahia_state_amendments import (
    BahiaStateAmendmentArchiveError,
    BahiaStateAmendmentArchiveSnapshot,
    BahiaStateAmendmentCatalogSnapshot,
    BahiaStateAmendmentRelationshipSnapshot,
    parse_state_amendment_archive,
    parse_state_amendment_catalog,
    validate_state_amendment_relationship_manifest,
)
from ..connectors.bahia_state_loa_amendments import (
    YEARLY_ANNEXES,
    BahiaStateLoaAnnexError,
    StateLoaAnnexSnapshot,
    build_state_loa_annex_manifest,
)
from ..connectors.cgu_federal_amendments import (
    CGUFederalAmendmentArchiveError,
    CGUFederalAmendmentSnapshot,
    parse_cgu_federal_amendments_archive,
)
from ..connectors.direct_diary import ENDPOINT_CODE, SOURCE_CODE, DirectEdition
from ..connectors.gazette_documents import CollectedDocument
from ..connectors.municipal_transparency import MunicipalTransparencyPage
from ..connectors.official_diary_catalog import (
    ENDPOINT_CODE as OFFICIAL_CATALOG_ENDPOINT_CODE,
)
from ..connectors.official_diary_catalog import (
    SOURCE_CODE as OFFICIAL_CATALOG_SOURCE_CODE,
)
from ..connectors.official_diary_catalog import (
    OfficialCatalogSnapshot,
)
from ..connectors.querido_diario import CollectedPage, GazettePage
from ..connectors.transferegov import TransferegovPage
from ..connectors.transferegov_download_catalog import (
    TransferegovDownloadCatalogError,
    TransferegovDownloadCatalogSnapshot,
    parse_catalog_items,
)
from ..connectors.transferegov_historical_amendments import (
    HistoricalAmendmentArchiveError,
    HistoricalAmendmentSnapshot,
    parse_historical_amendments_archive,
)
from ..connectors.transferegov_historical_proposals import (
    HistoricalProposalArchiveError,
    HistoricalProposalSnapshot,
    parse_historical_proposals_archive,
)
from .models import (
    ArtifactIntegrityError,
    DirectEditionBatch,
    DocumentBatch,
    DocumentPersistResult,
    OfficialDocumentSearchBatch,
    OfficialDocumentSearchInput,
    PersistenceBatch,
    PersistenceContractError,
    PersistenceResult,
    RawRecordInput,
    RepositoryDirectEditionResult,
    RepositorySearchResult,
    SearchEvidenceArtifact,
)
from .ports import ArtifactObjectStore, CollectionRepository

COLLECTOR_VERSION = "querido-diario-collector/0.1.0"
PARSER_VERSION = "querido-diario-gazette-page/1.0.0"
RECORD_TYPE = "querido_diario_gazette"
DOCUMENT_EXTENSIONS = {"pdf": "pdf", "txt": "txt"}
DIRECT_COLLECTOR_VERSION = "barreiras-diario-collector/0.1.0"
OFFICIAL_CATALOG_COLLECTOR_VERSION = "barreiras-diario-catalog-collector/1.0.0"
PNCP_COLLECTOR_VERSION = "pncp-registry-collector/0.1.0"
PNCP_CONTRATACAO_PARSER_VERSION = "pncp-contratacao-page/1.0.0"
CAMARA_COLLECTOR_VERSION = "camara-federal-collector/0.1.0"
ALBA_COLLECTOR_VERSION = "alba-collector/0.1.0"
ALBA_PARSER_VERSION = "alba-deputados/1.0.0"
ALBA_PROFILE_COLLECTOR_VERSION = "alba-profile-collector/0.1.0"
ALBA_PROFILE_PARSER_VERSION = "alba-deputado-profile/1.1.0"
EXECUTIVE_COLLECTOR_VERSION = "barreiras-executive-collector/1.0.0"
EXECUTIVE_PARSER_VERSION = "barreiras-executive-pages/1.1.1"
TSE_COLLECTOR_VERSION = "tse-collector/0.1.0"
TSE_PARSER_VERSION = "tse-votacao-munzona/1.0.0"
VEREADORES_COLLECTOR_VERSION = "cm-barreiras-collector/0.1.0"
VEREADORES_PARSER_VERSION = "cm-barreiras-vereadores/1.0.0"
MUNICIPAL_TRANSPARENCY_COLLECTOR_VERSION = "municipal-transparency-collector/0.1.0"
MUNICIPAL_TRANSPARENCY_PARSER_VERSION = "municipal-transparency-page/1.0.0"
PNCP_ITEM_PARSER_VERSION = "pncp-item-page/1.0.0"
PNCP_RESULTADO_PARSER_VERSION = "pncp-resultado-page/1.0.0"
PNCP_CONTRATO_PARSER_VERSION = "pncp-contrato-page/1.0.0"
TRANSFEREGOV_COLLECTOR_VERSION = "transferegov-parcerias-collector/1.1.0"
TRANSFEREGOV_PARSER_VERSION = "transferegov-parcerias-page/1.1.0"
TRANSFEREGOV_DOWNLOAD_CATALOG_COLLECTOR_VERSION = (
    "transferegov-download-catalog-collector/1.0.0"
)
TRANSFEREGOV_DOWNLOAD_CATALOG_PARSER_VERSION = (
    "transferegov-download-catalog/1.1.0"
)
TRANSFEREGOV_HISTORICAL_PROPOSAL_COLLECTOR_VERSION = (
    "transferegov-historical-proposals-collector/1.0.0"
)
TRANSFEREGOV_HISTORICAL_PROPOSAL_PARSER_VERSION = (
    "transferegov-historical-proposals/1.0.0"
)
TRANSFEREGOV_HISTORICAL_AMENDMENT_COLLECTOR_VERSION = (
    "transferegov-historical-amendments-collector/1.0.0"
)
TRANSFEREGOV_HISTORICAL_AMENDMENT_PARSER_VERSION = (
    "transferegov-historical-amendments/1.0.0"
)
CGU_FEDERAL_AMENDMENT_COLLECTOR_VERSION = (
    "cgu-federal-amendments-collector/1.0.0"
)
CGU_FEDERAL_AMENDMENT_PARSER_VERSION = "cgu-federal-amendments/1.0.0"
BAHIA_STATE_AMENDMENT_COLLECTOR_VERSION = (
    "bahia-state-amendments-collector/1.0.0"
)
BAHIA_STATE_AMENDMENT_CATALOG_PARSER_VERSION = (
    "bahia-state-amendment-catalog/1.0.0"
)
BAHIA_STATE_AMENDMENT_ARCHIVE_PARSER_VERSION = (
    "bahia-state-amendment-archive/1.2.0"
)
BAHIA_STATE_AMENDMENT_RELATIONSHIP_PARSER_VERSION = (
    "bahia-state-amendment-relationship-diagram/1.0.0"
)
BAHIA_STATE_LOA_ANNEX_COLLECTOR_VERSION = (
    "bahia-state-loa-amendment-annex-collector/1.0.0"
)
BAHIA_STATE_LOA_ANNEX_PARSER_VERSION = (
    "bahia-state-loa-amendment-annex/1.0.0"
)


def executive_record_idempotency_key(
    *,
    profile_key: str,
    payload_sha256: str,
    page_body_sha256: str,
    parser_version: str,
) -> str:
    """Identifica um perfil dentro de uma captura bruta específica.

    O mesmo perfil pode reaparecer em uma nova página oficial. Cada captura
    precisa manter sua própria relação com o bruto, enquanto o replay da
    mesma captura continua idempotente.
    """
    return hashlib.sha256(
        (
            "executive-profile:"
            f"{parser_version}:{page_body_sha256}:{profile_key}:{payload_sha256}"
        ).encode()
    ).hexdigest()


def official_catalog_record_idempotency_key(
    *, catalog_body_sha256: str, source_record_key: str, payload_sha256: str
) -> str:
    """Identifica uma publicação dentro de um snapshot do catálogo."""
    return hashlib.sha256(
        (
            "official-diary-record:"
            f"{catalog_body_sha256}:{source_record_key}:{payload_sha256}"
        ).encode()
    ).hexdigest()


class OfficialDiaryCatalogPersistenceService:
    """Preserva o catálogo HTML e seus registros estruturados por edição."""

    def __init__(self, *, object_store, repository) -> None:
        self.object_store = object_store
        self.repository = repository

    def persist(self, snapshot: OfficialCatalogSnapshot) -> PersistenceResult:
        actual_hash = hashlib.sha256(snapshot.raw_body).hexdigest()
        if (
            actual_hash != snapshot.body_sha256
            or len(snapshot.raw_body) != snapshot.body_size_bytes
        ):
            raise ArtifactIntegrityError(
                "O catálogo oficial não corresponde aos metadados informados."
            )
        object_key = (
            "barreiras-diario/gazettes/catalog/sha256/"
            f"{snapshot.body_sha256[:2]}/{snapshot.body_sha256}.html"
        )
        stored = self.object_store.put_if_absent(
            object_key=object_key,
            body=snapshot.raw_body,
            content_type=snapshot.media_type,
            expected_sha256=snapshot.body_sha256,
        )
        restored = self.object_store.read(object_key)
        if hashlib.sha256(restored).hexdigest() != snapshot.body_sha256:
            raise ArtifactIntegrityError(
                "O catálogo oficial restaurado diverge do bruto coletado."
            )

        records: list[RawRecordInput] = []
        for index, publication in enumerate(snapshot.publications):
            payload = {
                "edition": publication.edition_number,
                "title": publication.title,
                "summary": publication.summary,
                "date": publication.published_date,
                "reference": publication.reference,
                "publication_url": publication.publication_url,
                "summary_url": publication.summary_url,
                "catalog_url": snapshot.final_url,
            }
            payload_hash = hashlib.sha256(self._canonical_json(payload)).hexdigest()
            source_key = (
                f"barreiras-diario:publication:{publication.edition_number}:"
                f"{publication.published_date}"
            )
            records.append(
                RawRecordInput(
                    source_record_key=source_key,
                    record_type="barreiras_diario_publication",
                    record_index=index,
                    payload=payload,
                    payload_sha256=payload_hash,
                    parser_version="barreiras-diario-catalog/1.0.0",
                    idempotency_key=official_catalog_record_idempotency_key(
                        catalog_body_sha256=snapshot.body_sha256,
                        source_record_key=source_key,
                        payload_sha256=payload_hash,
                    ),
                )
            )

        page = CollectedPage(
            schema_name="barreiras-diario-catalog",
            schema_version="1.0.0",
            source_code=OFFICIAL_CATALOG_SOURCE_CODE,
            endpoint_code=OFFICIAL_CATALOG_ENDPOINT_CODE,
            idempotency_key=self._digest(
                f"official-diary-catalog:{snapshot.body_sha256}"
            ),
            request_url=snapshot.request_url,
            final_url=snapshot.final_url,
            requested_at=snapshot.requested_at,
            received_at=snapshot.received_at,
            attempts=snapshot.attempts,
            http_status=snapshot.http_status,
            collection_status="succeeded",
            body_sha256=snapshot.body_sha256,
            body_size_bytes=snapshot.body_size_bytes,
            media_type=snapshot.media_type,
            response_headers=self._safe_headers(snapshot.response_headers),
            cursor={"offset": 0, "size": len(records)},
            raw_body=snapshot.raw_body,
            parsed=GazettePage(
                total_gazettes=len(records),
                gazettes=(),
                source_extensions={"catalog": True},
            ),
        )
        persisted = self.repository.persist(
            PersistenceBatch(
                page=page,
                object_key=object_key,
                artifact_idempotency_key=self._digest(
                    f"official-diary-artifact:{snapshot.body_sha256}"
                ),
                collector_version=OFFICIAL_CATALOG_COLLECTOR_VERSION,
                parser_version="barreiras-diario-catalog/1.0.0",
                records=tuple(records),
            )
        )
        return PersistenceResult(
            collection_run_id=persisted.collection_run_id,
            raw_artifact_id=persisted.raw_artifact_id,
            object_key=object_key,
            sha256=snapshot.body_sha256,
            object_created=stored.created,
            inserted_records=persisted.inserted_records,
            existing_records=persisted.existing_records,
        )

    @staticmethod
    def _canonical_json(value: object) -> bytes:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _safe_headers(headers: dict[str, str] | Any) -> dict[str, str]:
        blocked = {"authorization", "cookie", "set-cookie"}
        return {
            str(key): str(value)
            for key, value in headers.items()
            if str(key).lower() not in blocked
        }


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


class TransferegovPersistenceService:
    """Preserva cada resposta oficial antes da normalizacao financeira."""

    _RESOURCE_CONTRACTS: ClassVar[dict[str, tuple[str, str, str]]] = {
        "propostas-barreiras": (
            "transferegov_proposta",
            "id_proposta",
            "proposta",
        ),
        "distribuicoes-proposta": (
            "transferegov_distribuicao_recurso",
            "id_distribuicao_recurso_proposta",
            "distribuicao",
        ),
        "parcerias-proposta": (
            "transferegov_parceria",
            "id_parceria",
            "parceria",
        ),
        "empenhos-parceria": (
            "transferegov_empenho",
            "id_empenho_parceria",
            "empenho",
        ),
        "documentos-habeis-parceria": (
            "transferegov_documento_habil",
            "id_documento_habil",
            "documento-habil",
        ),
        "ordens-pagamento-documento": (
            "transferegov_ordem_pagamento",
            "id_op",
            "ordem-pagamento",
        ),
    }

    def __init__(self, *, object_store, repository) -> None:
        self.object_store = object_store
        self.repository = repository

    def persist(self, page: TransferegovPage) -> PersistenceResult:
        actual_hash = hashlib.sha256(page.raw_body).hexdigest()
        if (
            actual_hash != page.body_sha256
            or len(page.raw_body) != page.body_size_bytes
        ):
            raise ArtifactIntegrityError(
                "A resposta do Transferegov diverge dos metadados coletados."
            )
        raw_items = self._raw_items(page)
        if raw_items != list(page.items):
            raise ArtifactIntegrityError(
                "Os itens validados divergem da resposta bruta do Transferegov."
            )
        try:
            record_type, identifier_field, key_label = self._RESOURCE_CONTRACTS[
                page.endpoint_code
            ]
        except KeyError as error:
            raise PersistenceContractError(
                f"Endpoint Transferegov sem contrato: {page.endpoint_code}."
            ) from error

        records: list[RawRecordInput] = []
        for index, item in enumerate(page.items):
            identifier = item.get(identifier_field)
            if (
                isinstance(identifier, bool)
                or not isinstance(identifier, int)
                or identifier < 1
            ):
                raise PersistenceContractError(
                    f"Item {index} sem {identifier_field} inteiro positivo."
                )
            canonical = self._canonical_json(item)
            payload_sha256 = hashlib.sha256(canonical).hexdigest()
            record_index = (
                index * 2
                if page.endpoint_code == "ordens-pagamento-documento"
                else index
            )
            records.append(
                RawRecordInput(
                    source_record_key=(
                        f"transferegov:{key_label}:{identifier}"
                    ),
                    record_type=record_type,
                    record_index=record_index,
                    payload=item,
                    payload_sha256=payload_sha256,
                    parser_version=TRANSFEREGOV_PARSER_VERSION,
                    idempotency_key=self._digest(
                        ":".join(
                            (
                                "transferegov-record",
                                page.idempotency_key,
                                TRANSFEREGOV_PARSER_VERSION,
                                str(record_index),
                                payload_sha256,
                            )
                        )
                    ),
                )
            )
            if page.endpoint_code == "ordens-pagamento-documento":
                bank_order = item.get("nr_ordem_bancaria")
                if bank_order is not None and not isinstance(bank_order, str):
                    raise PersistenceContractError(
                        f"Item {index} possui nr_ordem_bancaria inválido."
                    )
                if isinstance(bank_order, str) and bank_order.strip():
                    bank_record_index = record_index + 1
                    records.append(
                        RawRecordInput(
                            source_record_key=(
                                "transferegov:ordem-bancaria:"
                                f"{bank_order.strip()}"
                            ),
                            record_type="transferegov_ordem_bancaria",
                            record_index=bank_record_index,
                            payload=item,
                            payload_sha256=payload_sha256,
                            parser_version=TRANSFEREGOV_PARSER_VERSION,
                            idempotency_key=self._digest(
                                ":".join(
                                    (
                                        "transferegov-record",
                                        page.idempotency_key,
                                        TRANSFEREGOV_PARSER_VERSION,
                                        str(bank_record_index),
                                        payload_sha256,
                                    )
                                )
                            ),
                        )
                    )

        object_key = (
            f"transferegov/parcerias/{page.endpoint_code}/sha256/"
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
            or len(restored) != page.body_size_bytes
            or stored.sha256 != page.body_sha256
        ):
            raise ArtifactIntegrityError(
                "A resposta restaurada do Transferegov diverge da coletada."
            )
        persisted = self.repository.persist(
            PersistenceBatch(
                page=page,  # type: ignore[arg-type]
                object_key=object_key,
                artifact_idempotency_key=self._digest(
                    f"raw-artifact:{page.idempotency_key}"
                ),
                collector_version=TRANSFEREGOV_COLLECTOR_VERSION,
                parser_version=TRANSFEREGOV_PARSER_VERSION,
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

    @staticmethod
    def _raw_items(page: TransferegovPage) -> list[dict]:
        try:
            payload = json.loads(page.raw_body)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ArtifactIntegrityError(
                "A resposta bruta do Transferegov nao e JSON valido."
            ) from error
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ArtifactIntegrityError(
                "A resposta bruta do Transferegov perdeu seu envelope."
            )
        return payload["data"]

    @staticmethod
    def _canonical_json(value: object) -> bytes:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


class TransferegovDownloadCatalogPersistenceService:
    """Preserva o XML integral e materializa somente metadados de downloads."""

    def __init__(self, *, object_store, repository) -> None:
        self.object_store = object_store
        self.repository = repository

    def persist(
        self,
        snapshot: TransferegovDownloadCatalogSnapshot,
    ) -> PersistenceResult:
        actual_hash = hashlib.sha256(snapshot.raw_body).hexdigest()
        if (
            actual_hash != snapshot.body_sha256
            or len(snapshot.raw_body) != snapshot.body_size_bytes
        ):
            raise ArtifactIntegrityError(
                "O XML do catálogo diverge dos metadados coletados."
            )
        try:
            raw_items = parse_catalog_items(snapshot.raw_body)
        except TransferegovDownloadCatalogError as error:
            raise ArtifactIntegrityError(
                "O XML preservado do catálogo perdeu seu contrato."
            ) from error
        if raw_items != snapshot.items:
            raise ArtifactIntegrityError(
                "Os itens validados divergem do XML preservado do catálogo."
            )

        records: list[RawRecordInput] = []
        for index, item in enumerate(snapshot.items):
            name = item.get("name")
            if not isinstance(name, str) or not name:
                raise PersistenceContractError(
                    f"Item {index} do catálogo não possui nome."
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
                    source_record_key=f"transferegov:download:{name}",
                    record_type="transferegov_download_catalog_entry",
                    record_index=index,
                    payload=item,
                    payload_sha256=payload_sha256,
                    parser_version=(
                        TRANSFEREGOV_DOWNLOAD_CATALOG_PARSER_VERSION
                    ),
                    idempotency_key=hashlib.sha256(
                        (
                            "transferegov-download-record:"
                            f"{snapshot.idempotency_key}:{name}:{payload_sha256}"
                        ).encode()
                    ).hexdigest(),
                )
            )

        object_key = (
            "transferegov/parcerias/download-catalog/sha256/"
            f"{snapshot.body_sha256[:2]}/{snapshot.body_sha256}.xml"
        )
        stored = self.object_store.put_if_absent(
            object_key=object_key,
            body=snapshot.raw_body,
            content_type=snapshot.media_type,
            expected_sha256=snapshot.body_sha256,
        )
        restored = self.object_store.read(object_key)
        if (
            hashlib.sha256(restored).hexdigest() != snapshot.body_sha256
            or len(restored) != snapshot.body_size_bytes
            or stored.sha256 != snapshot.body_sha256
        ):
            raise ArtifactIntegrityError(
                "O catálogo restaurado diverge do XML coletado."
            )
        persisted = self.repository.persist(
            PersistenceBatch(
                page=snapshot,  # type: ignore[arg-type]
                object_key=object_key,
                artifact_idempotency_key=hashlib.sha256(
                    f"raw-artifact:{snapshot.idempotency_key}".encode()
                ).hexdigest(),
                collector_version=(
                    TRANSFEREGOV_DOWNLOAD_CATALOG_COLLECTOR_VERSION
                ),
                parser_version=TRANSFEREGOV_DOWNLOAD_CATALOG_PARSER_VERSION,
                records=tuple(records),
            )
        )
        return PersistenceResult(
            collection_run_id=persisted.collection_run_id,
            raw_artifact_id=persisted.raw_artifact_id,
            object_key=object_key,
            sha256=snapshot.body_sha256,
            object_created=stored.created,
            inserted_records=persisted.inserted_records,
            existing_records=persisted.existing_records,
        )


class TransferegovHistoricalProposalPersistenceService:
    """Preserva o ZIP integral e materializa somente o recorte municipal seguro."""

    def __init__(self, *, object_store, repository) -> None:
        self.object_store = object_store
        self.repository = repository

    def persist(self, snapshot: HistoricalProposalSnapshot) -> PersistenceResult:
        actual_hash = hashlib.sha256(snapshot.raw_body).hexdigest()
        if (
            actual_hash != snapshot.body_sha256
            or len(snapshot.raw_body) != snapshot.body_size_bytes
        ):
            raise ArtifactIntegrityError(
                "O ZIP histórico diverge dos metadados coletados."
            )
        try:
            raw_items = parse_historical_proposals_archive(
                snapshot.raw_body,
                year_from=snapshot.year_from,
                year_to=snapshot.year_to,
            )
        except HistoricalProposalArchiveError as error:
            raise ArtifactIntegrityError(
                "O ZIP preservado perdeu seu contrato histórico."
            ) from error
        if raw_items != snapshot.items:
            raise ArtifactIntegrityError(
                "Os itens municipais divergem do ZIP preservado."
            )

        records: list[RawRecordInput] = []
        for index, item in enumerate(snapshot.items):
            proposal_id = item.get("id_proposta")
            if not isinstance(proposal_id, str) or not proposal_id:
                raise PersistenceContractError(
                    f"Proposta histórica {index} não possui identidade."
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
                    source_record_key=(
                        f"transferegov:historical-proposal:{proposal_id}"
                    ),
                    record_type="transferegov_historical_proposal",
                    record_index=index,
                    payload=item,
                    payload_sha256=payload_sha256,
                    parser_version=(
                        TRANSFEREGOV_HISTORICAL_PROPOSAL_PARSER_VERSION
                    ),
                    idempotency_key=hashlib.sha256(
                        (
                            "transferegov-historical-proposal-record:"
                            f"{snapshot.body_sha256}:{proposal_id}:"
                            f"{payload_sha256}"
                        ).encode()
                    ).hexdigest(),
                )
            )

        object_key = (
            "transferegov/parcerias/historical/propostas/sha256/"
            f"{snapshot.body_sha256[:2]}/{snapshot.body_sha256}.zip"
        )
        stored = self.object_store.put_if_absent(
            object_key=object_key,
            body=snapshot.raw_body,
            content_type=snapshot.media_type,
            expected_sha256=snapshot.body_sha256,
        )
        restored = self.object_store.read(object_key)
        if (
            hashlib.sha256(restored).hexdigest() != snapshot.body_sha256
            or len(restored) != snapshot.body_size_bytes
            or stored.sha256 != snapshot.body_sha256
        ):
            raise ArtifactIntegrityError(
                "O ZIP histórico restaurado diverge do arquivo coletado."
            )
        persisted = self.repository.persist(
            PersistenceBatch(
                page=snapshot,  # type: ignore[arg-type]
                object_key=object_key,
                artifact_idempotency_key=hashlib.sha256(
                    f"raw-artifact:{snapshot.idempotency_key}".encode()
                ).hexdigest(),
                collector_version=(
                    TRANSFEREGOV_HISTORICAL_PROPOSAL_COLLECTOR_VERSION
                ),
                parser_version=TRANSFEREGOV_HISTORICAL_PROPOSAL_PARSER_VERSION,
                records=tuple(records),
            )
        )
        return PersistenceResult(
            collection_run_id=persisted.collection_run_id,
            raw_artifact_id=persisted.raw_artifact_id,
            object_key=object_key,
            sha256=snapshot.body_sha256,
            object_created=stored.created,
            inserted_records=persisted.inserted_records,
            existing_records=persisted.existing_records,
        )


class TransferegovHistoricalAmendmentPersistenceService:
    """Preserva o ZIP integral e materializa emendas do recorte comprovado."""

    def __init__(self, *, object_store, repository) -> None:
        self.object_store = object_store
        self.repository = repository

    def persist(self, snapshot: HistoricalAmendmentSnapshot) -> PersistenceResult:
        actual_hash = hashlib.sha256(snapshot.raw_body).hexdigest()
        if (
            actual_hash != snapshot.body_sha256
            or len(snapshot.raw_body) != snapshot.body_size_bytes
        ):
            raise ArtifactIntegrityError(
                "O ZIP histórico de emendas diverge dos metadados coletados."
            )
        try:
            raw_items = parse_historical_amendments_archive(
                snapshot.raw_body,
                proposal_ids=snapshot.proposal_ids,
            )
        except HistoricalAmendmentArchiveError as error:
            raise ArtifactIntegrityError(
                "O ZIP preservado perdeu seu contrato de emendas."
            ) from error
        if raw_items != snapshot.items:
            raise ArtifactIntegrityError(
                "As emendas municipais divergem do ZIP preservado."
            )

        records: list[RawRecordInput] = []
        for index, item in enumerate(snapshot.items):
            identity_fields = (
                item.get("id_proposta"),
                item.get("codigo_programa_emenda"),
                item.get("numero_emenda"),
                item.get("autor_nome"),
            )
            if any(
                not isinstance(value, str) or not value
                for value in identity_fields
            ):
                raise PersistenceContractError(
                    f"Emenda histórica {index} não possui identidade completa."
                )
            identity = ":".join(str(value) for value in identity_fields)
            identity_hash = hashlib.sha256(identity.encode("utf-8")).hexdigest()
            canonical = json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            payload_sha256 = hashlib.sha256(canonical).hexdigest()
            records.append(
                RawRecordInput(
                    source_record_key=(
                        "transferegov:historical-amendment:"
                        f"{identity_fields[0]}:{identity_hash[:24]}"
                    ),
                    record_type="transferegov_historical_amendment",
                    record_index=index,
                    payload=item,
                    payload_sha256=payload_sha256,
                    parser_version=TRANSFEREGOV_HISTORICAL_AMENDMENT_PARSER_VERSION,
                    idempotency_key=hashlib.sha256(
                        (
                            "transferegov-historical-amendment-record:"
                            f"{snapshot.body_sha256}:{identity_hash}:"
                            f"{payload_sha256}"
                        ).encode()
                    ).hexdigest(),
                )
            )

        object_key = (
            "transferegov/parcerias/historical/emendas/sha256/"
            f"{snapshot.body_sha256[:2]}/{snapshot.body_sha256}.zip"
        )
        stored = self.object_store.put_if_absent(
            object_key=object_key,
            body=snapshot.raw_body,
            content_type=snapshot.media_type,
            expected_sha256=snapshot.body_sha256,
        )
        restored = self.object_store.read(object_key)
        if (
            hashlib.sha256(restored).hexdigest() != snapshot.body_sha256
            or len(restored) != snapshot.body_size_bytes
            or stored.sha256 != snapshot.body_sha256
        ):
            raise ArtifactIntegrityError(
                "O ZIP histórico de emendas restaurado diverge do coletado."
            )
        persisted = self.repository.persist(
            PersistenceBatch(
                page=snapshot,  # type: ignore[arg-type]
                object_key=object_key,
                artifact_idempotency_key=hashlib.sha256(
                    f"raw-artifact:{snapshot.idempotency_key}".encode()
                ).hexdigest(),
                collector_version=TRANSFEREGOV_HISTORICAL_AMENDMENT_COLLECTOR_VERSION,
                parser_version=TRANSFEREGOV_HISTORICAL_AMENDMENT_PARSER_VERSION,
                records=tuple(records),
            )
        )
        return PersistenceResult(
            collection_run_id=persisted.collection_run_id,
            raw_artifact_id=persisted.raw_artifact_id,
            object_key=object_key,
            sha256=snapshot.body_sha256,
            object_created=stored.created,
            inserted_records=persisted.inserted_records,
            existing_records=persisted.existing_records,
        )


class CGUFederalAmendmentPersistenceService:
    """Preserva o ZIP integral da CGU antes de materializar Barreiras."""

    def __init__(self, *, object_store, repository) -> None:
        self.object_store = object_store
        self.repository = repository

    def persist(self, snapshot: CGUFederalAmendmentSnapshot) -> PersistenceResult:
        actual_hash = hashlib.sha256(snapshot.raw_body).hexdigest()
        if (
            actual_hash != snapshot.body_sha256
            or len(snapshot.raw_body) != snapshot.body_size_bytes
        ):
            raise ArtifactIntegrityError(
                "O ZIP federal da CGU diverge dos metadados coletados."
            )
        try:
            raw_items = parse_cgu_federal_amendments_archive(snapshot.raw_body)
        except CGUFederalAmendmentArchiveError as error:
            raise ArtifactIntegrityError(
                "O ZIP preservado perdeu seu contrato de emendas federais."
            ) from error
        if raw_items != snapshot.items:
            raise ArtifactIntegrityError(
                "As emendas de Barreiras divergem do ZIP preservado."
            )

        records: list[RawRecordInput] = []
        for index, item in enumerate(snapshot.items):
            identity_fields = (
                item.get("amendment_code"),
                item.get("municipality_ibge"),
                item.get("function_code"),
                item.get("subfunction_code"),
                item.get("program_code"),
                item.get("action_code"),
                item.get("budget_plan_code"),
            )
            if any(
                not isinstance(value, str) or not value
                for value in identity_fields
            ):
                raise PersistenceContractError(
                    f"Emenda federal {index} não possui identidade completa."
                )
            identity = ":".join(str(value) for value in identity_fields)
            identity_hash = hashlib.sha256(identity.encode("utf-8")).hexdigest()
            canonical = json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            payload_sha256 = hashlib.sha256(canonical).hexdigest()
            records.append(
                RawRecordInput(
                    source_record_key=(
                        "cgu:federal-amendment:"
                        f"{identity_fields[0]}:{identity_fields[1]}:"
                        f"{identity_hash[:24]}"
                    ),
                    record_type="cgu_federal_amendment_execution",
                    record_index=index,
                    payload=item,
                    payload_sha256=payload_sha256,
                    parser_version=CGU_FEDERAL_AMENDMENT_PARSER_VERSION,
                    idempotency_key=hashlib.sha256(
                        (
                            "cgu-federal-amendment-record:"
                            f"{snapshot.body_sha256}:{identity_hash}:{payload_sha256}"
                        ).encode()
                    ).hexdigest(),
                )
            )

        object_key = (
            "cgu/emendas-federais/sha256/"
            f"{snapshot.body_sha256[:2]}/{snapshot.body_sha256}.zip"
        )
        stored = self.object_store.put_if_absent(
            object_key=object_key,
            body=snapshot.raw_body,
            content_type=snapshot.media_type,
            expected_sha256=snapshot.body_sha256,
        )
        restored = self.object_store.read(object_key)
        if (
            hashlib.sha256(restored).hexdigest() != snapshot.body_sha256
            or len(restored) != snapshot.body_size_bytes
            or stored.sha256 != snapshot.body_sha256
        ):
            raise ArtifactIntegrityError(
                "O ZIP federal da CGU restaurado diverge do coletado."
            )
        persisted = self.repository.persist(
            PersistenceBatch(
                page=snapshot,  # type: ignore[arg-type]
                object_key=object_key,
                artifact_idempotency_key=hashlib.sha256(
                    f"raw-artifact:{snapshot.idempotency_key}".encode()
                ).hexdigest(),
                collector_version=CGU_FEDERAL_AMENDMENT_COLLECTOR_VERSION,
                parser_version=CGU_FEDERAL_AMENDMENT_PARSER_VERSION,
                records=tuple(records),
            )
        )
        return PersistenceResult(
            collection_run_id=persisted.collection_run_id,
            raw_artifact_id=persisted.raw_artifact_id,
            object_key=object_key,
            sha256=snapshot.body_sha256,
            object_created=stored.created,
            inserted_records=persisted.inserted_records,
            existing_records=persisted.existing_records,
        )


class BahiaStateAmendmentCatalogPersistenceService:
    """Preserva o JSON CKAN antes de baixar o ZIP que ele descreve."""

    def __init__(self, *, object_store, repository) -> None:
        self.object_store = object_store
        self.repository = repository

    def persist(
        self,
        snapshot: BahiaStateAmendmentCatalogSnapshot,
    ) -> PersistenceResult:
        _verify_state_amendment_bytes(
            snapshot,
            description="catálogo estadual de emendas",
        )
        try:
            resource = parse_state_amendment_catalog(snapshot.raw_body)
        except BahiaStateAmendmentArchiveError as error:
            raise ArtifactIntegrityError(
                "O catálogo estadual preservado perdeu seu contrato."
            ) from error
        if snapshot.items != (resource,):
            raise ArtifactIntegrityError(
                "O recurso estadual diverge do catálogo preservado."
            )
        record = _state_amendment_record(
            payload=resource,
            source_record_key=(
                "bahia:state-amendment-catalog:"
                f"{resource['resource_id']}"
            ),
            record_type="bahia_state_amendment_catalog_resource",
            parser_version=BAHIA_STATE_AMENDMENT_CATALOG_PARSER_VERSION,
            record_index=0,
            snapshot_key=snapshot.idempotency_key,
        )
        object_key = (
            "bahia/emendas-estaduais/catalog/sha256/"
            f"{snapshot.body_sha256[:2]}/{snapshot.body_sha256}.json"
        )
        return _persist_state_amendment_snapshot(
            snapshot=snapshot,
            records=(record,),
            object_key=object_key,
            collector_version=BAHIA_STATE_AMENDMENT_COLLECTOR_VERSION,
            parser_version=BAHIA_STATE_AMENDMENT_CATALOG_PARSER_VERSION,
            object_store=self.object_store,
            repository=self.repository,
            restored_description="catálogo estadual restaurado",
        )


class BahiaStateAmendmentArchivePersistenceService:
    """Preserva o ZIP integral e materializa somente o manifesto das views."""

    def __init__(self, *, object_store, repository) -> None:
        self.object_store = object_store
        self.repository = repository

    def persist(
        self,
        snapshot: BahiaStateAmendmentArchiveSnapshot,
    ) -> PersistenceResult:
        _verify_state_amendment_bytes(
            snapshot,
            description="ZIP estadual de emendas",
        )
        try:
            members = parse_state_amendment_archive(snapshot.raw_body)
        except BahiaStateAmendmentArchiveError as error:
            raise ArtifactIntegrityError(
                "O ZIP estadual preservado perdeu seu contrato."
            ) from error
        if members != snapshot.items:
            raise ArtifactIntegrityError(
                "O manifesto do ZIP estadual diverge do arquivo preservado."
            )
        records = tuple(
            _state_amendment_record(
                payload=member,
                source_record_key=(
                    "bahia:state-amendment-archive-member:"
                    f"{member['member_name']}:{member['content_sha256']}"
                ),
                record_type="bahia_state_amendment_archive_member",
                parser_version=BAHIA_STATE_AMENDMENT_ARCHIVE_PARSER_VERSION,
                record_index=index,
                snapshot_key=snapshot.idempotency_key,
            )
            for index, member in enumerate(members)
        )
        object_key = (
            "bahia/emendas-estaduais/archive/sha256/"
            f"{snapshot.body_sha256[:2]}/{snapshot.body_sha256}.zip"
        )
        return _persist_state_amendment_snapshot(
            snapshot=snapshot,
            records=records,
            object_key=object_key,
            collector_version=BAHIA_STATE_AMENDMENT_COLLECTOR_VERSION,
            parser_version=BAHIA_STATE_AMENDMENT_ARCHIVE_PARSER_VERSION,
            object_store=self.object_store,
            repository=self.repository,
            restored_description="ZIP estadual restaurado",
        )


class BahiaStateAmendmentRelationshipPersistenceService:
    """Preserva o diagrama oficial e somente seu manifesto técnico."""

    def __init__(self, *, object_store, repository) -> None:
        self.object_store = object_store
        self.repository = repository

    def persist(
        self,
        snapshot: BahiaStateAmendmentRelationshipSnapshot,
    ) -> PersistenceResult:
        _verify_state_amendment_bytes(
            snapshot,
            description="diagrama estadual de relacionamento",
        )
        if len(snapshot.items) != 1:
            raise ArtifactIntegrityError(
                "O diagrama estadual não possui um manifesto único."
            )
        manifest = snapshot.items[0]
        try:
            validate_state_amendment_relationship_manifest(
                snapshot.raw_body,
                manifest,
            )
        except BahiaStateAmendmentArchiveError as error:
            raise ArtifactIntegrityError(
                "O diagrama estadual preservado perdeu seu contrato."
            ) from error
        record = _state_amendment_record(
            payload=manifest,
            source_record_key=(
                "bahia:state-amendment-relationship-diagram:"
                f"{manifest['resource_id']}:{manifest['content_sha256']}"
            ),
            record_type="bahia_state_amendment_relationship_diagram",
            parser_version=BAHIA_STATE_AMENDMENT_RELATIONSHIP_PARSER_VERSION,
            record_index=0,
            snapshot_key=snapshot.idempotency_key,
        )
        object_key = (
            "bahia/emendas-estaduais/relationship-diagram/sha256/"
            f"{snapshot.body_sha256[:2]}/{snapshot.body_sha256}.png"
        )
        return _persist_state_amendment_snapshot(
            snapshot=snapshot,
            records=(record,),
            object_key=object_key,
            collector_version=BAHIA_STATE_AMENDMENT_COLLECTOR_VERSION,
            parser_version=BAHIA_STATE_AMENDMENT_RELATIONSHIP_PARSER_VERSION,
            object_store=self.object_store,
            repository=self.repository,
            restored_description="diagrama estadual restaurado",
        )


class BahiaStateLoaAmendmentAnnexPersistenceService:
    """Preserva o PDF anual e um manifesto tecnico sem valores financeiros."""

    def __init__(self, *, object_store, repository) -> None:
        self.object_store = object_store
        self.repository = repository

    def persist(self, snapshot: StateLoaAnnexSnapshot) -> PersistenceResult:
        _verify_state_amendment_bytes(
            snapshot,
            description="anexo anual da LOA",
        )
        contract = YEARLY_ANNEXES.get(snapshot.fiscal_year)
        if contract is None:
            raise ArtifactIntegrityError(
                "O ano do anexo da LOA nao possui contrato preservavel."
            )
        try:
            manifest = build_state_loa_annex_manifest(
                snapshot.raw_body,
                contract=contract,
            )
        except BahiaStateLoaAnnexError as error:
            raise ArtifactIntegrityError(
                "O PDF anual da LOA perdeu seu contrato."
            ) from error
        if snapshot.items != (manifest,):
            raise ArtifactIntegrityError(
                "O manifesto do anexo da LOA diverge do PDF preservado."
            )
        record = _state_amendment_record(
            payload=manifest,
            source_record_key=(
                "bahia:state-loa-amendment-annex:"
                f"{snapshot.fiscal_year}:{snapshot.annex_code}:"
                f"{snapshot.body_sha256}"
            ),
            record_type="bahia_state_loa_amendment_annex",
            parser_version=BAHIA_STATE_LOA_ANNEX_PARSER_VERSION,
            record_index=0,
            snapshot_key=snapshot.idempotency_key,
        )
        object_key = (
            "bahia/loa-emendas-estaduais/"
            f"{snapshot.fiscal_year}/sha256/{snapshot.body_sha256[:2]}/"
            f"{snapshot.body_sha256}.pdf"
        )
        return _persist_state_amendment_snapshot(
            snapshot=snapshot,
            records=(record,),
            object_key=object_key,
            collector_version=BAHIA_STATE_LOA_ANNEX_COLLECTOR_VERSION,
            parser_version=BAHIA_STATE_LOA_ANNEX_PARSER_VERSION,
            object_store=self.object_store,
            repository=self.repository,
            restored_description="anexo anual da LOA restaurado",
        )


def _verify_state_amendment_bytes(snapshot, *, description: str) -> None:
    actual_hash = hashlib.sha256(snapshot.raw_body).hexdigest()
    if (
        actual_hash != snapshot.body_sha256
        or len(snapshot.raw_body) != snapshot.body_size_bytes
    ):
        raise ArtifactIntegrityError(
            f"O {description} diverge dos metadados coletados."
        )


def _state_amendment_record(
    *,
    payload: dict[str, object],
    source_record_key: str,
    record_type: str,
    parser_version: str,
    record_index: int,
    snapshot_key: str,
) -> RawRecordInput:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    payload_sha256 = hashlib.sha256(canonical).hexdigest()
    return RawRecordInput(
        source_record_key=source_record_key,
        record_type=record_type,
        record_index=record_index,
        payload=payload,
        payload_sha256=payload_sha256,
        parser_version=parser_version,
        idempotency_key=hashlib.sha256(
            (
                "bahia-state-amendment-record:"
                f"{snapshot_key}:{parser_version}:{record_index}:{payload_sha256}"
            ).encode()
        ).hexdigest(),
    )


def _persist_state_amendment_snapshot(
    *,
    snapshot,
    records: tuple[RawRecordInput, ...],
    object_key: str,
    collector_version: str,
    parser_version: str,
    object_store,
    repository,
    restored_description: str,
) -> PersistenceResult:
    stored = object_store.put_if_absent(
        object_key=object_key,
        body=snapshot.raw_body,
        content_type=snapshot.media_type,
        expected_sha256=snapshot.body_sha256,
    )
    restored = object_store.read(object_key)
    if (
        hashlib.sha256(restored).hexdigest() != snapshot.body_sha256
        or len(restored) != snapshot.body_size_bytes
        or stored.sha256 != snapshot.body_sha256
        or stored.byte_size != snapshot.body_size_bytes
    ):
        raise ArtifactIntegrityError(
            f"O {restored_description} diverge do bruto coletado."
        )
    persisted = repository.persist(
        PersistenceBatch(
            page=snapshot,  # type: ignore[arg-type]
            object_key=object_key,
            artifact_idempotency_key=hashlib.sha256(
                f"raw-artifact:{snapshot.idempotency_key}".encode()
            ).hexdigest(),
            collector_version=collector_version,
            parser_version=parser_version,
            records=records,
        )
    )
    return PersistenceResult(
        collection_run_id=persisted.collection_run_id,
        raw_artifact_id=persisted.raw_artifact_id,
        object_key=object_key,
        sha256=snapshot.body_sha256,
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

    def preserved_document_identities(
        self,
        source_record_keys: tuple[str, ...],
    ) -> frozenset[tuple[str, str]]:
        """Retorna identidade e URL já preservadas sem expor o Storage."""

        return self.repository.municipal_document_identities(source_record_keys)

    def persist_official_document_searches(
        self,
        *,
        source_code: str,
        endpoint_code: str,
        resource: str,
        searches: tuple[OfficialDocumentSearchInput, ...],
        page_evidence: tuple[tuple[PersistenceResult, MunicipalTransparencyPage], ...],
    ) -> RepositorySearchResult:
        """Registra o resultado mensal apenas após preservar todas as páginas."""

        if not searches or not page_evidence:
            raise PersistenceContractError(
                "Busca oficial exige períodos e respostas brutas preservadas."
            )
        evidence = tuple(
            SearchEvidenceArtifact(
                raw_artifact_id=result.raw_artifact_id,
                sha256=page.body_sha256,
                source_url=page.request_url,
                retrieved_at=page.received_at,
            )
            for result, page in page_evidence
        )
        return self.repository.persist_official_document_searches(
            OfficialDocumentSearchBatch(
                source_code=source_code,
                endpoint_code=endpoint_code,
                resource=resource,
                searches=searches,
                evidence_artifacts=evidence,
                methodology_version="official-document-search/1.0.0",
            )
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
            if not isinstance(compra_controle, str):
                compra_controle = item.get("numeroControlePncpCompra")
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

    def persist_profile(self, page) -> PersistenceResult:
        """Preserva uma página individual da ALBA e sua foto oficial."""
        actual = hashlib.sha256(page.raw_body).hexdigest()
        if actual != page.body_sha256:
            raise ArtifactIntegrityError(
                "O perfil da Assembleia não corresponde ao hash informado."
            )
        if len(page.items) != 1:
            raise PersistenceContractError(
                "O perfil da Assembleia deve conter exatamente um registro."
            )
        item = page.items[0]
        identifier = item.get("id_alba")
        profile_url = item.get("perfil_url")
        if (
            not isinstance(identifier, str)
            or not identifier.isdigit()
            or not isinstance(profile_url, str)
            or not profile_url.startswith(
                "https://www.al.ba.gov.br/deputados/deputado-estadual/"
            )
        ):
            raise PersistenceContractError(
                "Perfil estadual sem identificador ou URL oficial."
            )
        canonical = json.dumps(
            item,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        payload_sha256 = hashlib.sha256(canonical).hexdigest()
        record = RawRecordInput(
            source_record_key=f"alba:deputado-profile:{identifier}",
            record_type="alba_deputado_estadual_profile",
            record_index=0,
            payload=item,
            payload_sha256=payload_sha256,
            parser_version=ALBA_PROFILE_PARSER_VERSION,
            idempotency_key=hashlib.sha256(
                ":".join(
                    (
                        "alba-deputado-profile",
                        page.idempotency_key,
                        ALBA_PROFILE_PARSER_VERSION,
                        payload_sha256,
                    )
                ).encode()
            ).hexdigest(),
        )
        object_key = (
            "alba/deputados/profiles/sha256/"
            f"{page.body_sha256[:2]}/{page.body_sha256}.html"
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
                "O perfil restaurado da ALBA diverge do coletado."
            )
        artifact_key = hashlib.sha256(
            f"raw-artifact:{page.idempotency_key}".encode()
        ).hexdigest()
        persisted = self.repository.persist(
            PersistenceBatch(
                page=page,
                object_key=object_key,
                artifact_idempotency_key=artifact_key,
                collector_version=ALBA_PROFILE_COLLECTOR_VERSION,
                parser_version=ALBA_PROFILE_PARSER_VERSION,
                records=(record,),
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


class MunicipalExecutivePersistenceService:
    """Preserva páginas e perfis oficiais do Executivo de Barreiras."""

    def __init__(self, *, object_store, repository) -> None:
        self.object_store = object_store
        self.repository = repository

    def persist(self, page) -> PersistenceResult:
        actual = hashlib.sha256(page.raw_body).hexdigest()
        if actual != page.body_sha256:
            raise ArtifactIntegrityError(
                "As páginas do Executivo não correspondem ao hash informado."
            )
        object_key = (
            "prefeitura/executivo/sha256/"
            f"{page.body_sha256[:2]}/{page.body_sha256}.json"
        )
        records = []
        for index, item in enumerate(page.items):
            profile_key = item.get("profile_key")
            name = item.get("display_name")
            role = item.get("role")
            if not isinstance(profile_key, str) or not profile_key:
                raise PersistenceContractError(f"Perfil {index} sem chave estável.")
            if not isinstance(name, str) or not name.strip():
                raise PersistenceContractError(f"Perfil {index} sem nome oficial.")
            if role not in {"prefeito", "vice-prefeito", "secretario"}:
                raise PersistenceContractError(f"Perfil {index} com função inválida.")
            canonical = json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            payload_sha256 = hashlib.sha256(canonical).hexdigest()
            records.append(
                RawRecordInput(
                    source_record_key=f"barreiras:executive:{profile_key}",
                    record_type="barreiras_executive_profile",
                    record_index=index,
                    payload=item,
                    payload_sha256=payload_sha256,
                    parser_version=EXECUTIVE_PARSER_VERSION,
                    idempotency_key=executive_record_idempotency_key(
                        profile_key=profile_key,
                        payload_sha256=payload_sha256,
                        page_body_sha256=page.body_sha256,
                        parser_version=EXECUTIVE_PARSER_VERSION,
                    ),
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
                "O envelope restaurado do Executivo diverge da coleta."
            )
        persisted = self.repository.persist(
            PersistenceBatch(
                page=page,
                object_key=object_key,
                artifact_idempotency_key=hashlib.sha256(f"raw-artifact:{page.idempotency_key}".encode()).hexdigest(),
                collector_version=EXECUTIVE_COLLECTOR_VERSION,
                parser_version=EXECUTIVE_PARSER_VERSION,
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
