"""Processamento verificavel dos anexos estaduais da LOA destinados a Barreiras."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from .bahia_state_loa import (
    LOA_BARREIRAS_PARSER_VERSION,
    LOA_SCOPE_PARSER_VERSION,
    AuthorizedLoaAmendment,
    Loa2026ScopeRow,
    LoaPage,
    parse_barreiras_loa_pages,
    parse_loa_2026_scope_pages,
)
from .pdf_text import PDF_PARSER_VERSION, derive_pdf_text
from .processing import PageInput

# A versao no tipo permite que um parser futuro reprocesse artefatos que tenham
# chegado a dead-letter sob um contrato antigo, sem apagar o historico.
LOA_EXTRACTION_JOB_TYPE = "bahia_state_loa_authorized_amendments_and_scope_v3"
LOA_VALIDATOR_VERSION = "bahia-state-loa-deterministic/1.0.0"


class LoaProcessingError(RuntimeError):
    """O anexo nao pode gerar resultados financeiros confiaveis."""


class LoaArtifactMismatchError(LoaProcessingError):
    """Os bytes restaurados divergem do hash imutavel coletado."""


class LoaIncompleteTextError(LoaProcessingError):
    """O texto integral necessario para extracao nao esta disponivel."""


@dataclass(frozen=True)
class BahiaStateLoaArtifact:
    raw_artifact_id: str
    raw_record_id: str
    sha256: str
    object_key: str
    fiscal_year: int
    annex_code: str
    source_url: str


@dataclass(frozen=True)
class BahiaStateLoaExtractionBatch:
    artifact: BahiaStateLoaArtifact
    pages: tuple[PageInput, ...]
    amendments: tuple[AuthorizedLoaAmendment, ...]
    job_type: str
    idempotency_key: str
    extractor_version: str
    validator_version: str
    scope_rows: tuple[Loa2026ScopeRow, ...] = ()


@dataclass(frozen=True)
class BahiaStateLoaPersistResult:
    job_created: bool
    results_inserted: int
    scope_rows_inserted: int = 0


class ObjectReader(Protocol):
    def read(self, object_key: str) -> bytes: ...


class LoaExtractionRepository(Protocol):
    def persist_extraction(
        self,
        batch: BahiaStateLoaExtractionBatch,
    ) -> BahiaStateLoaPersistResult: ...


def loa_job_idempotency_key(artifact_sha256: str) -> str:
    material = ":".join(
        (
            LOA_EXTRACTION_JOB_TYPE,
            artifact_sha256,
            PDF_PARSER_VERSION,
            LOA_BARREIRAS_PARSER_VERSION,
            LOA_SCOPE_PARSER_VERSION,
            LOA_VALIDATOR_VERSION,
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def amendment_payload(
    amendment: AuthorizedLoaAmendment,
    artifact: BahiaStateLoaArtifact,
) -> dict[str, object]:
    """Serializa o fato sem converter valor monetario em ponto flutuante."""
    return {
        "schema_name": "bahia-state-loa-authorized-amendment",
        "schema_version": "1.0.0",
        "fiscal_year": amendment.fiscal_year,
        "annex_code": amendment.annex_code,
        "amendment_number": amendment.amendment_number,
        "author_name": amendment.author_name,
        "author_external_code": amendment.author_external_code,
        "agency_code": amendment.agency_code,
        "budget_unit_code": amendment.budget_unit_code,
        "action_code": amendment.action_code,
        "official_description": amendment.official_description,
        "municipality": amendment.municipality,
        "authorized_amount": format(amendment.authorized_amount, "f"),
        "financial_stage": "authorized",
        "page_number": amendment.page_number,
        "evidence_text": amendment.evidence_text,
        "evidence_sha256": amendment.evidence_sha256,
        "source_url": artifact.source_url,
        "source_artifact_sha256": artifact.sha256,
        "parser_version": amendment.parser_version,
    }


def scope_row_payload(
    row: Loa2026ScopeRow,
    artifact: BahiaStateLoaArtifact,
) -> dict[str, object]:
    """Serializa apenas a chave estrutural privada do universo estadual."""
    return {
        "schema_name": "bahia-state-loa-2026-scope-row",
        "schema_version": "1.0.0",
        "fiscal_year": row.fiscal_year,
        "annex_code": row.annex_code,
        "amendment_number": row.amendment_number,
        "author_name": row.author_name,
        "author_external_code": row.author_external_code,
        "agency_code": row.agency_code,
        "budget_unit_code": row.budget_unit_code,
        "action_code": row.action_code,
        "author_page_number": row.author_page_number,
        "author_evidence_text": row.author_evidence_text,
        "author_evidence_sha256": row.author_evidence_sha256,
        "page_number": row.page_number,
        "evidence_text": row.evidence_text,
        "evidence_sha256": row.evidence_sha256,
        "source_url": artifact.source_url,
        "source_artifact_sha256": artifact.sha256,
        "parser_version": row.parser_version,
        "visibility": "private_reconciliation_scope",
    }


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


class BahiaStateLoaExtractionService:
    """Restaura, valida e extrai somente valores autorizados para Barreiras."""

    def __init__(
        self,
        *,
        object_reader: ObjectReader,
        repository: LoaExtractionRepository,
    ) -> None:
        self.object_reader = object_reader
        self.repository = repository

    def process(
        self,
        artifact: BahiaStateLoaArtifact,
    ) -> BahiaStateLoaPersistResult:
        raw_body = self.object_reader.read(artifact.object_key)
        restored_hash = hashlib.sha256(raw_body).hexdigest()
        if restored_hash != artifact.sha256:
            raise LoaArtifactMismatchError(
                "O PDF restaurado diverge do hash registrado na coleta."
            )

        pdf = derive_pdf_text(raw_body)
        if not pdf.pages or pdf.pages_with_text != len(pdf.pages):
            raise LoaIncompleteTextError(
                "O PDF nao possui texto integral em todas as paginas."
            )
        pages = tuple(
            PageInput(
                page_number=page.page_number,
                parser_version=pdf.parser_version,
                text=page.text,
                sha256=page.sha256,
            )
            for page in pdf.pages
        )
        loa_pages = tuple(
            LoaPage(page.page_number, page.text or "") for page in pdf.pages
        )
        amendments = parse_barreiras_loa_pages(
            fiscal_year=artifact.fiscal_year,
            annex_code=artifact.annex_code,
            pages=loa_pages,
        )
        if not amendments:
            raise LoaIncompleteTextError(
                "Nenhuma linha territorial de Barreiras foi encontrada; "
                "o formato oficial pode ter mudado."
            )
        scope_rows = (
            parse_loa_2026_scope_pages(
                annex_code=artifact.annex_code,
                pages=loa_pages,
            )
            if artifact.fiscal_year == 2026
            else ()
        )

        batch = BahiaStateLoaExtractionBatch(
            artifact=artifact,
            pages=pages,
            amendments=amendments,
            job_type=LOA_EXTRACTION_JOB_TYPE,
            idempotency_key=loa_job_idempotency_key(artifact.sha256),
            extractor_version=LOA_BARREIRAS_PARSER_VERSION,
            validator_version=LOA_VALIDATOR_VERSION,
            scope_rows=scope_rows,
        )
        return self.repository.persist_extraction(batch)
