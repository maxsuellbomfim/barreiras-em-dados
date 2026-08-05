"""Assistência local, determinística e auditável para atos de pessoal.

Este módulo é o plano de continuidade quando as APIs de modelos estão sem
cota. Ele não interpreta o documento: apenas recompõe o trecho já preservado
e monta uma frase neutra com campos que o extrator determinístico encontrou.
Casos incompletos ou com mais de uma pessoa continuam na revisão humana.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .candidates import RULESET_VERSION, clean_excerpt

LOCAL_ASSIST_VERSION = "deterministic-act-assist/1.0.0"
LOCAL_PROVIDER = "local-deterministic"
LOCAL_MODEL = "ruleset-v1"


@dataclass(frozen=True)
class LocalAssistOutcome:
    provider: str
    model: str
    suggestions: dict[str, str | None]
    summary: str
    clean_text: str
    raw_response: str


def _field_value(fields: dict[str, Any], name: str) -> str | None:
    entry = fields.get(name)
    if not isinstance(entry, dict):
        return None
    value = entry.get("value")
    return value.strip() if isinstance(value, str) and value.strip() else None


def build_local_act_assist(
    act_type: str,
    payload: dict[str, Any],
) -> LocalAssistOutcome | None:
    """Cria comentário factual somente quando os campos essenciais existem."""

    excerpt = str(payload.get("excerpt") or "")
    fields = payload.get("fields")
    if not excerpt.strip() or not isinstance(fields, dict):
        return None
    person = _field_value(fields, "person_name")
    position = _field_value(fields, "position")
    act_number = _field_value(fields, "act_number")
    act_date = _field_value(fields, "act_date")
    person_names = fields.get("person_names")
    if (
        not person
        or not position
        or not act_number
        or not act_date
        or fields.get("multiple_persons_detected") is True
        or (isinstance(person_names, list) and len(person_names) > 1)
    ):
        return None

    cleaned = clean_excerpt(excerpt)
    if not cleaned:
        return None
    verb = "nomeação" if act_type == "nomeacao" else "exoneração"
    relation = "para o cargo de" if act_type == "nomeacao" else "do cargo de"
    summary = (
        f"O ato registra a {verb} de {person} {relation} {position}."
    )
    raw = {
        "schema_name": "local-deterministic-assist",
        "schema_version": LOCAL_ASSIST_VERSION,
        "provider": LOCAL_PROVIDER,
        "model": LOCAL_MODEL,
        "ruleset_version": RULESET_VERSION,
        "act_type": act_type,
        "act_number": act_number,
        "act_date": act_date,
        "source_excerpt_sha256": hashlib.sha256(
            excerpt.encode("utf-8")
        ).hexdigest(),
        "method": "template-from-deterministic-fields",
    }
    return LocalAssistOutcome(
        provider=LOCAL_PROVIDER,
        model=LOCAL_MODEL,
        suggestions={},
        summary=summary,
        clean_text=cleaned[:12000],
        raw_response=json.dumps(raw, ensure_ascii=False, sort_keys=True),
    )

