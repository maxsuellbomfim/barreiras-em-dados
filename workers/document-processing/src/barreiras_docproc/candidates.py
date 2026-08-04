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

# A chave de idempotência do job inclui esta versão. 2.3.0 força o acervo a
# passar novamente pela extração após a detecção de listas e várias cláusulas
# de cargo, evitando que resultados antigos mantenham só o primeiro nome.
RULESET_VERSION = "gazette-act-candidates/2.3.0"
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


# O texto embutido destes PDFs vem fragmentado: a mesma palavra se parte
# entre linhas ("ESTAD" + "O DA BAHIA", "MUN" + "ICÍPIO DE BA" +
# "RREIRAS"). Um fragmento é um final de linha em MAIÚSCULA cuja última
# "palavra" é curta demais para ser palavra e cuja linha seguinte começa
# também em maiúscula: nesse caso as duas se colam sem espaço.
_MAX_FRAGMENT_CHARS = 6
_UPPER_CHARS = "A-ZÁÀÂÃÉÈÊÍÏÓÔÕÖÚÜÇ"


def _is_fragment_boundary(previous: str, following: str) -> bool:
    """Só junta fragmento inequívoco — na dúvida, preserva a quebra.

    A reconstituição completa (inclusive espaço espúrio no meio da palavra)
    é feita pela leitura assistida; aqui vale a regra conservadora.
    """
    if not previous or not following:
        return False
    # Só continua palavra quem termina E começa em maiúscula.
    if not re.search(rf"[{_UPPER_CHARS}]$", previous):
        return False
    if not re.match(rf"^[{_UPPER_CHARS}]", following):
        return False

    # 1) Linha inteira curta e sem espaços: "ESTAD", "MUN", "PORT", "RE".
    if " " not in previous and len(previous) <= _MAX_FRAGMENT_CHARS:
        return True

    # 2) Cauda curta continuada por bloco maior sem espaços:
    # "ICÍPIO DE BA" + "RREIRAS".
    last_word = previous.split()[-1]
    return (
        len(last_word) <= 3
        and " " not in following
        and len(following) >= 4
    )


# Conectores legítimos em linha própria não são fragmentos ("e", "de").
_CONNECTOR_WORDS = frozenset(
    {"e", "de", "da", "do", "das", "dos", "em", "no", "na", "ao", "os", "as"}
)


def _is_lowercase_fragment(previous: str, following: str) -> bool:
    """Sílaba solta continuada em minúscula: "ca"+"rgo", "Sa"+"úde"."""
    if not previous or not following:
        return False
    if " " in previous or len(previous) > 3 or not previous.isalpha():
        return False
    if previous.casefold() in _CONNECTOR_WORDS:
        return False
    return following[:1].islower()


def defragment(text: str) -> str:
    """Reconstitui palavras partidas pela extração do PDF."""
    lines = text.split("\n")
    rebuilt: list[str] = []
    for line in lines:
        stripped = line.strip()
        if rebuilt and (
            _is_fragment_boundary(rebuilt[-1], stripped)
            or _is_lowercase_fragment(rebuilt[-1], stripped)
        ):
            rebuilt[-1] = rebuilt[-1] + stripped
            continue
        rebuilt.append(stripped)
    return "\n".join(rebuilt)


def clean_excerpt(raw: str) -> str:
    """Versão legível do trecho: sem assinatura digital, sem quebra solta.

    Determinística e versionada com o ruleset: quem tiver o texto canônico e
    os offsets reproduz exatamente este resultado.
    """
    without_noise = _SIGNATURE_NOISE.sub("", raw)
    without_noise = _SIGNATURE_NAME.sub("", without_noise)
    rejoined = defragment(without_noise)
    # Quebra simples dentro de frase vira espaço; parágrafo (linha em
    # branco) é preservado.
    joined = re.sub(r"(?<!\n)\n(?!\n)", " ", rejoined)
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
