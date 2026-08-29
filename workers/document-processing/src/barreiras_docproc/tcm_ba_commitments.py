"""Candidatos conservadores de notas de empenho preservadas do TCM-BA."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .processing import PageInput, TextArtifact

EXTRACTOR_VERSION = "tcm-ba-commitment-candidates/1.0.0"
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
    return {
        "schema_name": "tcm-ba-commitment-candidate",
        "schema_version": "1.0.0",
        "candidate_status": "complete" if candidate.complete else "incomplete",
        "commitment_number": candidate.commitment_number,
        "issue_date": candidate.issue_date,
        "creditor_name": candidate.creditor_name,
        "creditor_cnpj": candidate.creditor_cnpj,
        "amount_text": candidate.amount_text,
        "budget_allocation": candidate.budget_allocation,
        "missing_fields": list(candidate.missing_fields),
        "source_page_number": candidate.page_number,
        "evidence_excerpt": candidate.evidence_excerpt,
        "source_artifact_sha256": artifact.sha256,
        "extractor_version": EXTRACTOR_VERSION,
    }


class TcmBaCommitmentExtractionService:
    def __init__(self, *, repository: TcmBaCommitmentRepository) -> None:
        self.repository = repository

    def process(
        self,
        artifact: TextArtifact,
        pages: tuple[PageInput, ...],
    ) -> TcmBaCommitmentPersistResult:
        batch = TcmBaCommitmentBatch(
            artifact=artifact,
            pages=pages,
            job_type=JOB_TYPE,
            job_idempotency_key=commitment_job_idempotency_key(artifact.sha256),
            extractor_version=EXTRACTOR_VERSION,
            candidates=find_commitment_candidates(pages),
        )
        return self.repository.persist_tcm_ba_commitment_candidates(batch)


_HEADING = re.compile(
    r"^[ \t]*NOTA\s+DE\s+EMPENHO\s+"
    r"(?:N\s*[º°O.]?\s*)?"
    r"(?P<number>\d[\d./-]{0,29})[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_ISSUE_DATE = re.compile(
    r"^[ \t]*(?:DATA\s+(?:DE\s+)?EMISSÃO|EMISSÃO|EMISSAO)"
    r"\s*[:.-]\s*(?P<value>\d{1,2}/\d{1,2}/\d{4})[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_CREDITOR = re.compile(
    r"^[ \t]*(?:CREDOR|FAVORECIDO|BENEFICIÁRIO|BENEFICIARIO)"
    r"\s*[:.-]\s*(?P<value>[^\n]+)$",
    re.IGNORECASE | re.MULTILINE,
)
_AMOUNT = re.compile(
    r"^[ \t]*VALOR(?:\s+DO\s+EMPENHO)?\s*[:.-]\s*"
    r"(?:R\$\s*)?(?P<value>-?[\d.]+,\d{2})[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_BUDGET_ALLOCATION = re.compile(
    r"^[ \t]*(?:DOTAÇÃO(?:\s+ORÇAMENTÁRIA)?|DOTACAO"
    r"(?:\s+ORCAMENTARIA)?|CLASSIFICAÇÃO\s+ORÇAMENTÁRIA|"
    r"CLASSIFICACAO\s+ORCAMENTARIA)\s*[:.-]\s*"
    r"(?P<value>[^\n]+)$",
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


def _redacted_evidence(text: str) -> str:
    return _CPF.sub("***.***.***-**", text[:_MAX_EVIDENCE_CHARS]).strip()


def find_commitment_candidates(
    pages: tuple[PageInput, ...],
) -> tuple[TcmBaCommitmentCandidate, ...]:
    candidates: list[TcmBaCommitmentCandidate] = []
    required_fields = (
        "issue_date",
        "creditor_name",
        "amount_text",
        "budget_allocation",
    )
    for page in pages:
        if page.text is None:
            continue
        headings = tuple(_HEADING.finditer(page.text))
        for index, heading in enumerate(headings):
            block_end = (
                headings[index + 1].start()
                if index + 1 < len(headings)
                else len(page.text)
            )
            block = page.text[heading.start() : block_end]
            creditor_value = _match_value(_CREDITOR, block)
            values: dict[str, str | None] = {
                "issue_date": _iso_date(_match_value(_ISSUE_DATE, block)),
                "creditor_name": _creditor_name(creditor_value),
                "amount_text": _match_value(_AMOUNT, block),
                "budget_allocation": _match_value(
                    _BUDGET_ALLOCATION,
                    block,
                ),
            }
            candidates.append(
                TcmBaCommitmentCandidate(
                    page_number=page.page_number,
                    commitment_number=heading.group("number"),
                    issue_date=values["issue_date"],
                    creditor_name=values["creditor_name"],
                    amount_text=values["amount_text"],
                    budget_allocation=values["budget_allocation"],
                    missing_fields=tuple(
                        field for field in required_fields if values[field] is None
                    ),
                    evidence_excerpt=_redacted_evidence(block),
                    creditor_cnpj=_creditor_cnpj(creditor_value),
                )
            )
    return tuple(candidates)
