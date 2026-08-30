"""Associação espacial conservadora de campos em notas de empenho TCM-BA."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from .gazette_documents import BoundingBox, DocumentBlock

SpatialRelation = Literal["below", "right"]

_MONEY = re.compile(r"^(?:R\$\s*)?-?[\d.]+,\d{2}$", re.IGNORECASE)
_DATE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
_CPF = re.compile(r"^\d{3}[.\s]?\d{3}[.\s]?\d{3}[-\s]?\d{2}$")
_CNPJ = re.compile(r"^\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}$")
_BUDGET_LABELS = {
    "DOTACAO",
    "DOTACAO ORCAMENTARIA",
    "CLASSIFICACAO ORCAMENTARIA",
}
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
