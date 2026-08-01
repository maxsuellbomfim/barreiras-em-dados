"""Extração determinística de campos de atos de pessoal.

Regras fixas e versionadas sobre o texto canônico, aplicadas ao redor do
verbo do ato. Cada campo tem estado explícito: `matched` com a regra que o
encontrou ou `not_found` — nunca um palpite. Nenhum LLM participa e nenhuma
probabilidade é inventada.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

FIELDSET_VERSION = "gazette-act-fields/1.1.0"
FIELD_WINDOW = 400
HEADING_WINDOW = 600

_MONTHS = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}

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
_HEADING_PATTERN = re.compile(
    r"PORTARIA\s+N\s*[°ºo.]*\s*([\d./-]{1,20})\s*,?\s*"
    r"DE\s+(\d{1,2})\s+DE\s+([A-ZÀ-Üa-zà-ü]+)\s+DE\s+(\d{4})",
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
    act_number: FieldExtraction
    act_date: FieldExtraction


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


def _strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    return "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )


def _heading_fields(
    heading_window: str,
) -> tuple[FieldExtraction, FieldExtraction]:
    """Último cabeçalho de Portaria antes do verbo: número e data do ato."""
    matches = list(_HEADING_PATTERN.finditer(heading_window))
    if not matches:
        return (
            _not_found("act-number-portaria-heading"),
            _not_found("act-date-portaria-heading"),
        )

    heading = matches[-1]
    number = _matched("act-number-portaria-heading", heading.group(1))
    month = _MONTHS.get(_strip_accents(heading.group(3)).lower())
    if month is None:
        return number, _not_found("act-date-portaria-heading")
    try:
        act_date = date(int(heading.group(4)), month, int(heading.group(2)))
    except ValueError:
        return number, _not_found("act-date-portaria-heading")
    return number, _matched(
        "act-date-portaria-heading",
        act_date.isoformat(),
    )


def extract_act_fields(
    text: str,
    *,
    match_start: int,
    match_end: int,
) -> ActFields:
    """Extrai campos ao redor do verbo do ato, com offsets absolutos."""
    window = text[match_end : match_end + FIELD_WINDOW]
    heading_window = text[max(0, match_start - HEADING_WINDOW) : match_start]

    person = _PERSON_PATTERN.search(window)
    position = _POSITION_PATTERN.search(window)
    symbol = _SYMBOL_PATTERN.search(window)
    organization = _ORGANIZATION_PATTERN.search(window)
    act_number, act_date = _heading_fields(heading_window)

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
        act_number=act_number,
        act_date=act_date,
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
        "act_number": entry(fields.act_number),
        "act_date": entry(fields.act_date),
    }
