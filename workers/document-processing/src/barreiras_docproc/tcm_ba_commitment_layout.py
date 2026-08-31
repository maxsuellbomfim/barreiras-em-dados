"""Associação espacial conservadora de campos em notas de empenho TCM-BA."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .gazette_documents import BoundingBox, DocumentBlock

SpatialRelation = Literal["below", "right", "inline"]
CreditorLabelKind = Literal[
    "creditor",
    "favored",
    "beneficiary",
    "social_name",
]
CreditorDiagnosisStatus = Literal[
    "matched",
    "no_label",
    "multiple_labels",
    "no_compatible_value",
    "ambiguous_values",
]
IssueDateLabelKind = Literal[
    "commitment_date",
    "issue_date",
    "emission",
    "generic_date",
]
IssueDateRole = Literal[
    "commitment",
    "emission",
    "liquidation",
    "payment",
    "processing",
    "due_date",
    "publication",
    "signature",
    "period",
    "generic_date",
    "unknown",
]
IssueDateDiagnosisStatus = Literal[
    "matched",
    "inline_labeled",
    "same_block_labeled",
    "no_label",
    "multiple_labels",
    "no_compatible_value",
    "ambiguous_values",
]
InlineIssueDateConsensusStatus = Literal[
    "none",
    "single",
    "repeated_consensus",
    "conflict",
]

_MONEY = re.compile(r"^(?:R\$\s*)?-?[\d.]+,\d{2}$", re.IGNORECASE)
_DATE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
_DATE_TOKEN_PATTERNS = (
    ("dmy_slash", re.compile(r"(?<!\d)\d{1,2}/\d{1,2}/\d{4}(?!\d)"), "%d/%m/%Y"),
    ("dmy_dash", re.compile(r"(?<!\d)\d{1,2}-\d{1,2}-\d{4}(?!\d)"), "%d-%m-%Y"),
    ("iso", re.compile(r"(?<!\d)\d{4}-\d{1,2}-\d{1,2}(?!\d)"), "%Y-%m-%d"),
)
_CPF = re.compile(r"^\d{3}[.\s]?\d{3}[.\s]?\d{3}[-\s]?\d{2}$")
_CNPJ = re.compile(r"^\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}$")
_BUDGET_LABELS = {
    "DOTACAO",
    "DOTACAO ORCAMENTARIA",
    "CLASSIFICACAO ORCAMENTARIA",
}
_ISSUE_DATE_LABELS = {
    "DATA DE EMISSAO",
    "DATA DO EMPANHO",
    "DATA DO EMPENHO",
    "EMISSAO",
}
_ISSUE_DATE_DIAGNOSTIC_LABEL_KINDS: dict[str, IssueDateLabelKind] = {
    "DATA DE EMISSAO": "issue_date",
    "DATA EMISSAO": "issue_date",
    "DATA DO EMPANHO": "commitment_date",
    "DATA DO EMPENHO": "commitment_date",
    "DATA EMPANHO": "commitment_date",
    "DATA EMPENHO": "commitment_date",
    "EMISSAO": "emission",
    "DATA": "generic_date",
    "DT": "generic_date",
}
_AMOUNT_LABELS = {
    "VALOR",
    "VALOR BRUTO",
    "VALOR DO EMPENHO",
}
_CREDITOR_LABEL_KINDS: dict[str, CreditorLabelKind] = {
    "CREDOR": "creditor",
    "FAVORECIDO": "favored",
    "BENEFICIARIO": "beneficiary",
    "SOCIAL NOME": "social_name",
    "R SOCIAL NOME": "social_name",
    "RAZAO SOCIAL NOME": "social_name",
}
_ALL_FIELD_LABELS = (
    _BUDGET_LABELS | _ISSUE_DATE_LABELS | _AMOUNT_LABELS | set(_CREDITOR_LABEL_KINDS)
)
_DOCUMENT_SUFFIX = re.compile(
    r"\s*(?:[-|]\s*)?(?:CPF|CNPJ|C\.?P\.?F\.?|C\.?N\.?P\.?J\.?)"
    r"\b.*$",
    re.IGNORECASE,
)

_MAX_PRIMARY_SCORE = 20.0
_MIN_SECONDARY_SCORE_DELTA = 5.0


@dataclass(frozen=True)
class SpatialBudgetMatch:
    value: str
    page_number: int
    label_block_order: int
    value_block_order: int
    relation: SpatialRelation


@dataclass(frozen=True)
class _ScoredMatch:
    match: SpatialBudgetMatch
    score: float


@dataclass(frozen=True)
class SpatialScalarMatch:
    value: str
    page_number: int
    label_block_order: int
    value_block_order: int
    relation: SpatialRelation
    occurrence_count: int = 1


@dataclass(frozen=True)
class _ScoredScalarMatch:
    match: SpatialScalarMatch
    score: float


@dataclass(frozen=True)
class SpatialCreditorDiagnosis:
    status: CreditorDiagnosisStatus
    label_kind: CreditorLabelKind | None = None
    match: SpatialScalarMatch | None = None


@dataclass(frozen=True)
class SpatialIssueDateDiagnosis:
    status: IssueDateDiagnosisStatus
    date_value_count: int
    date_format_counts: tuple[tuple[str, int], ...]
    date_role_counts: tuple[tuple[str, int], ...]
    direct_date_role_counts: tuple[tuple[str, int], ...]
    explicit_issue_date_count: int
    safe_context_patterns: tuple[str, ...]
    label_kind: IssueDateLabelKind | None = None
    match: SpatialScalarMatch | None = None


@dataclass(frozen=True)
class InlineIssueDateConsensus:
    status: InlineIssueDateConsensusStatus
    occurrence_count: int
    match: SpatialScalarMatch | None = None


def _normalized_label(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    compact = re.sub(r"[^A-Z0-9]+", " ", ascii_text.upper()).strip()
    return compact


def _is_budget_label(text: str) -> bool:
    return _normalized_label(text) in _BUDGET_LABELS


def _is_budget_value(text: str) -> bool:
    value = " ".join(text.split())
    digits = sum(character.isdigit() for character in value)
    return (
        3 <= len(value) <= 200
        and digits >= 2
        and not _is_budget_label(value)
        and _MONEY.fullmatch(value) is None
        and _DATE.fullmatch(value) is None
        and _CPF.fullmatch(value) is None
        and _CNPJ.fullmatch(value) is None
        and (digits >= 6 or any(separator in value for separator in (".", "/", "-")))
    )


def _width(box: BoundingBox) -> float:
    return max(box[2] - box[0], 0.0)


def _height(box: BoundingBox) -> float:
    return max(box[3] - box[1], 0.0)


def _center_x(box: BoundingBox) -> float:
    return (box[0] + box[2]) / 2.0


def _center_y(box: BoundingBox) -> float:
    return (box[1] + box[3]) / 2.0


def _overlap(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
    return max(min(end_a, end_b) - max(start_a, start_b), 0.0)


def _below_score(label: BoundingBox, value: BoundingBox) -> float | None:
    vertical_gap = label[1] - value[3]
    if not -2.0 <= vertical_gap <= 72.0:
        return None
    horizontal_overlap = _overlap(label[0], label[2], value[0], value[2])
    minimum_width = min(_width(label), _width(value))
    if minimum_width <= 0.0 or horizontal_overlap / minimum_width < 0.35:
        return None
    center_delta = abs(_center_x(label) - _center_x(value))
    if center_delta > max(_width(label), _width(value)) * 0.6:
        return None
    return max(vertical_gap, 0.0) + center_delta * 0.25


def _right_score(label: BoundingBox, value: BoundingBox) -> float | None:
    horizontal_gap = value[0] - label[2]
    if not -2.0 <= horizontal_gap <= 80.0:
        return None
    vertical_overlap = _overlap(label[1], label[3], value[1], value[3])
    minimum_height = min(_height(label), _height(value))
    if minimum_height <= 0.0 or vertical_overlap / minimum_height < 0.5:
        return None
    return max(horizontal_gap, 0.0) + abs(_center_y(label) - _center_y(value)) * 0.25


def _creditor_below_score(
    label: BoundingBox,
    value: BoundingBox,
) -> float | None:
    vertical_gap = label[1] - value[3]
    if not -2.0 <= vertical_gap <= 72.0:
        return None
    horizontal_overlap = _overlap(label[0], label[2], value[0], value[2])
    minimum_width = min(_width(label), _width(value))
    if minimum_width <= 0.0 or horizontal_overlap / minimum_width < 0.35:
        return None
    left_delta = abs(label[0] - value[0])
    if left_delta > 48.0:
        return None
    return max(vertical_gap, 0.0) + left_delta * 0.25


def find_spatial_budget_allocation(
    blocks: tuple[DocumentBlock, ...],
) -> SpatialBudgetMatch | None:
    """Retorna apenas uma associação geométrica inequívoca para a dotação."""
    label_count = sum(
        block.bbox is not None and _is_budget_label(block.text) for block in blocks
    )
    if label_count != 1:
        return None
    scored: list[_ScoredMatch] = []
    for label in blocks:
        if label.bbox is None or not _is_budget_label(label.text):
            continue
        for value in blocks:
            if (
                value is label
                or value.bbox is None
                or value.page_number != label.page_number
                or not _is_budget_value(value.text)
            ):
                continue
            below = _below_score(label.bbox, value.bbox)
            right = _right_score(label.bbox, value.bbox)
            options = tuple(
                (relation, score)
                for relation, score in (("below", below), ("right", right))
                if score is not None
            )
            if not options:
                continue
            relation, score = min(options, key=lambda item: item[1])
            scored.append(
                _ScoredMatch(
                    match=SpatialBudgetMatch(
                        value=" ".join(value.text.split()),
                        page_number=value.page_number,
                        label_block_order=label.block_order,
                        value_block_order=value.block_order,
                        relation=relation,
                    ),
                    score=score,
                )
            )

    if not scored:
        return None
    scored.sort(key=lambda candidate: candidate.score)
    if scored[0].score > _MAX_PRIMARY_SCORE:
        return None
    if (
        len(scored) > 1
        and scored[1].score - scored[0].score < _MIN_SECONDARY_SCORE_DELTA
    ):
        return None
    return scored[0].match


def _normalized_issue_date(text: str) -> str | None:
    value = " ".join(text.split())
    if _DATE.fullmatch(value) is None:
        return None
    try:
        return datetime.strptime(value, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def _normalized_amount_text(text: str) -> str | None:
    value = " ".join(text.split())
    if _MONEY.fullmatch(value) is None:
        return None
    return re.sub(r"^R\$\s*", "", value, flags=re.IGNORECASE)


def _find_spatial_scalar(
    blocks: tuple[DocumentBlock, ...],
    *,
    labels: set[str],
    normalize_value: Callable[[str], str | None],
) -> SpatialScalarMatch | None:
    label_count = sum(
        block.bbox is not None and _normalized_label(block.text) in labels
        for block in blocks
    )
    if label_count != 1:
        return None
    scored: list[_ScoredScalarMatch] = []
    for label in blocks:
        if label.bbox is None or _normalized_label(label.text) not in labels:
            continue
        for value in blocks:
            if (
                value is label
                or value.bbox is None
                or value.page_number != label.page_number
            ):
                continue
            normalized_value = normalize_value(value.text)
            if normalized_value is None:
                continue
            below = _below_score(label.bbox, value.bbox)
            right = _right_score(label.bbox, value.bbox)
            options = tuple(
                (relation, score)
                for relation, score in (("below", below), ("right", right))
                if score is not None
            )
            if not options:
                continue
            relation, score = min(options, key=lambda item: item[1])
            scored.append(
                _ScoredScalarMatch(
                    match=SpatialScalarMatch(
                        value=normalized_value,
                        page_number=value.page_number,
                        label_block_order=label.block_order,
                        value_block_order=value.block_order,
                        relation=relation,
                    ),
                    score=score,
                )
            )
    if not scored:
        return None
    scored.sort(key=lambda candidate: candidate.score)
    if scored[0].score > _MAX_PRIMARY_SCORE:
        return None
    if (
        len(scored) > 1
        and scored[1].score - scored[0].score < _MIN_SECONDARY_SCORE_DELTA
    ):
        return None
    return scored[0].match


def _embedded_date_formats(text: str) -> tuple[str, ...]:
    formats: list[str] = []
    for format_kind, pattern, date_format in _DATE_TOKEN_PATTERNS:
        for match in pattern.finditer(text):
            try:
                datetime.strptime(match.group(0), date_format)
            except ValueError:
                continue
            formats.append(format_kind)
    return tuple(formats)


def _date_role(text: str) -> IssueDateRole:
    normalized = _normalized_label(text)
    if "LIQUID" in normalized:
        return "liquidation"
    if "PAGAMENTO" in normalized or "PAGO" in normalized:
        return "payment"
    if "PROCESSAMENTO" in normalized or "PROCESSADO" in normalized:
        return "processing"
    if "VENCIMENTO" in normalized:
        return "due_date"
    if "PUBLICACAO" in normalized or "PUBLICADO" in normalized:
        return "publication"
    if "ASSINATURA" in normalized or "ASSINADO" in normalized:
        return "signature"
    if any(word in normalized for word in ("PERIODO", "INICIAL", "FINAL")):
        return "period"
    if "EMPENHO" in normalized or "EMPANHO" in normalized:
        return "commitment"
    if "EMISSAO" in normalized or "EMITIDO" in normalized or "EMITIDA" in normalized:
        return "emission"
    if normalized == "DATA" or normalized.startswith("DATA "):
        return "generic_date"
    return "unknown"


def _direct_date_roles(text: str) -> tuple[IssueDateRole, ...]:
    roles: list[IssueDateRole] = []
    for line in text.splitlines() or (text,):
        formats = _embedded_date_formats(line)
        if formats:
            role = _date_role(line)
            roles.extend(role for _format in formats)
    return tuple(roles)

def _explicit_issue_date_count(text: str) -> int:
    count = 0
    trusted_kinds = {"commitment_date", "issue_date", "emission"}
    for line in text.splitlines() or (text,):
        formats = _embedded_date_formats(line)
        kinds = set(_diagnostic_label_kinds(line))
        if formats and len(kinds) == 1 and kinds.pop() in trusted_kinds:
            count += len(formats)
    return count

def _embedded_date_roles(text: str) -> tuple[IssueDateRole, ...]:
    roles: list[IssueDateRole] = []
    previous_line = ""
    for line in text.splitlines() or (text,):
        formats = _embedded_date_formats(line)
        if formats:
            role = _date_role(line)
            if role == "unknown" and previous_line:
                role = _date_role(previous_line)
            roles.extend(role for _format in formats)
        if line.strip():
            previous_line = line
    return tuple(roles)

def _diagnostic_text_category(text: str) -> str:
    normalized = _normalized_label(text)
    if normalized in {"DATA", "DT"}:
        return "DATA_LABEL"
    if _embedded_date_formats(text):
        return f"{_date_role(text).upper()}_DATE"
    role = _date_role(text)
    return "OTHER" if role == "unknown" else role.upper()


def diagnostic_issue_date_context_patterns(
    blocks: tuple[DocumentBlock, ...],
) -> tuple[str, ...]:
    """Resume vizinhos de DATA em categorias fechadas, nunca em texto livre."""
    lines = tuple(
        line
        for block in sorted(blocks, key=lambda item: item.block_order)
        for line in block.text.splitlines() or (block.text,)
        if line.strip()
    )
    categories = tuple(_diagnostic_text_category(line) for line in lines)
    patterns: list[str] = []
    for index, category in enumerate(categories):
        if category not in {"DATA_LABEL", "GENERIC_DATE_DATE"}:
            continue
        start = max(index - 2, 0)
        end = min(index + 3, len(categories))
        patterns.append(">".join(categories[start:end]))
    return tuple(patterns)

def _diagnostic_label_kinds(text: str) -> tuple[IssueDateLabelKind, ...]:
    kinds: list[IssueDateLabelKind] = []
    ordered_labels = sorted(
        _ISSUE_DATE_DIAGNOSTIC_LABEL_KINDS.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for line in text.splitlines() or (text,):
        normalized = _normalized_label(line)
        for label, kind in ordered_labels:
            if normalized == label or normalized.startswith(f"{label} "):
                kinds.append(kind)
                break
    return tuple(kinds)


def diagnose_spatial_issue_date(
    blocks: tuple[DocumentBlock, ...],
) -> SpatialIssueDateDiagnosis:
    """Classifica o layout da data sem expor o valor no relatório."""
    format_counts: dict[str, int] = {}
    block_formats: list[tuple[DocumentBlock, tuple[str, ...]]] = []
    for block in blocks:
        if block.bbox is None:
            continue
        formats = _embedded_date_formats(block.text)
        block_formats.append((block, formats))
        for format_kind in formats:
            format_counts[format_kind] = format_counts.get(format_kind, 0) + 1
    date_format_counts = tuple(sorted(format_counts.items()))
    role_counts: dict[str, int] = {}
    for block in blocks:
        if block.bbox is None:
            continue
        for role in _embedded_date_roles(block.text):
            role_counts[role] = role_counts.get(role, 0) + 1
    date_role_counts = tuple(sorted(role_counts.items()))
    direct_role_counts: dict[str, int] = {}
    for block in blocks:
        if block.bbox is None:
            continue
        for role in _direct_date_roles(block.text):
            direct_role_counts[role] = direct_role_counts.get(role, 0) + 1
    direct_date_role_counts = tuple(sorted(direct_role_counts.items()))
    explicit_issue_date_count = sum(
        _explicit_issue_date_count(block.text)
        for block in blocks
        if block.bbox is not None
    )
    safe_context_patterns = diagnostic_issue_date_context_patterns(blocks)
    date_value_count = sum(format_counts.values())
    date_values = tuple(
        (block, normalized)
        for block in blocks
        if block.bbox is not None
        and (normalized := _normalized_issue_date(block.text)) is not None
    )
    labels = tuple(
        (block, _ISSUE_DATE_DIAGNOSTIC_LABEL_KINDS[_normalized_label(block.text)])
        for block in blocks
        if block.bbox is not None
        and _normalized_label(block.text) in _ISSUE_DATE_DIAGNOSTIC_LABEL_KINDS
    )
    if not labels:
        inline_kinds: list[IssueDateLabelKind] = []
        same_block_kinds: list[IssueDateLabelKind] = []
        for block, formats in block_formats:
            if not formats:
                continue
            block_kinds = _diagnostic_label_kinds(block.text)
            if not block_kinds:
                continue
            same_block_kinds.extend(block_kinds)
            for line in block.text.splitlines() or (block.text,):
                if _embedded_date_formats(line):
                    inline_kinds.extend(_diagnostic_label_kinds(line))
        if date_value_count == 1 and len(inline_kinds) == 1:
            return SpatialIssueDateDiagnosis(
                status="inline_labeled",
                date_value_count=date_value_count,
                date_format_counts=date_format_counts,
                date_role_counts=date_role_counts,
                direct_date_role_counts=direct_date_role_counts,
                explicit_issue_date_count=explicit_issue_date_count,
                safe_context_patterns=safe_context_patterns,
                label_kind=inline_kinds[0],
            )
        if date_value_count == 1 and len(same_block_kinds) == 1:
            return SpatialIssueDateDiagnosis(
                status="same_block_labeled",
                date_value_count=date_value_count,
                date_format_counts=date_format_counts,
                date_role_counts=date_role_counts,
                direct_date_role_counts=direct_date_role_counts,
                explicit_issue_date_count=explicit_issue_date_count,
                safe_context_patterns=safe_context_patterns,
                label_kind=same_block_kinds[0],
            )
        if len(inline_kinds) > 1 or len(same_block_kinds) > 1:
            return SpatialIssueDateDiagnosis(
                status="multiple_labels",
                date_value_count=date_value_count,
                date_format_counts=date_format_counts,
                date_role_counts=date_role_counts,
                direct_date_role_counts=direct_date_role_counts,
                explicit_issue_date_count=explicit_issue_date_count,
                safe_context_patterns=safe_context_patterns,
            )
        return SpatialIssueDateDiagnosis(
            status="no_label",
            date_value_count=date_value_count,
            date_format_counts=date_format_counts,
            date_role_counts=date_role_counts,
            direct_date_role_counts=direct_date_role_counts,
            explicit_issue_date_count=explicit_issue_date_count,
            safe_context_patterns=safe_context_patterns,
        )
    if len(labels) != 1:
        return SpatialIssueDateDiagnosis(
            status="multiple_labels",
            date_value_count=date_value_count,
            date_format_counts=date_format_counts,
            date_role_counts=date_role_counts,
            direct_date_role_counts=direct_date_role_counts,
            explicit_issue_date_count=explicit_issue_date_count,
            safe_context_patterns=safe_context_patterns,
        )
    label, label_kind = labels[0]
    label_box = label.bbox
    if label_box is None:
        return SpatialIssueDateDiagnosis(
            status="no_label",
            date_value_count=date_value_count,
            date_format_counts=date_format_counts,
            date_role_counts=date_role_counts,
            direct_date_role_counts=direct_date_role_counts,
            explicit_issue_date_count=explicit_issue_date_count,
            safe_context_patterns=safe_context_patterns,
        )
    scored: list[_ScoredScalarMatch] = []
    for value, normalized_value in date_values:
        value_box = value.bbox
        if (
            value is label
            or value_box is None
            or value.page_number != label.page_number
        ):
            continue
        below = _below_score(label_box, value_box)
        right = _right_score(label_box, value_box)
        options = tuple(
            (relation, score)
            for relation, score in (("below", below), ("right", right))
            if score is not None
        )
        if not options:
            continue
        relation, score = min(options, key=lambda item: item[1])
        scored.append(
            _ScoredScalarMatch(
                match=SpatialScalarMatch(
                    value=normalized_value,
                    page_number=value.page_number,
                    label_block_order=label.block_order,
                    value_block_order=value.block_order,
                    relation=relation,
                ),
                score=score,
            )
        )
    scored.sort(key=lambda candidate: candidate.score)
    if not scored or scored[0].score > _MAX_PRIMARY_SCORE:
        return SpatialIssueDateDiagnosis(
            status="no_compatible_value",
            date_value_count=date_value_count,
            date_format_counts=date_format_counts,
            date_role_counts=date_role_counts,
            direct_date_role_counts=direct_date_role_counts,
            explicit_issue_date_count=explicit_issue_date_count,
            safe_context_patterns=safe_context_patterns,
            label_kind=label_kind,
        )
    if (
        len(scored) > 1
        and scored[1].score - scored[0].score < _MIN_SECONDARY_SCORE_DELTA
    ):
        return SpatialIssueDateDiagnosis(
            status="ambiguous_values",
            date_value_count=date_value_count,
            date_format_counts=date_format_counts,
            date_role_counts=date_role_counts,
            direct_date_role_counts=direct_date_role_counts,
            explicit_issue_date_count=explicit_issue_date_count,
            safe_context_patterns=safe_context_patterns,
            label_kind=label_kind,
        )
    return SpatialIssueDateDiagnosis(
        status="matched",
        date_value_count=date_value_count,
        date_format_counts=date_format_counts,
        date_role_counts=date_role_counts,
        direct_date_role_counts=direct_date_role_counts,
        explicit_issue_date_count=explicit_issue_date_count,
        safe_context_patterns=safe_context_patterns,
        label_kind=label_kind,
        match=scored[0].match,
    )

def _embedded_date_values(text: str) -> tuple[str, ...]:
    values: list[str] = []
    for _format_kind, pattern, date_format in _DATE_TOKEN_PATTERNS:
        for match in pattern.finditer(text):
            try:
                value = (
                    datetime.strptime(match.group(0), date_format).date().isoformat()
                )
            except ValueError:
                continue
            values.append(value)
    return tuple(values)


def diagnose_inline_explicit_issue_date(
    blocks: tuple[DocumentBlock, ...],
) -> InlineIssueDateConsensus:
    """Classifica repetições inline sem expor os valores no diagnóstico."""
    trusted_kinds = {"commitment_date", "issue_date", "emission"}
    matches: list[SpatialScalarMatch] = []
    for block in blocks:
        if block.bbox is None:
            continue
        for line in block.text.splitlines() or (block.text,):
            kinds = set(_diagnostic_label_kinds(line))
            if len(kinds) != 1 or kinds.pop() not in trusted_kinds:
                continue
            for value in _embedded_date_values(line):
                matches.append(
                    SpatialScalarMatch(
                        value=value,
                        page_number=block.page_number,
                        label_block_order=block.block_order,
                        value_block_order=block.block_order,
                        relation="inline",
                    )
                )
    if not matches:
        return InlineIssueDateConsensus(status="none", occurrence_count=0)
    if len(matches) == 1:
        return InlineIssueDateConsensus(
            status="single",
            occurrence_count=1,
            match=matches[0],
        )
    if len({match.value for match in matches}) == 1:
        first = matches[0]
        return InlineIssueDateConsensus(
            status="repeated_consensus",
            occurrence_count=len(matches),
            match=SpatialScalarMatch(
                value=first.value,
                page_number=first.page_number,
                label_block_order=first.label_block_order,
                value_block_order=first.value_block_order,
                relation=first.relation,
                occurrence_count=len(matches),
            ),
        )
    return InlineIssueDateConsensus(
        status="conflict",
        occurrence_count=len(matches),
    )


def find_inline_explicit_issue_date(
    blocks: tuple[DocumentBlock, ...],
) -> SpatialScalarMatch | None:
    """Aceita somente um valor na mesma linha de um rótulo oficial completo."""
    diagnosis = diagnose_inline_explicit_issue_date(blocks)
    return (
        diagnosis.match
        if diagnosis.status in {"single", "repeated_consensus"}
        else None
    )

def find_spatial_issue_date(
    blocks: tuple[DocumentBlock, ...],
) -> SpatialScalarMatch | None:
    """Associa uma data real somente a um rótulo oficial inequívoco."""
    return _find_spatial_scalar(
        blocks,
        labels=_ISSUE_DATE_LABELS,
        normalize_value=_normalized_issue_date,
    )


def find_spatial_amount_text(
    blocks: tuple[DocumentBlock, ...],
) -> SpatialScalarMatch | None:
    """Associa um valor monetário somente a um rótulo oficial inequívoco."""
    return _find_spatial_scalar(
        blocks,
        labels=_AMOUNT_LABELS,
        normalize_value=_normalized_amount_text,
    )


def _normalized_creditor_value(text: str) -> str | None:
    value = " ".join(text.split())
    name = _DOCUMENT_SUFFIX.sub("", value).strip(" -|\t")
    normalized = _normalized_label(name)
    if not 3 <= len(name) <= 200:
        return None
    if sum(character.isalpha() for character in name) < 2:
        return None
    if normalized in _ALL_FIELD_LABELS or normalized in {"NOME", "NOTA DE EMPENHO"}:
        return None
    if (
        _MONEY.fullmatch(name) is not None
        or _DATE.fullmatch(name) is not None
        or _CPF.fullmatch(name) is not None
        or _CNPJ.fullmatch(name) is not None
    ):
        return None
    return name


def diagnose_spatial_creditor(
    blocks: tuple[DocumentBlock, ...],
) -> SpatialCreditorDiagnosis:
    """Classifica a geometria do credor sem expor o valor no relatório."""
    labels = tuple(
        (block, _CREDITOR_LABEL_KINDS[_normalized_label(block.text)])
        for block in blocks
        if block.bbox is not None
        and _normalized_label(block.text) in _CREDITOR_LABEL_KINDS
    )
    if not labels:
        return SpatialCreditorDiagnosis(status="no_label")
    if len(labels) != 1:
        return SpatialCreditorDiagnosis(status="multiple_labels")
    label, label_kind = labels[0]
    label_box = label.bbox
    if label_box is None:
        return SpatialCreditorDiagnosis(status="no_label")
    scored: list[_ScoredScalarMatch] = []
    for value in blocks:
        if (
            value is label
            or value.bbox is None
            or value.page_number != label.page_number
        ):
            continue
        normalized_value = _normalized_creditor_value(value.text)
        if normalized_value is None:
            continue
        below = _creditor_below_score(label_box, value.bbox)
        right = _right_score(label_box, value.bbox)
        options = tuple(
            (relation, score)
            for relation, score in (("below", below), ("right", right))
            if score is not None
        )
        if not options:
            continue
        relation, score = min(options, key=lambda item: item[1])
        scored.append(
            _ScoredScalarMatch(
                match=SpatialScalarMatch(
                    value=normalized_value,
                    page_number=value.page_number,
                    label_block_order=label.block_order,
                    value_block_order=value.block_order,
                    relation=relation,
                ),
                score=score,
            )
        )
    scored.sort(key=lambda candidate: candidate.score)
    if not scored or scored[0].score > _MAX_PRIMARY_SCORE:
        return SpatialCreditorDiagnosis(
            status="no_compatible_value",
            label_kind=label_kind,
        )
    if (
        len(scored) > 1
        and scored[1].score - scored[0].score < _MIN_SECONDARY_SCORE_DELTA
    ):
        return SpatialCreditorDiagnosis(
            status="ambiguous_values",
            label_kind=label_kind,
        )
    return SpatialCreditorDiagnosis(
        status="matched",
        label_kind=label_kind,
        match=scored[0].match,
    )
