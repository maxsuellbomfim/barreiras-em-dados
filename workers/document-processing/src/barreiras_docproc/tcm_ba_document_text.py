"""Deriva páginas canônicas dos PDFs mensais preservados do TCM-BA.

Esta etapa não classifica documentos nem publica valores. Ela apenas confere os
bytes contra o SHA-256 registrado e persiste o texto embutido página a página;
página sem texto permanece nula para o corredor de OCR.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from .pdf_text import PDF_PARSER_VERSION, derive_pdf_text
from .processing import ArtifactMismatchError, ObjectReader, PageInput, TextArtifact


class PageRepository(Protocol):
    def persist_tcm_document_text(
        self,
        artifact: TextArtifact,
        pages: tuple[PageInput, ...],
        *,
        job_type: str,
        job_idempotency_key: str,
    ) -> bool: ...


JOB_TYPE = "tcm_ba_document_text"


def job_idempotency_key(artifact_sha256: str) -> str:
    material = f"{JOB_TYPE}:{artifact_sha256}:{PDF_PARSER_VERSION}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TcmBaDocumentTextResult:
    pages_total: int
    pages_with_embedded_text: int
    pages_awaiting_ocr: int
    job_created: bool


class TcmBaDocumentTextService:
    """Valida o PDF e persiste páginas idempotentes, sem inferência."""

    def __init__(
        self,
        *,
        object_reader: ObjectReader,
        repository: PageRepository,
    ) -> None:
        self.object_reader = object_reader
        self.repository = repository

    def process(self, artifact: TextArtifact) -> TcmBaDocumentTextResult:
        raw_body = self.object_reader.read(artifact.object_key)
        restored_hash = hashlib.sha256(raw_body).hexdigest()
        if restored_hash != artifact.sha256:
            raise ArtifactMismatchError(
                "O PDF TCM-BA restaurado diverge do hash registrado."
            )

        pdf = derive_pdf_text(raw_body)
        pages = tuple(
            PageInput(
                page_number=page.page_number,
                parser_version=pdf.parser_version,
                text=page.text,
                sha256=page.sha256,
            )
            for page in pdf.pages
        )
        job_created = self.repository.persist_tcm_document_text(
            artifact,
            pages,
            job_type=JOB_TYPE,
            job_idempotency_key=job_idempotency_key(artifact.sha256),
        )
        pages_total = len(pages)
        return TcmBaDocumentTextResult(
            pages_total=pages_total,
            pages_with_embedded_text=pdf.pages_with_text,
            pages_awaiting_ocr=pages_total - pdf.pages_with_text,
            job_created=job_created,
        )
