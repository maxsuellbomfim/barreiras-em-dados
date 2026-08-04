"""Texto canônico reproduzível a partir do artefato de texto preservado."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

# A nova versão permite reconstruir artefatos textuais cuja página 1.0.0
# divergiu, mantendo ambas as derivações auditáveis no acervo.
PARSER_VERSION = "gazette-canonical-text/1.1.0"

# Alguns PDFs do Diário trazem NUL e outros controles vazados da camada
# binária. Não são conteúdo: são ruído de extração, e o PostgreSQL recusa
# NUL em campo `text`. Remover é parte da normalização — nunca houve texto
# com NUL persistido para divergir, porque a gravação falhava.
_ALLOWED_CONTROLS = {"\n", "\t"}


def sanitize_text(value: str) -> str:
    """Remove NUL e controles inválidos, preservando quebra e tabulação."""
    return "".join(
        character
        for character in value
        if character in _ALLOWED_CONTROLS or character.isprintable()
    )


class CanonicalTextError(RuntimeError):
    """O artefato de texto não pôde ser canonizado de forma determinística."""


@dataclass(frozen=True)
class CanonicalText:
    text: str
    sha256: str
    parser_version: str


def derive_canonical_text(raw_body: bytes) -> CanonicalText:
    """Decodifica UTF-8 estrito e normaliza quebras de linha para LF."""
    if not raw_body:
        raise CanonicalTextError("O artefato de texto está vazio.")
    try:
        decoded = raw_body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CanonicalTextError(
            "O artefato de texto não é UTF-8 válido."
        ) from error

    normalized = sanitize_text(
        decoded.replace("\r\n", "\n").replace("\r", "\n")
    )
    return CanonicalText(
        text=normalized,
        sha256=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        parser_version=PARSER_VERSION,
    )
