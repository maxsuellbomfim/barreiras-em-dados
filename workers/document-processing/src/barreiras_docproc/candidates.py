"""Regras determinísticas e versionadas de candidatos de atos de pessoal.

Nenhum LLM, nenhuma probabilidade: expressões regulares fixas produzem
candidatos com offsets reproduzíveis no texto canônico.

A unidade de candidato é **o ato inteiro** (o bloco da Portaria), não cada
ocorrência de palavra. Isso evita três defeitos vistos em produção:
duplicar o mesmo ato (o título "Dispõe sobre exoneração" e o dispositivo
"Art. 1º Exonerar" viravam dois cartões), transformar menção em candidato
(CONSIDERANDOs citando "nomeação e exoneração") e mostrar trecho cortado no
meio da frase. Só o verbo dispositivo abre um ato; o substantivo não.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

RULESET_VERSION = "gazette-act-candidates/2.0.0"
EXCERPT_RADIUS = 400
# Um ato de pessoal cabe folgado nisto; o corte só age em bloco anômalo.
MAX_EXCERPT_CHARS = 2600

# Cabeçalho que abre um ato no Diário de Barreiras.
_HEADING_PATTERN = re.compile(
    r"PORTARIA\s+N\s*[°ºo.]*\s*[\d./-]{1,20}\s*,?\s*"
    r"DE\s+\d{1,2}\s+DE\s+[A-ZÀ-Üa-zà-ü]+\s+DE\s+\d{4}",
    re.IGNORECASE,
)

# Somente formas dispositivas: "Exonerar", "Nomeia". O substantivo
# ("exoneração") é menção e não abre ato.
_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "nomeacao-verbo-dispositivo",
        "nomeacao",
        re.compile(r"\bNOMEAR\b|\bNOMEIA\b|\bNOMEIO\b", re.IGNORECASE),
    ),
    (
        "exoneracao-verbo-dispositivo",
        "exoneracao",
        re.compile(r"\bEXONERAR\b|\bEXONERA\b|\bEXONERO\b", re.IGNORECASE),
    ),
)

# Ruído de assinatura digital que polui o começo de cada edição.
_SIGNATURE_NOISE = re.compile(
    r"(?:Certificado\s+Digital|Foxit\s+PDF\s+Reader|OU=|CN=|"
    r"Razão:\s*Eu\s+sou\s+o\s+autor|Localização:|"
    r"Assinado\s+(?:digitalmente|eletronicamente)).*",
    re.IGNORECASE,
)
_SIGNATURE_NAME = re.compile(r"^[^\n:]{3,80}:\d{8,20}\s*$", re.MULTILINE)


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


def clean_excerpt(raw: str) -> str:
    """Versão legível do trecho: sem assinatura digital, sem quebra solta.

    Determinística e versionada com o ruleset: quem tiver o texto canônico e
    os offsets reproduz exatamente este resultado.
    """
    without_noise = _SIGNATURE_NOISE.sub("", raw)
    without_noise = _SIGNATURE_NAME.sub("", without_noise)
    # Quebra simples dentro de frase vira espaço; parágrafo (linha em
    # branco) é preservado.
    joined = re.sub(r"(?<!\n)\n(?!\n)", " ", without_noise)
    joined = re.sub(r"[ \t]+", " ", joined)
    joined = re.sub(r"\n{3,}", "\n\n", joined)
    return joined.strip()


def _blocks(text: str) -> list[tuple[int, int]]:
    """Blocos de ato delimitados pelos cabeçalhos de Portaria."""
    headings = [match.start() for match in _HEADING_PATTERN.finditer(text)]
    if not headings:
        return []
    bounds = []
    for index, start in enumerate(headings):
        end = headings[index + 1] if index + 1 < len(headings) else len(text)
        bounds.append((start, end))
    return bounds


def find_candidates(text: str) -> tuple[ActCandidate, ...]:
    """Um candidato por ato (bloco de Portaria) e tipo, em ordem estável."""
    found: list[ActCandidate] = []
    blocks = _blocks(text)

    if blocks:
        for block_start, block_end in blocks:
            block = text[block_start:block_end]
            for rule_id, act_type, pattern in _RULES:
                match = pattern.search(block)
                if match is None:
                    continue
                excerpt_end = min(
                    block_end,
                    block_start + MAX_EXCERPT_CHARS,
                )
                found.append(
                    ActCandidate(
                        act_type=act_type,
                        rule_id=rule_id,
                        ruleset_version=RULESET_VERSION,
                        match_start=block_start + match.start(),
                        match_end=block_start + match.end(),
                        match_text=match.group(0),
                        excerpt_start=block_start,
                        excerpt_end=excerpt_end,
                        excerpt=clean_excerpt(text[block_start:excerpt_end]),
                    )
                )
    else:
        # Sem cabeçalho identificável: janela em torno do verbo, como antes.
        for rule_id, act_type, pattern in _RULES:
            match = pattern.search(text)
            if match is None:
                continue
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
                    excerpt=clean_excerpt(text[excerpt_start:excerpt_end]),
                )
            )

    found.sort(key=lambda candidate: (candidate.match_start, candidate.rule_id))
    return tuple(found)
