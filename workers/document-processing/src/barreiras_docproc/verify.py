"""Verificação literal de campos contra o trecho oficial (ADR 0012).

Quem decide a publicação automática não é a IA: é este verificador
determinístico e versionado. Um valor — venha da extração determinística ou
da sugestão assistida — só é aceito se ocorrer literalmente no trecho
oficial (normalizado por espaços, caixa e acentos; datas conferidas por
extenso e nos formatos usuais). O que não passa fica na fila humana.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Any

VERIFIER_VERSION = "gazette-act-verifier/2.2.0"
# Sem estes verificados, nada é publicado automaticamente.
REQUIRED_FIELDS = ("person_name", "act_number", "act_date", "position")
OPTIONAL_FIELDS = ("position_symbol", "organization")
# Publicação automática exige também a leitura recomposta pela IA: sem ela
# o cidadão receberia o texto fragmentado do PDF.
REQUIRE_CLEAN_TEXT = True

# Palavras que só aparecem quando a captura passou para outro ato/bloco.
_BLOCK_MARKER = re.compile(
    r"\b(EXTRATO|PORTARIA|CONVOCA\w*|EDITAL|DECRETO|AVISO|JUSTIFICATIVA|"
    r"Titular|Suplente|Lei\s+n)\b",
    re.IGNORECASE,
)

_MONTHS_PT = {
    1: "janeiro",
    2: "fevereiro",
    3: "março",
    4: "abril",
    5: "maio",
    6: "junho",
    7: "julho",
    8: "agosto",
    9: "setembro",
    10: "outubro",
    11: "novembro",
    12: "dezembro",
}


@dataclass(frozen=True)
class VerificationOutcome:
    publishable: bool
    verified_fields: dict[str, dict[str, str]]
    missing: tuple[str, ...]


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    stripped = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )
    return re.sub(r"\s+", " ", stripped).casefold().strip()


def value_in_excerpt(value: str, excerpt: str) -> bool:
    normalized_value = _normalize(value)
    if not normalized_value:
        return False
    normalized_excerpt = _normalize(excerpt)
    # Evita aceitar um número/nome que seja apenas substring de outro token
    # (por exemplo, 205 dentro de 1205), sem perder pontuação do documento.
    return re.search(
        rf"(?<![a-z0-9]){re.escape(normalized_value)}(?![a-z0-9])",
        normalized_excerpt,
    ) is not None


def date_in_excerpt(iso_value: str, excerpt: str) -> bool:
    """A data confere se aparece por extenso ou nos formatos usuais."""
    try:
        parsed = date.fromisoformat(iso_value.strip())
    except ValueError:
        return False
    month_name = _MONTHS_PT[parsed.month]
    spellings = (
        f"{parsed.day} de {month_name} de {parsed.year}",
        f"{parsed.day:02d} de {month_name} de {parsed.year}",
        f"{parsed.day:02d}/{parsed.month:02d}/{parsed.year}",
        f"{parsed.day}/{parsed.month}/{parsed.year}",
        parsed.isoformat(),
    )
    normalized_excerpt = _normalize(excerpt)
    return any(
        _normalize(spelling) in normalized_excerpt for spelling in spellings
    )


def _field_verified(field: str, value: str, excerpt: str) -> bool:
    if field == "act_date":
        return date_in_excerpt(value, excerpt)
    if not value_in_excerpt(value, excerpt):
        return False
    if field == "person_name":
        # "SMS JUSTIFICATIVA" chegou ao site por sugestão da IA: estar no
        # texto não basta, precisa parecer nome de pessoa.
        from .fields import _plausible_person

        return _plausible_person(value)
    if field == "organization":
        # Órgão que invade o bloco seguinte da edição não é órgão.
        return len(value) <= 90 and not _BLOCK_MARKER.search(value)
    return True


def _deterministic_value(fields: dict[str, Any], field: str) -> str | None:
    entry = fields.get(field)
    if isinstance(entry, dict):
        value = entry.get("value")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def verify_candidate(
    payload: dict[str, Any],
    suggestions: dict[str, Any] | None,
    summary: str | None,
    clean_text: str | None = None,
) -> VerificationOutcome:
    """Confere campo a campo; sugestão fora do texto é descartada, nunca
    publicada."""
    excerpt = str(payload.get("excerpt") or "")
    fields = payload.get("fields") or {}
    if not isinstance(fields, dict):
        fields = {}
    assisted = suggestions or {}

    verified: dict[str, dict[str, str]] = {}
    missing: list[str] = []
    for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
        candidates = (
            (_deterministic_value(fields, field), "deterministic"),
            (
                (
                    assisted.get(field).strip()
                    if isinstance(assisted.get(field), str)
                    and assisted.get(field).strip()
                    else None
                ),
                "assisted",
            ),
        )
        accepted = False
        for value, source in candidates:
            if value and excerpt and _field_verified(field, value, excerpt):
                verified[field] = {"value": value, "source": source}
                accepted = True
                break
        if not accepted and field in REQUIRED_FIELDS:
            missing.append(field)

    # Um card com duas pessoas não pode ser publicado como se fosse um único
    # ato individual. A revisão humana deve separar/verificar cada nome antes
    # de qualquer publicação.
    person_names = fields.get("person_names")
    if fields.get("multiple_persons_detected") is True or (
        isinstance(person_names, list) and len(person_names) > 1
    ):
        missing.append("multiple_persons_requires_split_review")

    if not (summary and summary.strip()):
        missing.append("assisted_summary")
    if REQUIRE_CLEAN_TEXT and not (clean_text and clean_text.strip()):
        missing.append("clean_text")

    return VerificationOutcome(
        publishable=not missing,
        verified_fields=verified,
        missing=tuple(missing),
    )
