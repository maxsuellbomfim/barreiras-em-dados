"""Regras determinísticas e versionadas de candidatos de atos de pessoal.

Nenhum LLM, nenhuma probabilidade: expressões regulares fixas produzem
candidatos com offsets reproduzíveis no texto canônico. Todo candidato nasce
com estado `needs_review` e nada é publicado sem aprovação humana.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

RULESET_VERSION = "gazette-act-candidates/1.0.0"
EXCERPT_RADIUS = 400

_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "nomeacao-verbo",
        "nomeacao",
        re.compile(r"\bNOMEAR\b|\bNOMEIA\b|\bNOMEA[ÇC][ÃA]O\b", re.IGNORECASE),
    ),
    (
        "exoneracao-verbo",
        "exoneracao",
        re.compile(
            r"\bEXONERAR\b|\bEXONERA\b|\bEXONERA[ÇC][ÃA]O\b",
            re.IGNORECASE,
        ),
    ),
)


@dataclass(frozen=True)
class ActCandidate:
    act_type: str
    rule_id: str
    ruleset_version: str
    match_start: int
    match_end: int
    match_text: str
    excerpt_start: int
    excerpt_end: int
    excerpt: str


def find_candidates(text: str) -> tuple[ActCandidate, ...]:
    """Varre o texto canônico e devolve candidatos em ordem determinística."""
    found: list[ActCandidate] = []
    for rule_id, act_type, pattern in _RULES:
        for match in pattern.finditer(text):
            excerpt_start = max(0, match.start() - EXCERPT_RADIUS)
            excerpt_end = min(len(text), match.end() + EXCERPT_RADIUS)
            found.append(
                ActCandidate(
                    act_type=act_type,
                    rule_id=rule_id,
                    ruleset_version=RULESET_VERSION,
                    match_start=match.start(),
                    match_end=match.end(),
                    match_text=match.group(0),
                    excerpt_start=excerpt_start,
                    excerpt_end=excerpt_end,
                    excerpt=text[excerpt_start:excerpt_end],
                )
            )
    found.sort(key=lambda candidate: (candidate.match_start, candidate.rule_id))
    return tuple(found)
