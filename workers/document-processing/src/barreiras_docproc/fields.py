"""Extração determinística de campos de atos de pessoal.

Regras fixas e versionadas sobre o texto canônico, aplicadas ao redor do
verbo do ato. Cada campo tem estado explícito: `matched` com a regra que o
encontrou ou `not_found` — nunca um palpite. Nenhum LLM participa e nenhuma
probabilidade é inventada.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

FIELDSET_VERSION = "gazette-act-fields/1.0.0"
FIELD_WINDOW = 400

_UPPER = "A-ZÁÀÂÃÉÈÊÍÏÓÔÕÖÚÜÇ"
# Travessão e apóstrofo tipográfico ocorrem nos textos reais dos diários.
_PERSON_PATTERN = re.compile(
    rf"^[\s,:–-]*(?:a\s+pedido\s*,?\s*)?"  # noqa: RUF001
    rf"((?:[{_UPPER}][{_UPPER}'’-]+)"  # noqa: RUF001
    rf"(?:\s+(?:D[AEO]S?\s+|E\s+)?[{_UPPER}][{_UPPER}'’-]+)+)"  # noqa: RUF001
)
_POSITION_PATTERN = re.compile(
    r"(?:para|do|da)\s+o?\s*cargo(?:\s+em\s+comiss[ãa]o)?\s+de\s+"
    r"([^,\n]{3,120}?)"
    r"(?=,|\s+s[íi]mbolo|\s+d[ao]\s+Secretaria|\.|\n)",
    re.IGNORECASE,
)
_SYMBOL_PATTERN = re.compile(
    r"s[íi]mbolo\s+([A-Z]{1,5}\s*-\s*\d+)",
    re.IGNORECASE,
)
_ORGANIZATION_PATTERN = re.compile(
    r"(Secretaria(?:\s+Municipal)?\s+de\s+[^,.\n]{3,120})",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FieldExtraction:
    value: str | None
    status: str
    rule_id: str


@dataclass(frozen=True)
class ActFields:
    fieldset_version: str
    person_name: FieldExtraction
    position: FieldExtraction
    position_symbol: FieldExtraction
    organization: FieldExtraction


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" ,;:–-")  # noqa: RUF001


def _matched(rule_id: str, value: str) -> FieldExtraction:
    return FieldExtraction(
        value=_normalize(value),
        status="matched",
        rule_id=rule_id,
    )


def _not_found(rule_id: str) -> FieldExtraction:
    return FieldExtraction(value=None, status="not_found", rule_id=rule_id)


def extract_act_fields(
    text: str,
    *,
    match_start: int,
    match_end: int,
) -> ActFields:
    """Extrai campos na janela após o verbo do ato, com offsets absolutos."""
    del match_start
    window = text[match_end : match_end + FIELD_WINDOW]

    person = _PERSON_PATTERN.search(window)
    position = _POSITION_PATTERN.search(window)
    symbol = _SYMBOL_PATTERN.search(window)
    organization = _ORGANIZATION_PATTERN.search(window)

    return ActFields(
        fieldset_version=FIELDSET_VERSION,
        person_name=(
            _matched("person-uppercase-after-verb", person.group(1))
            if person
            else _not_found("person-uppercase-after-verb")
        ),
        position=(
            _matched("position-after-cargo-de", position.group(1))
            if position
            else _not_found("position-after-cargo-de")
        ),
        position_symbol=(
            _matched("symbol-after-simbolo", symbol.group(1))
            if symbol
            else _not_found("symbol-after-simbolo")
        ),
        organization=(
            _matched("organization-secretaria", organization.group(1))
            if organization
            else _not_found("organization-secretaria")
        ),
    )


def fields_payload(fields: ActFields) -> dict[str, object]:
    def entry(extraction: FieldExtraction) -> dict[str, object]:
        return {
            "value": extraction.value,
            "status": extraction.status,
            "rule_id": extraction.rule_id,
        }

    return {
        "fieldset_version": fields.fieldset_version,
        "person_name": entry(fields.person_name),
        "position": entry(fields.position),
        "position_symbol": entry(fields.position_symbol),
        "organization": entry(fields.organization),
    }
