"""Resumo por edição ancorado no texto oficial (ADR 0013).

A IA lista e traduz os itens publicados em cada edição do Diário; o código
só aceita um item se a citação-âncora que o acompanha ocorrer literalmente
no texto canônico da edição. Item sem âncora verificável é descartado —
nunca publicado. O resumo é rotulado como gerado por IA e é reversível como
qualquer publicação automática.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .assist import ContractViolationError, _parse_content
from .verify import value_in_excerpt

DIGEST_PROMPT_VERSION = "edition-digest/1.0.0"
DETERMINISTIC_DIGEST_VERSION = "edition-digest-deterministic/1.2.0"
DIGEST_PIPELINE_VERSION = "edition-digest-pipeline/1.2.0"
ANCHOR_VERIFIER_VERSION = "edition-digest-anchor-check/1.0.0"
ITEM_TYPES = frozenset(
    {
        "nomeacao",
        "exoneracao",
        "contrato",
        "licitacao",
        "decreto",
        "portaria",
        "aviso",
        "outro",
    }
)
CHUNK_CHARS = 12000
# ponytail: teto de fatias por edição; cobertura parcial fica explícita no
# payload e no site, nunca silenciosa.
MAX_CHUNKS_PER_EDITION = 10
MAX_ITEMS_PER_CHUNK = 30
MIN_ANCHOR_CHARS = 20
MAX_TITLE_CHARS = 120
MAX_SUMMARY_CHARS = 400

_NUMBERED_HEADING = re.compile(
    r"(?im)^[ \t]*(?P<kind>DECRETO|LEI|PORTARIA)\s*N[^\d\n]{0,4}"
    r"(?P<number>\d[\d./-]*)(?P<suffix>[^\n]{0,140})$"
)
_PUBLIC_HEADING = re.compile(
    r"(?im)^[ \t]*(?P<heading>"
    r"AVISO(?:\s+DE\s+[^\n]{2,140})?|"
    r"EDITAL(?:\s+DE\s+[^\n]{2,140})?|"
    r"EXTRATO\s+(?:DA|DE|DO)\s+[^\n]{2,140}|"
    r"DECISÃO\s+SOBRE\s+IMPUGNAÇÃO\s+AO\s+EDITAL[^\n]{0,80}|"
    r"ERRATA(?:[^\n]{0,80})?"
    r")[ \t]*$"
)
_PERSONNEL_DEVICE = re.compile(
    r"\b(?:NOMEAR|NOMEIA|NOMEIO|EXONERAR|EXONERA|EXONERO)\b",
    re.IGNORECASE,
)
_DATE_LINE = re.compile(
    r"^(?:DE\s+)?\d{1,2}(?:/|\s+DE\s+)"
    r"(?:\d{1,2}/|[A-ZÀ-Üa-zà-ü]+\s+DE\s+)\d{4}\.?$",
    re.IGNORECASE,
)
_NON_DESCRIPTION_LINE = re.compile(
    r"^(?:LEI\s+\d|O(?:\(?A\)?)?\s+PREFEITO|"
    r"D\s*E\s*C\s*R\s*E\s*T\s*A|"
    r"DECRETA\s*:|ART(?:IGO|\.)\s*\d)",
    re.IGNORECASE,
)
_DESCRIPTION_ACTION = re.compile(
    r"^(?:ALTERA|ABRE|CONSTITUI|DISPÕE|INSTITUI|REGULAMENTA|CONVOCA|"
    r"TORNA\s+PÚBLICO|PRORROGA|DESIGNA|NOMEIA|EXONERA|AUTORIZA|DECLARA)\b",
    re.IGNORECASE,
)
_HEADING_DATE = re.compile(
    r"^(?:,)?DE(?:\d{1,2}/\d{1,2}/\d{4}|\d{1,2}DE[A-ZÀ-Ü]+DE\d{4})\.?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DigestItem:
    item_type: str
    title: str
    summary: str
    anchor: str


def chunk_text(text: str) -> list[str]:
    """Fatias de até CHUNK_CHARS respeitando parágrafos quando possível."""
    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= CHUNK_CHARS:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(paragraph) > CHUNK_CHARS:
            chunks.append(paragraph[:CHUNK_CHARS])
            paragraph = paragraph[CHUNK_CHARS:]
        current = paragraph
    if current.strip():
        chunks.append(current)
    return [chunk for chunk in chunks if chunk.strip()]


def build_digest_messages(chunk: str) -> list[dict[str, str]]:
    system = (
        "Você lê o Diário Oficial de Barreiras-BA e lista o que foi "
        "publicado, para qualquer cidadão entender. Responda SOMENTE um "
        "objeto JSON. Regra absoluta: nunca invente; cada item precisa de "
        "uma citação literal copiada exatamente do trecho."
    )
    user = (
        "Liste os atos publicados neste trecho do Diário Oficial. Para "
        "cada item devolva:\n"
        '- "tipo": um de nomeacao, exoneracao, contrato, licitacao, '
        "decreto, portaria, aviso, outro;\n"
        '- "titulo": título curto e factual;\n'
        '- "resumo": 1 a 2 frases simples e neutras explicando o ato;\n'
        '- "trecho": citação LITERAL de 20 a 120 caracteres copiada '
        "exatamente do texto abaixo, que identifique o item.\n"
        'Responda {"items": [...]} — lista vazia se não houver atos.\n'
        f"Texto oficial:\n---\n{chunk}\n---"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def parse_digest_items(
    content: str,
    chunk: str,
) -> tuple[list[DigestItem], int]:
    """Itens com âncora verificada e a contagem dos descartados."""
    parsed = _parse_content(content)
    raw_items = parsed.get("items")
    if not isinstance(raw_items, list):
        raise ContractViolationError('O resumo deve conter a lista "items".')

    accepted: list[DigestItem] = []
    dropped = 0
    for raw in raw_items[:MAX_ITEMS_PER_CHUNK]:
        item = _validated_item(raw, chunk)
        if item is None:
            dropped += 1
            continue
        accepted.append(item)
    dropped += max(0, len(raw_items) - MAX_ITEMS_PER_CHUNK)
    return accepted, dropped


def deterministic_digest_items(text: str) -> list[DigestItem]:
    """Resume atos com cabeçalho oficial reconhecido por regras locais."""
    from .candidates import clean_excerpt, find_candidates
    from .fields import extract_act_fields

    positioned_items: list[tuple[int, DigestItem]] = []
    for candidate in find_candidates(text):
        fields = extract_act_fields(
            text,
            match_start=candidate.match_start,
            match_end=candidate.match_end,
        )
        person = fields.person_name.value
        position = fields.position.value
        if not person or not position:
            continue
        kind = "Nomeação" if candidate.act_type == "nomeacao" else "Exoneração"
        relation = (
            "para o cargo de" if candidate.act_type == "nomeacao" else "do cargo de"
        )
        anchor = clean_excerpt(text[candidate.excerpt_start : candidate.excerpt_end])[
            :240
        ].strip()
        if len(anchor) < MIN_ANCHOR_CHARS:
            continue
        positioned_items.append(
            (
                candidate.excerpt_start,
                DigestItem(
                    item_type=candidate.act_type,
                    title=f"{kind}: {person}"[:MAX_TITLE_CHARS],
                    summary=(
                        f"O ato registra a {kind.casefold()} de {person} "
                        f"{relation} {position}."
                    )[:MAX_SUMMARY_CHARS],
                    anchor=anchor,
                ),
            )
        )
    headings: list[tuple[int, int, str, str]] = []
    for match in _NUMBERED_HEADING.finditer(text):
        if not _is_numbered_heading(match, text):
            continue
        kind = match.group("kind").casefold()
        number = match.group("number")
        item_type = kind if kind in {"decreto", "portaria"} else "outro"
        headings.append(
            (
                match.start(),
                match.end(),
                item_type,
                f"{kind.capitalize()} nº {number}",
            )
        )
    for match in _PUBLIC_HEADING.finditer(text):
        heading = " ".join(match.group("heading").split())
        if " e/ou " in heading.casefold():
            continue
        folded = heading.casefold()
        if "contrato" in folded or "termo aditivo" in folded:
            item_type = "contrato"
        elif folded.startswith("extrato da portaria"):
            item_type = "portaria"
        elif any(
            marker in folded
            for marker in (
                "licita",
                "pregão",
                "impugnação",
                "dispensa",
                "registro de preços",
                "ata de regist",
            )
        ):
            item_type = "licitacao"
        elif folded.startswith("aviso") or folded.startswith("edital"):
            item_type = "aviso"
        else:
            item_type = "outro"
        headings.append(
            (
                match.start(),
                match.end(),
                item_type,
                heading[:1].upper() + heading[1:].lower(),
            )
        )

    headings.sort(key=lambda entry: entry[0])
    for index, (start, heading_end, item_type, title) in enumerate(headings):
        end = headings[index + 1][0] if index + 1 < len(headings) else len(text)
        segment = text[start:end]
        if item_type == "outro" and title.casefold().startswith("errata"):
            if re.search(r"\b(?:PREGÃO|LICITAÇÃO)\b", segment, re.IGNORECASE):
                item_type = "licitacao"
        if item_type == "portaria" and _PERSONNEL_DEVICE.search(segment):
            continue
        anchor = segment[:240].strip()
        if len(anchor) < MIN_ANCHOR_CHARS:
            continue
        description = _first_official_description(text[heading_end:end])
        summary = (
            f"O texto oficial informa: {description}"
            if description
            else f"A edição publica {title}."
        )
        positioned_items.append(
            (
                start,
                DigestItem(
                    item_type=item_type,
                    title=title[:MAX_TITLE_CHARS],
                    summary=summary[:MAX_SUMMARY_CHARS],
                    anchor=anchor,
                ),
            )
        )
    positioned_items.sort(key=lambda entry: entry[0])
    return _deduplicate_items([item for _position, item in positioned_items])


def _is_numbered_heading(match: re.Match[str], text: str) -> bool:
    """Rejeita citações legais que apenas começam por Decreto/Portaria."""
    suffix = " ".join(match.group("suffix").split()).strip()
    compact_suffix = re.sub(r"\s+", "", suffix)
    action_suffix = suffix.lstrip(" ,.;:-")
    if suffix.strip(" ,.;:-"):
        return bool(
            _DESCRIPTION_ACTION.match(action_suffix)
            or _HEADING_DATE.match(compact_suffix)
        )

    following_lines = [
        " ".join(line.split()).strip()
        for line in text[match.end() : match.end() + 600].splitlines()
        if line.strip()
    ][:10]
    if not following_lines:
        return False
    for line in following_lines:
        if re.match(
            r"^(?:DECRETO|LEI|PORTARIA)\s*N[^\d\n]{0,4}\d",
            line,
            re.IGNORECASE,
        ):
            return False
        if _DESCRIPTION_ACTION.match(line):
            return True
    return False


def _deduplicate_items(items: list[DigestItem]) -> list[DigestItem]:
    """Remove a mesma publicação repetida no PDF sem fundir atos distintos."""
    unique: list[DigestItem] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        key = (
            item.item_type,
            " ".join(item.title.casefold().split()),
            " ".join(item.anchor.casefold().split()),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _first_official_description(body: str) -> str | None:
    """Seleciona uma ementa literal próxima sem interpretar números."""
    fallback: str | None = None
    for raw_line in body.splitlines():
        line = " ".join(raw_line.split()).strip()
        if not line or _DATE_LINE.match(line) or _NON_DESCRIPTION_LINE.match(line):
            continue
        if line.casefold().startswith(("prefeitura municipal", "estado da bahia")):
            continue
        if _DESCRIPTION_ACTION.match(line):
            return line[:300]
        if fallback is None:
            fallback = line[:300]
    return fallback


def _validated_item(raw: Any, chunk: str) -> DigestItem | None:
    if not isinstance(raw, dict):
        return None
    title = raw.get("titulo")
    summary = raw.get("resumo")
    anchor = raw.get("trecho")
    if not (
        isinstance(title, str)
        and title.strip()
        and isinstance(summary, str)
        and summary.strip()
        and isinstance(anchor, str)
        and len(anchor.strip()) >= MIN_ANCHOR_CHARS
    ):
        return None
    if not value_in_excerpt(anchor, chunk):
        return None
    item_type = raw.get("tipo")
    if not isinstance(item_type, str) or item_type not in ITEM_TYPES:
        item_type = "outro"
    return DigestItem(
        item_type=item_type,
        title=title.strip()[:MAX_TITLE_CHARS],
        summary=summary.strip()[:MAX_SUMMARY_CHARS],
        anchor=anchor.strip(),
    )


def digest_payload(
    *,
    edition: int,
    year: int,
    items: list[DigestItem],
    chunks_total: int,
    chunks_failed: int,
    items_dropped: int,
    partial: bool,
    providers: list[str],
    prompt_version: str = DIGEST_PROMPT_VERSION,
) -> dict[str, Any]:
    return {
        "schema_name": "edition-digest",
        "schema_version": "1.0.0",
        "prompt_version": prompt_version,
        "edition": edition,
        "year": year,
        "items": [
            {
                "tipo": item.item_type,
                "titulo": item.title,
                "resumo": item.summary,
                "trecho": item.anchor,
            }
            for item in items
        ],
        "stats": {
            "chunks_total": chunks_total,
            "chunks_failed": chunks_failed,
            "items_dropped": items_dropped,
            "partial": partial,
            "providers": sorted(set(providers)),
        },
    }


def job_idempotency_key(sha256: str) -> str:
    import hashlib

    return hashlib.sha256(
        f"edition-digest:{sha256}:{DIGEST_PIPELINE_VERSION}".encode()
    ).hexdigest()
