"""Tipos da fronteira entre aquisição, Storage e PostgreSQL."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from ..connectors.gazette_documents import CollectedDocument
from ..connectors.querido_diario import CollectedPage


class PersistenceError(RuntimeError):
    """Falha explícita ao preservar ou registrar uma coleta."""


class ArtifactIntegrityError(PersistenceError):
    """Os bytes restaurados não correspondem ao hash esperado."""


class PersistenceContractError(PersistenceError):
    """O bruto e a representação validada deixaram de concordar."""


@dataclass(frozen=True)
class StoredObject:
    object_key: str
    sha256: str
    byte_size: int
    created: bool


@dataclass(frozen=True)
class RawRecordInput:
    source_record_key: str
    record_type: str
    record_index: int
    payload: dict[str, Any]
    payload_sha256: str
    parser_version: str
    idempotency_key: str


@dataclass(frozen=True)
class PersistenceBatch:
    page: CollectedPage
    object_key: str
    artifact_idempotency_key: str
    collector_version: str
    parser_version: str
    records: tuple[RawRecordInput, ...]


@dataclass(frozen=True)
class RepositoryPersistResult:
    collection_run_id: str
    raw_artifact_id: str
    inserted_records: int
    existing_records: int


@dataclass(frozen=True)
class RawRecordEvidence:
    record_type: str
    source_record_key: str
    payload_sha256: str


@dataclass(frozen=True)
class PersistenceResult:
    collection_run_id: str
    raw_artifact_id: str
    object_key: str
    sha256: str
    object_created: bool
    inserted_records: int
    existing_records: int
    record_evidence: tuple[RawRecordEvidence, ...] = ()


@dataclass(frozen=True)
class OfficialDocumentSearchInput:
    fiscal_year: int
    reference_month: int
    period_start: date
    period_end: date
    search_status: str
    match_count: int


@dataclass(frozen=True)
class SearchEvidenceArtifact:
    raw_artifact_id: str
    sha256: str
    source_url: str
    retrieved_at: str


@dataclass(frozen=True)
class OfficialDocumentSearchBatch:
    source_code: str
    endpoint_code: str
    resource: str
    searches: tuple[OfficialDocumentSearchInput, ...]
    evidence_artifacts: tuple[SearchEvidenceArtifact, ...]
    methodology_version: str


@dataclass(frozen=True)
class RepositorySearchResult:
    inserted_searches: int
    existing_searches: int


@dataclass(frozen=True)
class DocumentBatch:
    source_code: str
    endpoint_code: str
    collection_run_id: str
    parent_artifact_id: str
    source_record_key: str
    document: CollectedDocument
    object_key: str
    idempotency_key: str
    collector_version: str
    document_schema_name: str = "gazette-document"
    document_object_prefix: str = "querido-diario/gazettes/documents"


@dataclass(frozen=True)
class RepositoryDocumentResult:
    raw_artifact_id: str
    created: bool


@dataclass(frozen=True)
class DocumentPersistResult:
    raw_artifact_id: str
    object_key: str
    sha256: str
    object_created: bool
    artifact_created: bool


@dataclass(frozen=True)
class TcmBaDocumentReference:
    competence: str
    expected_total_documents: int
    document_position: int
    source_record_key: str
    parent_artifact_id: str
    category: str
    name: str
    inserted_at: str
    page_number: int
    download_form_id: str


@dataclass(frozen=True)
class TcmBaDocumentSelection:
    competence: str
    expected_total_documents: int
    preserved_documents: int
    pending_documents: int
    references: tuple[TcmBaDocumentReference, ...]


@dataclass(frozen=True)
class TcmBaDocumentAuditArtifact:
    artifact_id: str
    parent_artifact_id: str
    object_key: str
    sha256: str
    byte_size: int
    content_type: str
    http_status: int
    schema_name: str
    source_record_key: str


@dataclass(frozen=True)
class TcmBaDocumentAuditSnapshot:
    competence: str
    partition_status: str
    partition_completed_at: datetime
    observed_records: int
    checkpoint: Mapping[str, object]
    run_status: str
    metrics: Mapping[str, object]
    artifacts: tuple[TcmBaDocumentAuditArtifact, ...]
    catalog_links: int
    current_open_failures: int
    historical_open_failures: int


@dataclass(frozen=True)
class DirectEditionBatch:
    source_code: str
    endpoint_code: str
    edition_number: int
    edition_year: int
    document: CollectedDocument
    object_key: str
    artifact_idempotency_key: str
    run_idempotency_key: str
    collector_version: str


@dataclass(frozen=True)
class RepositoryDirectEditionResult:
    collection_run_id: str
    raw_artifact_id: str
    created: bool
