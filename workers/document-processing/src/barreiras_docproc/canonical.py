"""Texto canônico reproduzível a partir do artefato de texto preservado."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

PARSER_VERSION = "gazette-canonical-text/1.0.0"


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

    normalized = decoded.replace("\r\n", "\n").replace("\r", "\n")
    return CanonicalText(
        text=normalized,
        sha256=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        parser_version=PARSER_VERSION,
    )
