"""Candidatos conservadores de notas de empenho preservadas do TCM-BA."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol

from .pdf_layout import PDF_LAYOUT_VERSION, PdfLayoutPage, derive_pdf_layout
from .processing import (
    ArtifactMismatchError,
    ObjectReader,
    PageInput,
    TextArtifact,
)
from .tcm_ba_commitment_layout import (
    SpatialBudgetMatch,
    SpatialScalarMatch,
    diagnose_spatial_creditor,
    find_inline_explicit_issue_date,
    find_spatial_amount_text,
    find_spatial_budget_allocation,
    find_spatial_issue_date,
)

EXTRACTOR_VERSION = "tcm-ba-commitment-candidates/1.8.0"
SCHEMA_VERSION = "1.5.0"
JOB_TYPE = "tcm_ba_commitment_candidates"


@dataclass(frozen=True)
class TcmBaCommitmentCandidate:
    page_number: int
    commitment_number: str
    issue_date: str | None
    creditor_name: str | None
    amount_text: str | None
    budget_allocation: str | None
    missing_fields: tuple[str, ...]
    evidence_excerpt: str
    creditor_cnpj: str | None = None
    budget_allocation_evidence: SpatialBudgetMatch | None = None
    issue_date_evidence: SpatialScalarMatch | None = None
    amount_text_evidence: SpatialScalarMatch | None = None
    creditor_name_evidence: SpatialScalarMatch | None = None

    @property
    def complete(self) -> bool:
        return not self.missing_fields


@dataclass(frozen=True)
class TcmBaCommitmentBatch:
    artifact: TextArtifact
    pages: tuple[PageInput, ...]
    job_type: str
    job_idempotency_key: str
    extractor_version: str
    candidates: tuple[TcmBaCommitmentCandidate, ...]


@dataclass(frozen=True)
class TcmBaCommitmentPersistResult:
    job_created: bool
    results_inserted: int


@dataclass(frozen=True)
class TcmBaCommitmentCoverage:
    eligible_artifacts: int
    processed_artifacts: int
    candidate_results: int
    complete_candidates: int
    incomplete_candidates: int
    zero_candidate_artifacts: int
    missing_artifacts: int
    duplicate_results: int
    invalid_results: int
    open_failures: int

    @property
    def complete(self) -> bool:
        return (
            self.eligible_artifacts > 0
            and self.processed_artifacts == self.eligible_artifacts
            and self.candidate_results
            == self.complete_candidates + self.incomplete_candidates
            and 0 <= self.zero_candidate_artifacts <= self.processed_artifacts
            and self.missing_artifacts == 0
            and self.duplicate_results == 0
            and self.invalid_results == 0
            and self.open_failures == 0
        )


@dataclass(frozen=True)
class TcmBaCommitmentMissingFieldGroup:
    missing_fields: tuple[str, ...]
    candidates: int


@dataclass(frozen=True)
class TcmBaCommitmentFieldBreakdown:
    total_candidates: int
    complete_candidates: int
    spatial_budget_allocations: int
    spatial_issue_dates: int
    spatial_amounts: int
    spatial_creditor_names: int
    invalid_spatial_evidence: int
    missing_issue_date: int
    missing_creditor_name: int
    missing_amount_text: int
    missing_budget_allocation: int
    groups: tuple[TcmBaCommitmentMissingFieldGroup, ...]


class TcmBaCommitmentRepository(Protocol):
    def persist_tcm_ba_commitment_candidates(
        self,
        batch: TcmBaCommitmentBatch,
    ) -> TcmBaCommitmentPersistResult: ...


def commitment_job_idempotency_key(artifact_sha256: str) -> str:
    material = f"tcm-ba-commitments:{artifact_sha256}:{EXTRACTOR_VERSION}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def commitment_candidate_payload(
    candidate: TcmBaCommitmentCandidate,
    artifact: TextArtifact,
) -> dict[str, object]:
    spatial = candidate.budget_allocation_evidence

    def spatial_payload(
        match: SpatialScalarMatch | None,
        *,
        include_occurrence_count: bool = False,
    ) -> dict[str, object] | None:
        if match is None:
            return None
        payload: dict[str, object] = {
            "parser_version": PDF_LAYOUT_VERSION,
            "page_number": match.page_number,
            "label_block_order": match.label_block_order,
            "value_block_order": match.value_block_order,
            "relation": match.relation,
        }
        if include_occurrence_count:
            payload["occurrence_count"] = match.occurrence_count
        return payload

    return {
        "schema_name": "tcm-ba-commitment-candidate",
        "schema_version": SCHEMA_VERSION,
        "candidate_status": "complete" if candidate.complete else "incomplete",
        "commitment_number": candidate.commitment_number,
        "issue_date": candidate.issue_date,
        "issue_date_evidence": spatial_payload(
            candidate.issue_date_evidence,
            include_occurrence_count=True,
        ),
        "creditor_name": candidate.creditor_name,
        "creditor_name_evidence": spatial_payload(candidate.creditor_name_evidence),
        "creditor_cnpj": candidate.creditor_cnpj,
        "amount_text": candidate.amount_text,
        "amount_text_evidence": spatial_payload(candidate.amount_text_evidence),
        "budget_allocation": candidate.budget_allocation,
        "budget_allocation_evidence": (
            None
            if spatial is None
            else {
                "parser_version": PDF_LAYOUT_VERSION,
                "page_number": spatial.page_number,
                "label_block_order": spatial.label_block_order,
                "value_block_order": spatial.value_block_order,
                "relation": spatial.relation,
            }
        ),
        "missing_fields": list(candidate.missing_fields),
        "source_page_number": candidate.page_number,
        "evidence_excerpt": candidate.evidence_excerpt,
        "source_artifact_sha256": artifact.sha256,
        "extractor_version": EXTRACTOR_VERSION,
    }


def apply_spatial_budget_allocations(
    candidates: tuple[TcmBaCommitmentCandidate, ...],
    layout_pages: tuple[PdfLayoutPage, ...],
) -> tuple[TcmBaCommitmentCandidate, ...]:
    """Preenche somente uma nota incompleta em página espacial inequívoca."""
    candidates_per_page: dict[int, int] = {}
    for candidate in candidates:
        candidates_per_page[candidate.page_number] = (
            candidates_per_page.get(candidate.page_number, 0) + 1
        )
    layouts = {page.page_number: page for page in layout_pages}
    enriched: list[TcmBaCommitmentCandidate] = []
    for candidate in candidates:
        layout = layouts.get(candidate.page_number)
        if (
            candidate.budget_allocation is not None
            or candidates_per_page[candidate.page_number] != 1
            or layout is None
            or layout.extraction_method != "embedded_layout"
        ):
            enriched.append(candidate)
            continue
        match = find_spatial_budget_allocation(layout.blocks)
        if match is None:
            enriched.append(candidate)
            continue
        enriched.append(
            replace(
                candidate,
                budget_allocation=match.value,
                missing_fields=tuple(
                    field
                    for field in candidate.missing_fields
                    if field != "budget_allocation"
                ),
                budget_allocation_evidence=match,
            )
        )
    return tuple(enriched)


def apply_spatial_scalar_fields(
    candidates: tuple[TcmBaCommitmentCandidate, ...],
    layout_pages: tuple[PdfLayoutPage, ...],
) -> tuple[TcmBaCommitmentCandidate, ...]:
    """Preenche data e valor somente para uma nota inequívoca por página."""
    candidates_per_page: dict[int, int] = {}
    for candidate in candidates:
        candidates_per_page[candidate.page_number] = (
            candidates_per_page.get(candidate.page_number, 0) + 1
        )
    layouts = {page.page_number: page for page in layout_pages}
    enriched: list[TcmBaCommitmentCandidate] = []
    for candidate in candidates:
        layout = layouts.get(candidate.page_number)
        if (
            candidates_per_page[candidate.page_number] != 1
            or layout is None
            or layout.extraction_method != "embedded_layout"
        ):
            enriched.append(candidate)
            continue
        issue_match = (
            None
            if candidate.issue_date is not None
            else (
                find_spatial_issue_date(layout.blocks)
                or find_inline_explicit_issue_date(layout.blocks)
            )
        )
        amount_match = (
            None
            if candidate.amount_text is not None
            else find_spatial_amount_text(layout.blocks)
        )
        replacements: dict[str, object] = {}
        resolved_fields: set[str] = set()
        if issue_match is not None:
            replacements["issue_date"] = issue_match.value
            replacements["issue_date_evidence"] = issue_match
            resolved_fields.add("issue_date")
        if amount_match is not None:
            replacements["amount_text"] = amount_match.value
            replacements["amount_text_evidence"] = amount_match
            resolved_fields.add("amount_text")
        if not replacements:
            enriched.append(candidate)
            continue
        replacements["missing_fields"] = tuple(
            field for field in candidate.missing_fields if field not in resolved_fields
        )
        enriched.append(replace(candidate, **replacements))
    return tuple(enriched)


def apply_spatial_creditor_names(
    candidates: tuple[TcmBaCommitmentCandidate, ...],
    layout_pages: tuple[PdfLayoutPage, ...],
) -> tuple[TcmBaCommitmentCandidate, ...]:
    """Preenche credor somente para uma nota e um vencedor inequívocos."""
    candidates_per_page: dict[int, int] = {}
    for candidate in candidates:
        candidates_per_page[candidate.page_number] = (
            candidates_per_page.get(candidate.page_number, 0) + 1
        )
    layouts = {page.page_number: page for page in layout_pages}
    enriched: list[TcmBaCommitmentCandidate] = []
    for candidate in candidates:
        layout = layouts.get(candidate.page_number)
        if (
            candidate.creditor_name is not None
            or candidates_per_page[candidate.page_number] != 1
            or layout is None
            or layout.extraction_method != "embedded_layout"
        ):
            enriched.append(candidate)
            continue
        diagnosis = diagnose_spatial_creditor(layout.blocks)
        if diagnosis.status != "matched" or diagnosis.match is None:
            enriched.append(candidate)
            continue
        enriched.append(
            replace(
                candidate,
                creditor_name=diagnosis.match.value,
                creditor_name_evidence=diagnosis.match,
                missing_fields=tuple(
                    field
                    for field in candidate.missing_fields
                    if field != "creditor_name"
                ),
            )
        )
    return tuple(enriched)


class TcmBaCommitmentExtractionService:
    def __init__(
        self,
        *,
        repository: TcmBaCommitmentRepository,
        object_reader: ObjectReader | None = None,
    ) -> None:
        self.repository = repository
        self.object_reader = object_reader

    def process(
        self,
        artifact: TextArtifact,
        pages: tuple[PageInput, ...],
    ) -> TcmBaCommitmentPersistResult:
        candidates = find_commitment_candidates(pages)
        requires_layout = any(
            candidate.budget_allocation is None
            or candidate.issue_date is None
            or candidate.amount_text is None
            or candidate.creditor_name is None
            for candidate in candidates
        )
        if requires_layout:
            if self.object_reader is None:
                raise RuntimeError(
                    "A extração espacial requer leitor privado do artefato."
                )
            raw_body = self.object_reader.read(artifact.object_key)
            if hashlib.sha256(raw_body).hexdigest() != artifact.sha256:
                raise ArtifactMismatchError(
                    "O PDF restaurado diverge do hash registrado do artefato."
                )
            layout_pages = derive_pdf_layout(raw_body)
            candidates = apply_spatial_budget_allocations(
                candidates,
                layout_pages,
            )
            candidates = apply_spatial_scalar_fields(
                candidates,
                layout_pages,
            )
            candidates = apply_spatial_creditor_names(
                candidates,
                layout_pages,
            )
        batch = TcmBaCommitmentBatch(
            artifact=artifact,
            pages=pages,
            job_type=JOB_TYPE,
            job_idempotency_key=commitment_job_idempotency_key(artifact.sha256),
            extractor_version=EXTRACTOR_VERSION,
            candidates=candidates,
        )
        return self.repository.persist_tcm_ba_commitment_candidates(batch)


_HEADING = re.compile(
    r"^[ \t]*NOTA\s+DE\s+EMPENHO\s+"
    r"(?:N\s*[º°O.]?\s*)?"
    r"(?P<number>\d[\d./-]{0,29})[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_DOCUMENT_MARKER = re.compile(
    r"\bNOTA\s+DE\s+EMPENHO\b",
    re.IGNORECASE,
)
_LABELED_COMMITMENT_NUMBER = re.compile(
    r"^[ \t]*(?:N\s*[º°O.]?\s*(?:DO\s+)?EMPENHO|EMPENHO)"
    r"\s*[:;.-]\s*(?P<number>\d(?:[\d./ -]{0,28}\d)?)",
    re.IGNORECASE | re.MULTILINE,
)
_ISSUE_DATE = re.compile(
    r"^[ \t]*(?:DATA[ \t]+(?:DE[ \t]+)?EMISSÃO|EMISSÃO|EMISSAO|"
    r"DATA[ \t]+DO[ \t]+EMP[EA]NHO)[ \t]*[:;.-][ \t]*"
    r"(?P<value>\d{1,2}/\d{1,2}/\d{4})[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_ISSUE_DATE_LABEL = re.compile(
    r"^[ \t]*(?:DATA[ \t]+(?:DE[ \t]+)?EMISSÃO|EMISSÃO|EMISSAO|"
    r"DATA[ \t]+DO[ \t]+EMP[EA]NHO)[ \t]*[:;.-]?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_CREDITOR = re.compile(
    r"^[ \t]*(?:CREDOR|FAVORECIDO|BENEFICIÁRIO|BENEFICIARIO|"
    r"(?:R\.?[ \t]*)?S[O0][A-Z]{2,6}[ \t]*/[ \t]*NOME)"
    r"[ \t]*[:;.-][ \t]*(?P<value>[^\n]+)$",
    re.IGNORECASE | re.MULTILINE,
)
_CREDITOR_LABEL = re.compile(
    r"^[ \t]*(?:CREDOR|FAVORECIDO|BENEFICIÁRIO|BENEFICIARIO|"
    r"(?:R\.?[ \t]*)?S[O0][A-Z]{2,6}[ \t]*/[ \t]*NOME)"
    r"[ \t]*[:;.-]?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_AMOUNT = re.compile(
    r"^[ \t]*VALOR(?:[ \t]+(?:BRUTO|DO[ \t]+EMPENHO))?"
    r"[ \t]*[:;.-][ \t]*(?:R\$[ \t]*)?"
    r"(?P<value>-?[\d.]+,\d{2})[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_AMOUNT_LABEL = re.compile(
    r"^[ \t]*VALOR(?:[ \t]+(?:BRUTO|DO[ \t]+EMPENHO))?"
    r"[ \t]*[:;.-]?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_AMOUNT_VALUE = re.compile(r"^(?:R\$[ \t]*)?-?[\d.]+,\d{2}$", re.IGNORECASE)
_BUDGET_ALLOCATION = re.compile(
    r"^[ \t]*(?:DOTAÇÃO(?:[ \t]+ORÇAMENTÁRIA)?|DOTACAO"
    r"(?:[ \t]+ORCAMENTARIA)?|CLASSIFICAÇÃO[ \t]+ORÇAMENTÁRIA|"
    r"CLASSIFICACAO[ \t]+ORCAMENTARIA)[ \t]*[:;.-][ \t]*"
    r"(?P<value>[^\n]+)$",
    re.IGNORECASE | re.MULTILINE,
)
_BUDGET_ALLOCATION_LABEL = re.compile(
    r"^[ \t]*(?:DOTAÇÃO(?:[ \t]+ORÇAMENTÁRIA)?|DOTACAO"
    r"(?:[ \t]+ORCAMENTARIA)?|CLASSIFICAÇÃO[ \t]+ORÇAMENTÁRIA|"
    r"CLASSIFICACAO[ \t]+ORCAMENTARIA)[ \t]*[:;.-]?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_FIELD_LABELS = (
    _ISSUE_DATE_LABEL,
    _CREDITOR_LABEL,
    _AMOUNT_LABEL,
    _BUDGET_ALLOCATION_LABEL,
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
_MAX_EVIDENCE_CHARS = 2000


def _match_value(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    if match is None:
        return None
    value = match.group("value").strip()
    return value or None


def _iso_date(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def _creditor_name(value: str | None) -> str | None:
    if value is None:
        return None
    name = _DOCUMENT_SUFFIX.sub("", value).strip(" -|\t")
    return name or None


def _creditor_cnpj(value: str | None) -> str | None:
    if value is None:
        return None
    match = _CNPJ.search(value)
    return "".join(match.groups()) if match is not None else None


def _canonical_commitment_number(value: str) -> str:
    compact = re.sub(r"\s*([./-])\s*", r"\1", value.strip())
    return compact.strip(" ./-")


def _is_field_label(value: str) -> bool:
    return any(pattern.fullmatch(value) is not None for pattern in _FIELD_LABELS)


def _valid_date_value(value: str) -> bool:
    return _iso_date(value) is not None


def _valid_creditor_value(value: str) -> bool:
    name = _creditor_name(value)
    return (
        name is not None
        and sum(character.isalpha() for character in name) >= 2
        and not _is_field_label(value)
        and _AMOUNT_VALUE.fullmatch(value) is None
        and _iso_date(value) is None
    )


def _valid_amount_value(value: str) -> bool:
    return _AMOUNT_VALUE.fullmatch(value) is not None


def _valid_budget_value(value: str) -> bool:
    return (
        3 <= len(value) <= 200
        and sum(character.isdigit() for character in value) >= 2
        and not _is_field_label(value)
        and _AMOUNT_VALUE.fullmatch(value) is None
        and _iso_date(value) is None
        and _CNPJ.search(value) is None
        and _CPF.search(value) is None
    )


def _following_line_value(
    pattern: re.Pattern[str],
    text: str,
    validator: Callable[[str], bool],
) -> str | None:
    match = pattern.search(text)
    if match is None:
        return None
    for line in text[match.end() :].splitlines():
        value = line.strip()
        if not value:
            continue
        if _is_field_label(value):
            return None
        return value if validator(value) else None
    return None


def _redacted_evidence(text: str) -> str:
    return _CPF.sub("***.***.***-**", text[:_MAX_EVIDENCE_CHARS]).strip()


def find_commitment_candidates(
    pages: tuple[PageInput, ...],
) -> tuple[TcmBaCommitmentCandidate, ...]:
    candidates: list[TcmBaCommitmentCandidate] = []
    seen_candidates: set[
        tuple[str, str | None, str | None, str | None, str | None, str | None]
    ] = set()
    required_fields = (
        "issue_date",
        "creditor_name",
        "amount_text",
        "budget_allocation",
    )
    for page in pages:
        if page.text is None:
            continue
        markers = tuple(_DOCUMENT_MARKER.finditer(page.text))
        for index, marker in enumerate(markers):
            block_end = (
                markers[index + 1].start()
                if index + 1 < len(markers)
                else len(page.text)
            )
            block = page.text[marker.start() : block_end]
            heading = _HEADING.search(block)
            number_match = heading or _LABELED_COMMITMENT_NUMBER.search(block)
            if number_match is None:
                continue
            commitment_number = _canonical_commitment_number(
                number_match.group("number")
            )
            if not commitment_number:
                continue
            issue_value = _match_value(_ISSUE_DATE, block) or _following_line_value(
                _ISSUE_DATE_LABEL,
                block,
                _valid_date_value,
            )
            creditor_value = _match_value(_CREDITOR, block) or _following_line_value(
                _CREDITOR_LABEL,
                block,
                _valid_creditor_value,
            )
            amount_text = _match_value(_AMOUNT, block) or _following_line_value(
                _AMOUNT_LABEL,
                block,
                _valid_amount_value,
            )
            budget_allocation = _match_value(
                _BUDGET_ALLOCATION,
                block,
            ) or _following_line_value(
                _BUDGET_ALLOCATION_LABEL,
                block,
                _valid_budget_value,
            )
            values: dict[str, str | None] = {
                "issue_date": _iso_date(issue_value),
                "creditor_name": _creditor_name(creditor_value),
                "amount_text": amount_text,
                "budget_allocation": budget_allocation,
            }
            creditor_cnpj = _creditor_cnpj(block)
            candidate_identity = (
                commitment_number,
                values["issue_date"],
                values["creditor_name"],
                creditor_cnpj,
                values["amount_text"],
                values["budget_allocation"],
            )
            if candidate_identity in seen_candidates:
                continue
            candidates.append(
                TcmBaCommitmentCandidate(
                    page_number=page.page_number,
                    commitment_number=commitment_number,
                    issue_date=values["issue_date"],
                    creditor_name=values["creditor_name"],
                    amount_text=values["amount_text"],
                    budget_allocation=values["budget_allocation"],
                    missing_fields=tuple(
                        field for field in required_fields if values[field] is None
                    ),
                    evidence_excerpt=_redacted_evidence(block),
                    creditor_cnpj=creditor_cnpj,
                )
            )
            seen_candidates.add(candidate_identity)
    return tuple(candidates)
