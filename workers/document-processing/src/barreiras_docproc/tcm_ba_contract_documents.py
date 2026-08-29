"""Segmentos privados de contratos e aditivos preservados pelo TCM-BA."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Protocol

from .processing import PageInput, TextArtifact

EXTRACTOR_VERSION = "tcm-ba-contract-document-segments/1.0.0"
VALIDATOR_VERSION = "deterministic-contract-heading-allowlist/1.0.0"
JOB_TYPE = "tcm_ba_contract_document_segments"


@dataclass(frozen=True)
class TcmBaContractDocumentSegment:
    ordinal: int
    document_kind: str
    classification_status: str
    start_page: int
    start_offset: int
    end_page: int
    end_offset: int
    heading_page: int | None
    heading_offset: int | None
    heading_text_sha256: str | None
    source_page_numbers: tuple[int, ...]
    source_page_sha256s: tuple[str, ...]
    segment_text_sha256: str


@dataclass(frozen=True)
class TcmBaContractDocumentBatch:
    artifact: TextArtifact
    pages: tuple[PageInput, ...]
    segments: tuple[TcmBaContractDocumentSegment, ...]
    job_type: str
    job_idempotency_key: str
    extractor_version: str


@dataclass(frozen=True)
class TcmBaContractDocumentPersistResult:
    job_created: bool
    results_inserted: int
    identified_segments: int
    unknown_segments: int


@dataclass(frozen=True)
class TcmBaContractDocumentCoverage:
    eligible_artifacts: int
    processed_artifacts: int
    identified_segments: int
    unknown_segments: int
    missing_artifacts: int
    unknown_only_artifacts: int
    duplicate_results: int
    invalid_results: int
    open_failures: int

    @property
    def complete(self) -> bool:
        return (
            self.eligible_artifacts > 0
            and self.processed_artifacts == self.eligible_artifacts
            and self.identified_segments > 0
            and self.missing_artifacts == 0
            and self.unknown_only_artifacts == 0
            and self.duplicate_results == 0
            and self.invalid_results == 0
            and self.open_failures == 0
        )


class TcmBaContractDocumentRepository(Protocol):
    def persist_contract_document_segments(
        self,
        batch: TcmBaContractDocumentBatch,
    ) -> TcmBaContractDocumentPersistResult: ...


_ORDINAL = (
    r"(?:(?:PRIMEIRO|SEGUNDO|TERCEIRO|QUARTO|QUINTO|SEXTO|S[ÉE]TIMO|"
    r"OITAVO|NONO|D[ÉE]CIMO|\d+[º°O.]?)[ \t]+)?"
)
_PREFIX = r"^[ \t]*(?:EXTRATO[ \t]+DE[ \t]+)?"
_HEADING_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "contract_amendment",
        re.compile(
            _PREFIX + _ORDINAL + r"(?:TERMO[ \t]+)?ADITIV[OA]\b",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "contract_termination",
        re.compile(
            _PREFIX + r"(?:TERMO[ \t]+DE[ \t]+)?(?:RESCIS[ÃA]O|DISTRATO)\b",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "contract_apostille",
        re.compile(
            _PREFIX + r"(?:TERMO[ \t]+DE[ \t]+)?APOSTILAMENTO\b",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "price_registry_minutes",
        re.compile(
            _PREFIX + r"ATA[ \t]+DE[ \t]+REGISTRO[ \t]+DE[ \t]+PRE[CÇ]OS\b",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "accreditation_term",
        re.compile(
            _PREFIX + r"(?:TERMO[ \t]+DE[ \t]+)?CREDENCIAMENTO\b",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "service_or_supply_order",
        re.compile(
            _PREFIX + r"ORDEM[ \t]+DE[ \t]+(?:SERVI[CÇ]O|FORNECIMENTO)\b",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "agreement",
        re.compile(
            _PREFIX + r"CONV[EÊ]NIO\b",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "use_instrument",
        re.compile(
            _PREFIX
            + r"(?:TERMO[ \t]+DE[ \t]+)?(?:CESS[AÃ]O|PERMISS[AÃ]O|COMODATO)\b",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "contract",
        re.compile(
            _PREFIX + r"CONTRATO(?:[ \t]+(?:ADMINISTRATIVO|DE))?\b",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
)


@dataclass(frozen=True)
class _Heading:
    page_index: int
    offset: int
    end: int
    document_kind: str


def _headings(pages: tuple[PageInput, ...]) -> tuple[_Heading, ...]:
    found: dict[tuple[int, int], _Heading] = {}
    for page_index, page in enumerate(pages):
        text = page.text or ""
        for document_kind, pattern in _HEADING_PATTERNS:
            for match in pattern.finditer(text):
                key = (page_index, match.start())
                found.setdefault(
                    key,
                    _Heading(page_index, match.start(), match.end(), document_kind),
                )
    return tuple(found[key] for key in sorted(found))


def _segment_hash(
    pages: tuple[PageInput, ...],
    start_index: int,
    start_offset: int,
    end_index: int,
    end_offset: int,
) -> str:
    pieces: list[str] = []
    for page_index in range(start_index, end_index + 1):
        text = pages[page_index].text or ""
        piece_start = start_offset if page_index == start_index else 0
        piece_end = end_offset if page_index == end_index else len(text)
        pieces.append(f"{pages[page_index].page_number}\n{text[piece_start:piece_end]}")
    material = "\n\f\n".join(pieces)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def segment_contract_documents(
    pages: tuple[PageInput, ...],
) -> tuple[TcmBaContractDocumentSegment, ...]:
    if not pages:
        return ()
    headings = _headings(pages)
    if not headings:
        first = pages[0]
        last = pages[-1]
        return (
            TcmBaContractDocumentSegment(
                ordinal=1,
                document_kind="unknown",
                classification_status="needs_review",
                start_page=first.page_number,
                start_offset=0,
                end_page=last.page_number,
                end_offset=len(last.text or ""),
                heading_page=None,
                heading_offset=None,
                heading_text_sha256=None,
                source_page_numbers=tuple(page.page_number for page in pages),
                source_page_sha256s=tuple(page.sha256 for page in pages),
                segment_text_sha256=_segment_hash(
                    pages, 0, 0, len(pages) - 1, len(last.text or "")
                ),
            ),
        )

    segments: list[TcmBaContractDocumentSegment] = []
    for index, heading in enumerate(headings):
        start_index = 0 if index == 0 else heading.page_index
        start_offset = 0 if index == 0 else heading.offset
        if index + 1 < len(headings):
            next_heading = headings[index + 1]
            end_index = next_heading.page_index
            end_offset = next_heading.offset
            if end_offset == 0 and end_index > start_index:
                end_index -= 1
                end_offset = len(pages[end_index].text or "")
        else:
            end_index = len(pages) - 1
            end_offset = len(pages[end_index].text or "")
        source_pages = pages[start_index : end_index + 1]
        heading_text = (pages[heading.page_index].text or "")[
            heading.offset : heading.end
        ]
        segments.append(
            TcmBaContractDocumentSegment(
                ordinal=index + 1,
                document_kind=heading.document_kind,
                classification_status="identified",
                start_page=pages[start_index].page_number,
                start_offset=start_offset,
                end_page=pages[end_index].page_number,
                end_offset=end_offset,
                heading_page=pages[heading.page_index].page_number,
                heading_offset=heading.offset,
                heading_text_sha256=hashlib.sha256(
                    heading_text.encode("utf-8")
                ).hexdigest(),
                source_page_numbers=tuple(page.page_number for page in source_pages),
                source_page_sha256s=tuple(page.sha256 for page in source_pages),
                segment_text_sha256=_segment_hash(
                    pages,
                    start_index,
                    start_offset,
                    end_index,
                    end_offset,
                ),
            )
        )
    return tuple(segments)


def contract_document_job_idempotency_key(artifact_sha256: str) -> str:
    material = f"tcm-ba-contract-segments:{artifact_sha256}:{EXTRACTOR_VERSION}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def contract_document_payload(
    segment: TcmBaContractDocumentSegment,
    artifact: TextArtifact,
) -> dict[str, object]:
    return {
        "schema_name": "tcm-ba-contract-document-segment",
        "schema_version": "1.0.0",
        "segment_ordinal": segment.ordinal,
        "document_kind": segment.document_kind,
        "classification_status": segment.classification_status,
        "classification_basis": "deterministic_heading_allowlist",
        "start_page": segment.start_page,
        "start_offset": segment.start_offset,
        "end_page": segment.end_page,
        "end_offset": segment.end_offset,
        "heading_page": segment.heading_page,
        "heading_offset": segment.heading_offset,
        "heading_text_sha256": segment.heading_text_sha256,
        "source_page_numbers": list(segment.source_page_numbers),
        "source_page_sha256s": list(segment.source_page_sha256s),
        "segment_text_sha256": segment.segment_text_sha256,
        "source_artifact_sha256": artifact.sha256,
        "extractor_version": EXTRACTOR_VERSION,
    }


class TcmBaContractDocumentExtractionService:
    def __init__(self, *, repository: TcmBaContractDocumentRepository) -> None:
        self.repository = repository

    def process(
        self,
        artifact: TextArtifact,
        pages: tuple[PageInput, ...],
    ) -> TcmBaContractDocumentPersistResult:
        return self.repository.persist_contract_document_segments(
            TcmBaContractDocumentBatch(
                artifact=artifact,
                pages=pages,
                segments=segment_contract_documents(pages),
                job_type=JOB_TYPE,
                job_idempotency_key=contract_document_job_idempotency_key(
                    artifact.sha256
                ),
                extractor_version=EXTRACTOR_VERSION,
            )
        )
