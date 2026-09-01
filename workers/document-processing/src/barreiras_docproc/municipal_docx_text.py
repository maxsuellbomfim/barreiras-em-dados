"""Deriva e persiste o texto literal dos DOCX municipais preservados.

Um DOCX não possui páginas fixas. O texto integral é registrado como uma
unidade lógica privada para busca, sem substituir o artefato oficial.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from .docx_text import DOCX_PARSER_VERSION, derive_docx_text
from .processing import (
    ArtifactMismatchError,
    ObjectReader,
    PageInput,
    TextArtifact,
)


class MunicipalDocxRepository(Protocol):
    def persist_municipal_docx_text(
        self,
        artifact: TextArtifact,
        pages: tuple[PageInput, ...],
        *,
        job_type: str,
        job_idempotency_key: str,
    ) -> bool: ...


JOB_TYPE = "municipal_docx_text"


def job_idempotency_key(artifact_sha256: str) -> str:
    material = f"{JOB_TYPE}:{artifact_sha256}:{DOCX_PARSER_VERSION}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MunicipalDocxTextResult:
    text_characters: int
    blocks_total: int
    job_created: bool


class MunicipalDocxTextService:
    """Confere o bruto antes de persistir texto derivado idempotente."""

    def __init__(
        self,
        *,
        object_reader: ObjectReader,
        repository: MunicipalDocxRepository,
    ) -> None:
        self.object_reader = object_reader
        self.repository = repository

    def process(self, artifact: TextArtifact) -> MunicipalDocxTextResult:
        raw_body = self.object_reader.read(artifact.object_key)
        restored_hash = hashlib.sha256(raw_body).hexdigest()
        if restored_hash != artifact.sha256:
            raise ArtifactMismatchError(
                "O DOCX municipal restaurado diverge do hash registrado."
            )

        derived = derive_docx_text(raw_body)
        pages = (
            PageInput(
                page_number=1,
                parser_version=derived.parser_version,
                text=derived.text,
                sha256=derived.text_sha256,
            ),
        )
        job_created = self.repository.persist_municipal_docx_text(
            artifact,
            pages,
            job_type=JOB_TYPE,
            job_idempotency_key=job_idempotency_key(artifact.sha256),
        )
        return MunicipalDocxTextResult(
            text_characters=len(derived.text),
            blocks_total=len(derived.blocks),
            job_created=job_created,
        )
