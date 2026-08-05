"""Resumo por edição ancorado no texto oficial (ADR 0013).

A IA lista e traduz os itens publicados em cada edição do Diário; o código
só aceita um item se a citação-âncora que o acompanha ocorrer literalmente
no texto canônico da edição. Item sem âncora verificável é descartado —
nunca publicado. O resumo é rotulado como gerado por IA e é reversível como
qualquer publicação automática.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .assist import ContractViolationError, _parse_content
from .verify import value_in_excerpt

DIGEST_PROMPT_VERSION = "edition-digest/1.0.0"
DETERMINISTIC_DIGEST_VERSION = "edition-digest-deterministic/1.0.0"
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
    """Resume somente atos de pessoal reconhecidos pelas regras locais."""
    from .candidates import clean_excerpt, find_candidates
    from .fields import extract_act_fields

    items: list[DigestItem] = []
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
            "para o cargo de"
            if candidate.act_type == "nomeacao"
            else "do cargo de"
        )
        anchor = clean_excerpt(
            text[candidate.excerpt_start : candidate.excerpt_end]
        )[:240].strip()
        if len(anchor) < MIN_ANCHOR_CHARS:
            continue
        items.append(
            DigestItem(
                item_type=candidate.act_type,
                title=f"{kind}: {person}"[:MAX_TITLE_CHARS],
                summary=(
                    f"O ato registra a {kind.casefold()} de {person} "
                    f"{relation} {position}."
                )[:MAX_SUMMARY_CHARS],
                anchor=anchor,
            )
        )
    return items


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
        f"edition-digest:{sha256}:{DIGEST_PROMPT_VERSION}".encode()
    ).hexdigest()
