"""Campos privados e conservadores de segmentos contratuais do TCM-BA."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .processing import PageInput, TextArtifact
from .tcm_ba_contract_documents import (
    EXTRACTOR_VERSION as SEGMENT_EXTRACTOR_VERSION,
)
from .tcm_ba_contract_documents import (
    TcmBaContractDocumentSegment,
)

EXTRACTOR_VERSION = "tcm-ba-contract-field-candidates/1.1.1"
VALIDATOR_VERSION = "private-source-anchor-review/1.0.0"
JOB_TYPE = "tcm_ba_contract_field_candidates"


@dataclass(frozen=True)
class TcmBaContractFieldAnchor:
    page_number: int
    start_offset: int
    end_offset: int
    page_sha256: str
    evidence_sha256: str


@dataclass(frozen=True)
class TcmBaContractFieldCandidate:
    source_segment_ordinal: int
    source_segment_text_sha256: str
    document_kind: str
    instrument_number: str | None
    related_contract_number: str | None
    administrative_process_number: str | None
    contracted_party_name: str | None
    contracted_party_cnpj: str | None
    object_text: str | None
    amount_text: str | None
    signature_date: str | None
    validity_text: str | None
    unobserved_fields: tuple[str, ...]
    source_anchors: dict[str, TcmBaContractFieldAnchor]

    @property
    def candidate_status(self) -> str:
        return "fields_observed" if self.source_anchors else "no_fields_observed"


@dataclass(frozen=True)
class TcmBaContractFieldBatch:
    artifact: TextArtifact
    pages: tuple[PageInput, ...]
    segments: tuple[TcmBaContractDocumentSegment, ...]
    candidates: tuple[TcmBaContractFieldCandidate, ...]
    job_type: str
    job_idempotency_key: str
    extractor_version: str


@dataclass(frozen=True)
class TcmBaContractFieldPersistResult:
    job_created: bool
    results_inserted: int
    fields_observed: int
    empty_candidates: int


@dataclass(frozen=True)
class TcmBaContractFieldCoverage:
    eligible_artifacts: int
    processed_artifacts: int
    eligible_segments: int
    processed_segments: int
    observed_fields: int
    no_fields_observed: int
    missing_segments: int
    duplicate_results: int
    invalid_results: int
    open_failures: int

    @property
    def complete(self) -> bool:
        return (
            self.eligible_artifacts > 0
            and self.processed_artifacts == self.eligible_artifacts
            and self.eligible_segments > 0
            and self.processed_segments == self.eligible_segments
            and self.observed_fields > 0
            and self.missing_segments == 0
            and self.duplicate_results == 0
            and self.invalid_results == 0
            and self.open_failures == 0
        )


class TcmBaContractFieldRepository(Protocol):
    def persist_contract_field_candidates(
        self,
        batch: TcmBaContractFieldBatch,
    ) -> TcmBaContractFieldPersistResult: ...


@dataclass(frozen=True)
class _PageSlice:
    page: PageInput
    text: str
    source_offset: int


@dataclass(frozen=True)
class _ObservedValue:
    value: str
    anchor: TcmBaContractFieldAnchor


_NUMBER = r"(?P<value>[A-Z0-9][A-Z0-9./-]{0,39})"
_VALUE_SEPARATOR = r"(?:[ \t]*[:.-][ \t]*|[ \t]+)"
_AMENDMENT_NUMBER = re.compile(
    r"(?:TERMO\s+)?ADITIV[OA]\s+N\s*[º°O.]?\s*" + _NUMBER,
    re.IGNORECASE,
)
_RELATED_CONTRACT_NUMBER = re.compile(
    r"\b(?:AO|DO|REFERENTE\s+AO)\s+CONTRATO(?:\s+ADMINISTRATIVO)?\s+"
    r"N\s*[º°O.]?\s*" + _NUMBER,
    re.IGNORECASE,
)
_INSTRUMENT_PATTERNS: dict[str, re.Pattern[str]] = {
    "contract": re.compile(
        r"\bCONTRATO(?:\s+ADMINISTRATIVO)?\s+N\s*[º°O.]?\s*" + _NUMBER,
        re.IGNORECASE,
    ),
    "contract_termination": re.compile(
        r"\b(?:RESCIS[ÃA]O|DISTRATO)\s+N\s*[º°O.]?\s*" + _NUMBER,
        re.IGNORECASE,
    ),
    "contract_apostille": re.compile(
        r"\bAPOSTILAMENTO\s+N\s*[º°O.]?\s*" + _NUMBER,
        re.IGNORECASE,
    ),
    "price_registry_minutes": re.compile(
        r"\bATA\s+DE\s+REGISTRO\s+DE\s+PRE[CÇ]OS\s+"
        r"N\s*[º°O.]?\s*" + _NUMBER,
        re.IGNORECASE,
    ),
    "accreditation_term": re.compile(
        r"\bCREDENCIAMENTO\s+N\s*[º°O.]?\s*" + _NUMBER,
        re.IGNORECASE,
    ),
    "service_or_supply_order": re.compile(
        r"\bORDEM\s+DE\s+(?:SERVI[CÇ]O|FORNECIMENTO)\s+"
        r"N\s*[º°O.]?\s*" + _NUMBER,
        re.IGNORECASE,
    ),
    "agreement": re.compile(
        r"\bCONV[EÊ]NIO\s+N\s*[º°O.]?\s*" + _NUMBER,
        re.IGNORECASE,
    ),
    "use_instrument": re.compile(
        r"\b(?:CESS[AÃ]O|PERMISS[AÃ]O|COMODATO)\s+"
        r"N\s*[º°O.]?\s*" + _NUMBER,
        re.IGNORECASE,
    ),
}
_ADMINISTRATIVE_PROCESS = re.compile(
    r"^[ \t]*PROCESSO(?:\s+ADMINISTRATIVO)?\s+"
    r"N\s*[º°O.]?\s*" + _NUMBER,
    re.IGNORECASE | re.MULTILINE,
)
_PARTY = re.compile(
    r"^[ \t]*(?:CONTRATAD[OA]|CREDENCIAD[OA]|FORNECEDOR(?:A)?)"
    + _VALUE_SEPARATOR
    + r"(?P<value>[^\n]+)",
    re.IGNORECASE | re.MULTILINE,
)
_OBJECT = re.compile(
    r"^[ \t]*(?:DO\s+)?OBJETO" + _VALUE_SEPARATOR + r"(?P<value>[^\n]+)",
    re.IGNORECASE | re.MULTILINE,
)
_AMOUNT = re.compile(
    r"^[ \t]*(?:VALOR(?:\s+(?:GLOBAL|TOTAL|ESTIMADO|MENSAL|DO\s+CONTRATO))?)"
    + _VALUE_SEPARATOR
    + r"(?:R\$\s*)?(?P<value>-?[\d.]+,\d{2})",
    re.IGNORECASE | re.MULTILINE,
)
_SIGNATURE_DATE = re.compile(
    r"^[ \t]*(?:DATA\s+(?:DA|DE)\s+ASSINATURA|"
    r"ASSINATURA(?:\s+DO\s+CONTRATO)?)"
    + _VALUE_SEPARATOR
    + r"(?P<value>\d{1,2}/\d{1,2}/\d{4})",
    re.IGNORECASE | re.MULTILINE,
)
_VALIDITY = re.compile(
    r"^[ \t]*(?:VIG[EÊ]NCIA|PRAZO(?:\s+DE\s+VIG[EÊ]NCIA)?)"
    + _VALUE_SEPARATOR
    + r"(?P<value>[^\n]+)",
    re.IGNORECASE | re.MULTILINE,
)
_DOCUMENT_SUFFIX = re.compile(
    r"\s*(?:[-|]\s*)?(?:CPF|CNPJ|C\.?P\.?F\.?|C\.?N\.?P\.?J\.?)"
    r"\b.*$",
    re.IGNORECASE,
)
_CPF = re.compile(r"(?<!\d)\d{3}[.\s]?\d{3}[.\s]?\d{3}[-\s]?\d{2}(?!\d)")
_CNPJ = re.compile(
    r"(?<!\d)(\d{2})\.?([\d]{3})\.?([\d]{3})/?([\d]{4})-?([\d]{2})(?!\d)"
)
_FIELDS = (
    "instrument_number",
    "related_contract_number",
    "administrative_process_number",
    "contracted_party_name",
    "contracted_party_cnpj",
    "object_text",
    "amount_text",
    "signature_date",
    "validity_text",
)


def _page_slices(
    pages: tuple[PageInput, ...],
    segment: TcmBaContractDocumentSegment,
) -> tuple[_PageSlice, ...]:
    selected: list[_PageSlice] = []
    for page in pages:
        if not segment.start_page <= page.page_number <= segment.end_page:
            continue
        source = page.text or ""
        start = segment.start_offset if page.page_number == segment.start_page else 0
        end = (
            segment.end_offset if page.page_number == segment.end_page else len(source)
        )
        if end < start or start < 0 or end > len(source):
            raise ValueError("Os limites do segmento contratual são inválidos.")
        selected.append(
            _PageSlice(page=page, text=source[start:end], source_offset=start)
        )
    if not selected:
        raise ValueError("O segmento contratual não possui páginas de origem.")
    return tuple(selected)


def _observe(
    pattern: re.Pattern[str] | None,
    slices: tuple[_PageSlice, ...],
) -> _ObservedValue | None:
    if pattern is None:
        return None
    for page_slice in slices:
        match = pattern.search(page_slice.text)
        if match is None:
            continue
        raw_value = match.group("value")
        value = " ".join(raw_value.split()).strip(" \t-|;")
        if not value:
            continue
        start = page_slice.source_offset + match.start("value")
        end = page_slice.source_offset + match.end("value")
        return _ObservedValue(
            value=value,
            anchor=TcmBaContractFieldAnchor(
                page_number=page_slice.page.page_number,
                start_offset=start,
                end_offset=end,
                page_sha256=page_slice.page.sha256,
                evidence_sha256=hashlib.sha256(raw_value.encode("utf-8")).hexdigest(),
            ),
        )
    return None


def _party_name(value: str | None) -> str | None:
    if value is None:
        return None
    name = _DOCUMENT_SUFFIX.sub("", value)
    name = _CPF.sub("", name).strip(" \t-|")
    return name or None


def _redacted_personal_text(value: str | None) -> str | None:
    if value is None:
        return None
    redacted = _CPF.sub("***.***.***-**", value).strip()
    return redacted or None


def _party_cnpj(value: str | None) -> str | None:
    if value is None:
        return None
    match = _CNPJ.search(value)
    return "".join(match.groups()) if match is not None else None


def _iso_date(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def _candidate(
    pages: tuple[PageInput, ...],
    segment: TcmBaContractDocumentSegment,
) -> TcmBaContractFieldCandidate:
    slices = _page_slices(pages, segment)
    instrument_pattern = (
        _AMENDMENT_NUMBER
        if segment.document_kind == "contract_amendment"
        else _INSTRUMENT_PATTERNS.get(segment.document_kind)
    )
    observed = {
        "instrument_number": _observe(instrument_pattern, slices),
        "related_contract_number": _observe(
            _RELATED_CONTRACT_NUMBER
            if segment.document_kind == "contract_amendment"
            else None,
            slices,
        ),
        "administrative_process_number": _observe(
            _ADMINISTRATIVE_PROCESS,
            slices,
        ),
        "contracted_party": _observe(_PARTY, slices),
        "object_text": _observe(_OBJECT, slices),
        "amount_text": _observe(_AMOUNT, slices),
        "signature_date": _observe(_SIGNATURE_DATE, slices),
        "validity_text": _observe(_VALIDITY, slices),
    }
    party = observed["contracted_party"]
    anchors: dict[str, TcmBaContractFieldAnchor] = {}
    for field in (
        "instrument_number",
        "related_contract_number",
        "administrative_process_number",
        "object_text",
        "amount_text",
        "signature_date",
        "validity_text",
    ):
        item = observed[field]
        if item is not None:
            anchors[field] = item.anchor
    if party is not None:
        if _party_name(party.value) is not None:
            anchors["contracted_party_name"] = party.anchor
        if _party_cnpj(party.value) is not None:
            anchors["contracted_party_cnpj"] = party.anchor

    values: dict[str, str | None] = {
        "instrument_number": (
            observed["instrument_number"].value
            if observed["instrument_number"] is not None
            else None
        ),
        "related_contract_number": (
            observed["related_contract_number"].value
            if observed["related_contract_number"] is not None
            else None
        ),
        "administrative_process_number": (
            observed["administrative_process_number"].value
            if observed["administrative_process_number"] is not None
            else None
        ),
        "contracted_party_name": _party_name(party.value if party else None),
        "contracted_party_cnpj": _party_cnpj(party.value if party else None),
        "object_text": _redacted_personal_text(
            observed["object_text"].value
            if observed["object_text"] is not None
            else None
        ),
        "amount_text": (
            observed["amount_text"].value
            if observed["amount_text"] is not None
            else None
        ),
        "signature_date": _iso_date(
            observed["signature_date"].value
            if observed["signature_date"] is not None
            else None
        ),
        "validity_text": _redacted_personal_text(
            observed["validity_text"].value
            if observed["validity_text"] is not None
            else None
        ),
    }
    if values["signature_date"] is None:
        anchors.pop("signature_date", None)
    applicable_fields = tuple(
        field
        for field in _FIELDS
        if field != "related_contract_number"
        or segment.document_kind == "contract_amendment"
    )
    return TcmBaContractFieldCandidate(
        source_segment_ordinal=segment.ordinal,
        source_segment_text_sha256=segment.segment_text_sha256,
        document_kind=segment.document_kind,
        instrument_number=values["instrument_number"],
        related_contract_number=values["related_contract_number"],
        administrative_process_number=values["administrative_process_number"],
        contracted_party_name=values["contracted_party_name"],
        contracted_party_cnpj=values["contracted_party_cnpj"],
        object_text=values["object_text"],
        amount_text=values["amount_text"],
        signature_date=values["signature_date"],
        validity_text=values["validity_text"],
        unobserved_fields=tuple(
            field for field in applicable_fields if values[field] is None
        ),
        source_anchors=anchors,
    )


def extract_contract_field_candidates(
    pages: tuple[PageInput, ...],
    segments: tuple[TcmBaContractDocumentSegment, ...],
) -> tuple[TcmBaContractFieldCandidate, ...]:
    return tuple(_candidate(pages, segment) for segment in segments)


def contract_field_job_idempotency_key(artifact_sha256: str) -> str:
    material = (
        f"tcm-ba-contract-fields:{artifact_sha256}:"
        f"{SEGMENT_EXTRACTOR_VERSION}:{EXTRACTOR_VERSION}"
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _anchor_payload(anchor: TcmBaContractFieldAnchor) -> dict[str, object]:
    return {
        "page_number": anchor.page_number,
        "start_offset": anchor.start_offset,
        "end_offset": anchor.end_offset,
        "page_sha256": anchor.page_sha256,
        "evidence_sha256": anchor.evidence_sha256,
    }


def contract_field_candidate_payload(
    candidate: TcmBaContractFieldCandidate,
    artifact: TextArtifact,
) -> dict[str, object]:
    return {
        "schema_name": "tcm-ba-contract-field-candidate",
        "schema_version": "1.0.0",
        "candidate_status": candidate.candidate_status,
        "source_segment_ordinal": candidate.source_segment_ordinal,
        "source_segment_text_sha256": candidate.source_segment_text_sha256,
        "document_kind": candidate.document_kind,
        "instrument_number": candidate.instrument_number,
        "related_contract_number": candidate.related_contract_number,
        "administrative_process_number": candidate.administrative_process_number,
        "contracted_party_name": candidate.contracted_party_name,
        "contracted_party_cnpj": candidate.contracted_party_cnpj,
        "object_text": candidate.object_text,
        "amount_text": candidate.amount_text,
        "signature_date": candidate.signature_date,
        "validity_text": candidate.validity_text,
        "unobserved_fields": list(candidate.unobserved_fields),
        "source_anchors": {
            field: _anchor_payload(anchor)
            for field, anchor in sorted(candidate.source_anchors.items())
        },
        "source_artifact_sha256": artifact.sha256,
        "source_segment_extractor_version": SEGMENT_EXTRACTOR_VERSION,
        "extractor_version": EXTRACTOR_VERSION,
    }


class TcmBaContractFieldExtractionService:
    def __init__(self, *, repository: TcmBaContractFieldRepository) -> None:
        self.repository = repository

    def process(
        self,
        artifact: TextArtifact,
        pages: tuple[PageInput, ...],
        segments: tuple[TcmBaContractDocumentSegment, ...],
    ) -> TcmBaContractFieldPersistResult:
        candidates = extract_contract_field_candidates(pages, segments)
        return self.repository.persist_contract_field_candidates(
            TcmBaContractFieldBatch(
                artifact=artifact,
                pages=pages,
                segments=segments,
                candidates=candidates,
                job_type=JOB_TYPE,
                job_idempotency_key=contract_field_job_idempotency_key(artifact.sha256),
                extractor_version=EXTRACTOR_VERSION,
            )
        )
