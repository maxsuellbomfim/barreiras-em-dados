"""Processamento verificável do recorte territorial de transferências especiais."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from .bahia_special_transfers import (
    SPECIAL_TRANSFER_PARSER_VERSION,
    SpecialTransferPaymentCandidate,
    SpecialTransferYearCoverage,
    analyze_special_transfer_payments,
)

SPECIAL_TRANSFER_JOB_TYPE = "bahia_special_transfer_payments_v3"
SPECIAL_TRANSFER_VALIDATOR_VERSION = (
    "bahia-special-transfer-territorial-deterministic/1.0.0"
)


class SpecialTransferProcessingError(RuntimeError):
    """O retrato estadual não pode produzir resultados confiáveis."""


class SpecialTransferArtifactMismatchError(SpecialTransferProcessingError):
    """Os bytes restaurados divergem do hash imutável da coleta."""


@dataclass(frozen=True)
class SpecialTransferArtifact:
    raw_artifact_id: str
    sha256: str
    object_key: str
    source_url: str
    collected_at: str


@dataclass(frozen=True)
class SpecialTransferExtractionBatch:
    artifact: SpecialTransferArtifact
    candidates: tuple[SpecialTransferPaymentCandidate, ...]
    annual_coverage: tuple[SpecialTransferYearCoverage, ...]
    job_type: str
    idempotency_key: str
    extractor_version: str
    validator_version: str


@dataclass(frozen=True)
class SpecialTransferPersistResult:
    job_created: bool
    results_inserted: int


class ObjectReader(Protocol):
    def read(self, object_key: str) -> bytes: ...


class SpecialTransferRepository(Protocol):
    def persist_extraction(
        self,
        batch: SpecialTransferExtractionBatch,
    ) -> SpecialTransferPersistResult: ...


def special_transfer_job_idempotency_key(artifact_sha256: str) -> str:
    material = ":".join(
        (
            SPECIAL_TRANSFER_JOB_TYPE,
            artifact_sha256,
            SPECIAL_TRANSFER_PARSER_VERSION,
            SPECIAL_TRANSFER_VALIDATOR_VERSION,
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


class SpecialTransferExtractionService:
    def __init__(self, *, object_reader: ObjectReader, repository) -> None:
        self.object_reader = object_reader
        self.repository = repository

    def process(
        self,
        artifact: SpecialTransferArtifact,
    ) -> SpecialTransferPersistResult:
        raw_body = self.object_reader.read(artifact.object_key)
        if hashlib.sha256(raw_body).hexdigest() != artifact.sha256:
            raise SpecialTransferArtifactMismatchError(
                "O ZIP de transferências especiais diverge do hash coletado."
            )
        analysis = analyze_special_transfer_payments(raw_body)
        batch = SpecialTransferExtractionBatch(
            artifact=artifact,
            candidates=analysis.candidates,
            annual_coverage=analysis.annual_coverage,
            job_type=SPECIAL_TRANSFER_JOB_TYPE,
            idempotency_key=special_transfer_job_idempotency_key(artifact.sha256),
            extractor_version=SPECIAL_TRANSFER_PARSER_VERSION,
            validator_version=SPECIAL_TRANSFER_VALIDATOR_VERSION,
        )
        return self.repository.persist_extraction(batch)
