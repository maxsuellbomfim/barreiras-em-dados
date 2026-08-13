"""Processamento verificavel do retrato estadual de execucao de emendas."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from .bahia_state_execution import (
    STATE_EXECUTION_PARSER_VERSION,
    StateExecutionAggregate,
    parse_state_execution_archive,
)

STATE_EXECUTION_JOB_TYPE = "bahia_state_execution_aggregates_v1"
STATE_EXECUTION_VALIDATOR_VERSION = "bahia-state-execution-deterministic/1.0.0"


class StateExecutionProcessingError(RuntimeError):
    """O retrato estadual nao pode produzir resultados confiaveis."""


class StateExecutionArtifactMismatchError(StateExecutionProcessingError):
    """Os bytes restaurados divergem do hash imutavel da coleta."""


class StateExecutionEmptySnapshotError(StateExecutionProcessingError):
    """O retrato oficial nao contem linhas financeiras publicaveis."""


@dataclass(frozen=True)
class StateExecutionArtifact:
    raw_artifact_id: str
    sha256: str
    object_key: str
    source_url: str
    collected_at: str


@dataclass(frozen=True)
class StateExecutionExtractionBatch:
    artifact: StateExecutionArtifact
    aggregates: tuple[StateExecutionAggregate, ...]
    job_type: str
    idempotency_key: str
    extractor_version: str
    validator_version: str


@dataclass(frozen=True)
class StateExecutionPersistResult:
    job_created: bool
    results_inserted: int


class ObjectReader(Protocol):
    def read(self, object_key: str) -> bytes: ...


class StateExecutionRepository(Protocol):
    def persist_extraction(
        self,
        batch: StateExecutionExtractionBatch,
    ) -> StateExecutionPersistResult: ...


def execution_job_idempotency_key(artifact_sha256: str) -> str:
    material = ":".join(
        (
            STATE_EXECUTION_JOB_TYPE,
            artifact_sha256,
            STATE_EXECUTION_PARSER_VERSION,
            STATE_EXECUTION_VALIDATOR_VERSION,
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def execution_payload(
    aggregate: StateExecutionAggregate,
    artifact: StateExecutionArtifact,
) -> dict[str, object]:
    return {
        "schema_name": "bahia-state-execution-aggregate",
        "schema_version": "1.0.0",
        "fiscal_year": aggregate.fiscal_year,
        "agency_name": aggregate.agency_name,
        "agency_code": aggregate.agency_code,
        "budget_unit_name": aggregate.budget_unit_name,
        "budget_unit_code": aggregate.budget_unit_code,
        "action_name": aggregate.action_name,
        "action_code": aggregate.action_code,
        "author_name": aggregate.author_name,
        "author_external_code": aggregate.author_external_code,
        "execution_code": aggregate.execution_code,
        "initial_budget_amount": format(aggregate.initial_budget_amount, "f"),
        "current_budget_amount": format(aggregate.current_budget_amount, "f"),
        "committed_amount": format(aggregate.committed_amount, "f"),
        "liquidated_amount": format(aggregate.liquidated_amount, "f"),
        "paid_amount": format(aggregate.paid_amount, "f"),
        "territorial_scope": aggregate.territorial_scope,
        "evidence_text": aggregate.evidence_text,
        "evidence_sha256": aggregate.evidence_sha256,
        "source_url": artifact.source_url,
        "source_artifact_sha256": artifact.sha256,
        "source_collected_at": artifact.collected_at,
        "parser_version": aggregate.parser_version,
    }


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


class StateExecutionExtractionService:
    def __init__(self, *, object_reader: ObjectReader, repository) -> None:
        self.object_reader = object_reader
        self.repository = repository

    def process(
        self,
        artifact: StateExecutionArtifact,
    ) -> StateExecutionPersistResult:
        raw_body = self.object_reader.read(artifact.object_key)
        if hashlib.sha256(raw_body).hexdigest() != artifact.sha256:
            raise StateExecutionArtifactMismatchError(
                "O ZIP estadual restaurado diverge do hash coletado."
            )
        aggregates = parse_state_execution_archive(raw_body)
        if not aggregates:
            raise StateExecutionEmptySnapshotError(
                "O ZIP estadual verificado nao contem linhas de execucao financeira."
            )
        batch = StateExecutionExtractionBatch(
            artifact=artifact,
            aggregates=aggregates,
            job_type=STATE_EXECUTION_JOB_TYPE,
            idempotency_key=execution_job_idempotency_key(artifact.sha256),
            extractor_version=STATE_EXECUTION_PARSER_VERSION,
            validator_version=STATE_EXECUTION_VALIDATOR_VERSION,
        )
        return self.repository.persist_extraction(batch)
