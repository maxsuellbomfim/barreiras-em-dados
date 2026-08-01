"""Orquestra a extração candidata de um artefato de texto preservado."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from .candidates import RULESET_VERSION, ActCandidate, find_candidates
from .canonical import CanonicalText, derive_canonical_text
from .fields import extract_act_fields, fields_payload
from .pdf_text import derive_pdf_text


class ProcessingError(RuntimeError):
    """Falha explícita ao processar um artefato de texto."""


class ArtifactMismatchError(ProcessingError):
    """Os bytes restaurados não correspondem ao hash registrado do artefato."""


@dataclass(frozen=True)
class TextArtifact:
    raw_artifact_id: str
    sha256: str
    object_key: str


@dataclass(frozen=True)
class PageInput:
    page_number: int
    parser_version: str
    text: str | None
    sha256: str | None


@dataclass(frozen=True)
class ExtractionBatch:
    artifact: TextArtifact
    canonical: CanonicalText
    pages: tuple[PageInput, ...]
    job_type: str
    job_idempotency_key: str
    ruleset_version: str
    candidates: tuple[ActCandidate, ...]


@dataclass(frozen=True)
class ExtractionPersistResult:
    job_created: bool
    results_inserted: int


class ObjectReader(Protocol):
    def read(self, object_key: str) -> bytes: ...


class ExtractionRepository(Protocol):
    def persist_extraction(
        self,
        batch: ExtractionBatch,
    ) -> ExtractionPersistResult: ...

    def persist_extraction_failure(
        self,
        artifact: TextArtifact,
        *,
        job_type: str,
        job_idempotency_key: str,
        error_code: str,
        error_detail: str,
    ) -> None: ...


JOB_TYPE = "gazette_act_candidates"


def job_idempotency_key(artifact_sha256: str, ruleset_version: str) -> str:
    material = f"gazette-acts:{artifact_sha256}:{ruleset_version}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def candidate_payload(
    candidate: ActCandidate,
    canonical: CanonicalText,
    artifact: TextArtifact,
) -> dict[str, object]:
    """Payload reproduzível: quem reproduzir o texto acha o mesmo trecho."""
    fields = extract_act_fields(
        canonical.text,
        match_start=candidate.match_start,
        match_end=candidate.match_end,
    )
    return {
        "schema_name": "gazette-act-candidate",
        "schema_version": "1.2.0",
        "act_type": candidate.act_type,
        "fields": fields_payload(fields),
        "rule_id": candidate.rule_id,
        "ruleset_version": candidate.ruleset_version,
        "match_start": candidate.match_start,
        "match_end": candidate.match_end,
        "match_text": candidate.match_text,
        "excerpt_start": candidate.excerpt_start,
        "excerpt_end": candidate.excerpt_end,
        "excerpt": candidate.excerpt,
        "canonical_text_sha256": canonical.sha256,
        "source_artifact_sha256": artifact.sha256,
    }


class GazetteActExtractionService:
    """Deriva texto canônico e enfileira candidatos, sem publicar nada."""

    def __init__(
        self,
        *,
        object_reader: ObjectReader,
        repository: ExtractionRepository,
    ) -> None:
        self.object_reader = object_reader
        self.repository = repository

    def process(self, artifact: TextArtifact) -> ExtractionPersistResult:
        raw_body = self.object_reader.read(artifact.object_key)
        restored_hash = hashlib.sha256(raw_body).hexdigest()
        if restored_hash != artifact.sha256:
            raise ArtifactMismatchError(
                "O texto restaurado diverge do hash registrado do artefato."
            )

        if artifact.object_key.endswith(".pdf"):
            pdf = derive_pdf_text(raw_body)
            canonical = CanonicalText(
                text=pdf.text,
                sha256=pdf.sha256,
                parser_version=pdf.parser_version,
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
        else:
            canonical = derive_canonical_text(raw_body)
            pages = (
                PageInput(
                    page_number=1,
                    parser_version=canonical.parser_version,
                    text=canonical.text,
                    sha256=canonical.sha256,
                ),
            )

        candidates = find_candidates(canonical.text)
        batch = ExtractionBatch(
            artifact=artifact,
            canonical=canonical,
            pages=pages,
            job_type=JOB_TYPE,
            job_idempotency_key=job_idempotency_key(
                artifact.sha256,
                RULESET_VERSION,
            ),
            ruleset_version=RULESET_VERSION,
            candidates=candidates,
        )
        return self.repository.persist_extraction(batch)


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
