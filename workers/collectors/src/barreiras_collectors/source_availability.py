"""Fonte externa fora do ar: falha tratada dentro do prazo (ADR 0089).

A falha continua registrada como sempre; muda só o código de saída. Dentro do
prazo de atualização da fonte, o comando sai com 75 (EX_TEMPFAIL) e o
workflow vira aviso; além do prazo, ou sem prazo configurado, sai com 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

SOURCE_UNAVAILABLE_EXIT_CODE = 75
UNHANDLED_FAILURE_EXIT_CODE = 1


class SourceUnavailable(Exception):
    """A fonte não respondeu depois das novas tentativas (transporte/5xx/429).

    Resposta que chegou fora do contrato nunca usa esta marca.
    """


@dataclass(frozen=True)
class SourceFreshness:
    last_valid_at: datetime | None
    expected_hours: int | None
    grace_hours: int


def unavailable_exit_code(freshness: SourceFreshness, *, now: datetime) -> int:
    if freshness.expected_hours is None or freshness.last_valid_at is None:
        return UNHANDLED_FAILURE_EXIT_CODE
    deadline = freshness.last_valid_at + timedelta(
        hours=freshness.expected_hours + freshness.grace_hours
    )
    if now <= deadline:
        return SOURCE_UNAVAILABLE_EXIT_CODE
    return UNHANDLED_FAILURE_EXIT_CODE
