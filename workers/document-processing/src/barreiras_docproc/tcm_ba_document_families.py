"""Inventário privado e determinístico das famílias documentais do TCM-BA."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol

from .processing import TextArtifact

EXTRACTOR_VERSION = "tcm-ba-document-family-inventory/1.0.0"
VALIDATOR_VERSION = "official-catalog-category-allowlist/1.0.0"
JOB_TYPE = "tcm_ba_document_family_inventory"

_CODE_PATTERN = re.compile(r"^\s*(PCMGE\d{3})(?:\b|\s*[-\u2013\u2014])", re.IGNORECASE)
_FAMILY_BY_CODE = {
    "PCMGE004": "cide_transfer_proofs",
    "PCMGE005": "fundeb_transfer_proofs",
    "PCMGE006": "royalties_transfer_proofs",
    "PCMGE008": "legislative_transfer_proofs",
    "PCMGE009": "contracts_and_amendments",
    "PCMGE010": "agreements_and_credit_notices",
    "PCMGE011": "qdd_decrees",
    "PCMGE012": "special_credit_decrees",
}


@dataclass(frozen=True)
class TcmBaCatalogDocument:
    artifact: TextArtifact
    source_record_key: str
    official_category: str


@dataclass(frozen=True)
class TcmBaDocumentFamilyClassification:
    family: str
    status: str
    basis: str
    official_category_code: str | None


@dataclass(frozen=True)
class TcmBaDocumentFamilyBatch:
    document: TcmBaCatalogDocument
    classification: TcmBaDocumentFamilyClassification
    job_type: str
    job_idempotency_key: str
    extractor_version: str


@dataclass(frozen=True)
class TcmBaDocumentFamilyPersistResult:
    job_created: bool
    results_inserted: int
    family: str


class TcmBaDocumentFamilyRepository(Protocol):
    def persist_document_family(
        self,
        batch: TcmBaDocumentFamilyBatch,
    ) -> TcmBaDocumentFamilyPersistResult: ...


def _plain(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    return " ".join(without_marks.casefold().split())


def classify_document_family(
    official_category: str,
) -> TcmBaDocumentFamilyClassification:
    """Classifica apenas pelo metadado literal publicado no catálogo oficial."""

    match = _CODE_PATTERN.match(official_category)
    category_code = match.group(1).upper() if match else None
    family = _FAMILY_BY_CODE.get(category_code or "")
    if family is None and _plain(official_category) == "documentos adicionais":
        family = "additional_documents"
    if family is None:
        return TcmBaDocumentFamilyClassification(
            family="unknown",
            status="unknown",
            basis="official_catalog_category",
            official_category_code=category_code,
        )
    return TcmBaDocumentFamilyClassification(
        family=family,
        status="classified",
        basis="official_catalog_category",
        official_category_code=category_code,
    )


def document_family_job_idempotency_key(artifact_sha256: str) -> str:
    material = (
        f"tcm-ba-document-family:{artifact_sha256}:{EXTRACTOR_VERSION}"
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def document_family_payload(
    document: TcmBaCatalogDocument,
    classification: TcmBaDocumentFamilyClassification,
) -> dict[str, object]:
    """Retorna somente o inventário necessário, sem nome nem valor documental."""

    return {
        "schema_name": "tcm-ba-document-family",
        "schema_version": "1.0.0",
        "family": classification.family,
        "classification_status": classification.status,
        "classification_basis": classification.basis,
        "official_category_code": classification.official_category_code,
        "source_record_key": document.source_record_key,
        "source_artifact_sha256": document.artifact.sha256,
        "extractor_version": EXTRACTOR_VERSION,
    }


class TcmBaDocumentFamilyService:
    def __init__(self, *, repository: TcmBaDocumentFamilyRepository) -> None:
        self.repository = repository

    def process(
        self,
        document: TcmBaCatalogDocument,
    ) -> TcmBaDocumentFamilyPersistResult:
        classification = classify_document_family(document.official_category)
        return self.repository.persist_document_family(
            TcmBaDocumentFamilyBatch(
                document=document,
                classification=classification,
                job_type=JOB_TYPE,
                job_idempotency_key=document_family_job_idempotency_key(
                    document.artifact.sha256
                ),
                extractor_version=EXTRACTOR_VERSION,
            )
        )
