"""Sugestão assistida de aliases de representantes.

Este módulo não identifica pessoas por conta própria. Ele prepara um conjunto
fechado de candidatos vindos de fontes oficiais e pede à cascata uma sugestão
estruturada. A saída sempre nasce como ``pending``; somente uma revisão humana
autorizada pode transformá-la em alias aceito.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

from .assist import _parse_content, run_cascade_content

ALIAS_ASSIST_PROMPT_VERSION = "representative-alias-assist/1.1.0"
ALIAS_ASSIST_VALIDATOR_VERSION = "representative-alias-literal-safe/1.0.0"
MAX_ALIAS_NAME = 200
MAX_RATIONALE = 800
MAX_EVIDENCE_ITEMS = 6

_STOPWORDS = frozenset(
    {
        "A",
        "AS",
        "DA",
        "DAS",
        "DE",
        "DO",
        "DOS",
        "E",
    }
)


def normalize_name(value: str) -> str:
    """Normaliza somente para triagem de candidatos, nunca para publicar."""

    decomposed = unicodedata.normalize("NFD", value)
    without_marks = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return re.sub(r"[^A-Z0-9]+", " ", without_marks.upper()).strip()


def candidate_tokens(value: str) -> frozenset[str]:
    return frozenset(
        token
        for token in normalize_name(value).split()
        if len(token) >= 3 and token not in _STOPWORDS
    )


def _name_parts(value: str, *, strip_parenthetical: bool = False) -> tuple[str, ...]:
    """Retorna partes de nome para triagem, sem alterar o texto publicado.

    Conteúdo entre parênteses costuma ser nome de urna, apelido ou partido.
    Ele é mantido como sinal separado; nunca é descartado do registro de
    origem nem usado sozinho para aceitar um vínculo.
    """

    text = value
    if strip_parenthetical:
        text = re.sub(r"\([^)]*\)", " ", text)
    return tuple(
        token
        for token in normalize_name(text).split()
        if len(token) >= 2 and token not in _STOPWORDS
    )


def _parenthetical_parts(value: str) -> tuple[str, ...]:
    return tuple(
        normalized
        for normalized in (
            normalize_name(match)
            for match in re.findall(r"\(([^)]*)\)", value)
        )
        if normalized
    )


def name_match_signals(
    observed_name: str,
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    """Calcula sinais explicáveis para ordenar uma hipótese de alias.

    A função é deliberadamente fechada no conjunto de candidatos oficiais. O
    sinal ``first_and_surname`` é apenas uma boa pista (primeiro nome e pelo
    menos um sobrenome em comum), não uma prova de identidade.
    """

    canonical = str(candidate.get("canonical_name") or "").strip()
    observed_normalized = normalize_name(observed_name)
    canonical_normalized = normalize_name(canonical)
    observed_base = normalize_name(
        re.sub(r"\([^)]*\)", " ", observed_name)
    )
    canonical_base = normalize_name(
        re.sub(r"\([^)]*\)", " ", canonical)
    )
    observed_parts = _name_parts(observed_name, strip_parenthetical=True)
    canonical_parts = _name_parts(canonical, strip_parenthetical=True)
    observed_aliases = set(_parenthetical_parts(observed_name))
    candidate_aliases: set[str] = set()
    for key in ("ballot_name", "alias_text", "nickname"):
        value = str(candidate.get(key) or "").strip()
        if value:
            candidate_aliases.add(normalize_name(value))

    first_and_surname = False
    surname_overlap: frozenset[str] = frozenset()
    if len(observed_parts) >= 2 and len(canonical_parts) >= 2:
        surname_overlap = frozenset(observed_parts[1:]) & frozenset(
            canonical_parts[1:]
        )
        first_and_surname = (
            observed_parts[0] == canonical_parts[0]
            and bool(surname_overlap)
        )
    parenthetical_match = bool(observed_aliases & candidate_aliases)
    exact_normalized = bool(observed_normalized) and (
        observed_normalized == canonical_normalized
    )
    base_normalized = bool(observed_base) and (observed_base == canonical_base)
    token_overlap = len(candidate_tokens(observed_name) & candidate_tokens(canonical))

    # Pontuação é somente para ordenar a lista fechada enviada à revisão.
    # Distâncias fortes ficam bem acima do simples número de tokens comuns.
    if exact_normalized:
        score = 100
    elif base_normalized:
        score = 96
    elif parenthetical_match:
        score = 90
    elif first_and_surname:
        score = 72
    else:
        score = min(token_overlap, 5)
    score += min(len(surname_overlap), 2)
    return {
        "score": score,
        "exact_normalized": exact_normalized,
        "base_normalized": base_normalized,
        "parenthetical_match": parenthetical_match,
        "first_and_surname": first_and_surname,
        "surname_overlap": tuple(sorted(surname_overlap)),
        "token_overlap": token_overlap,
    }


def _variant_kind(observed_name: str, canonical_name: str) -> str:
    if observed_name.strip() == canonical_name.strip():
        return "other"
    observed_casefold = " ".join(observed_name.split()).casefold()
    canonical_casefold = " ".join(canonical_name.split()).casefold()
    return (
        "case_variant"
        if observed_casefold == canonical_casefold
        else "spacing_variant"
    )


def classify_alias_deterministically(
    observed_name: str,
    candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Produz uma hipótese local, sempre adequada a ``status=pending``.

    A regra aceita como *match de revisão* somente uma correspondência exata,
    uma correspondência do nome-base sem parênteses ou um único candidato com
    primeiro nome e sobrenome em comum. O último caso recebe confiança menor e
    rationale explícito. Empates permanecem ambíguos e sem ID.
    """

    if not observed_name.strip() or not candidates:
        return {
            "decision": "ambiguous",
            "candidate_external_id": None,
            "alias_kind": "other",
            "confidence": 0.0,
            "rationale": "Não há nome observado ou candidatos oficiais suficientes.",
            "evidence": ["triagem local sem decisão de identidade"],
            "validator_version": ALIAS_ASSIST_VALIDATOR_VERSION,
        }

    scored = [
        (name_match_signals(observed_name, candidate), candidate)
        for candidate in candidates
    ]
    scored.sort(
        key=lambda pair: (
            int(pair[0]["score"]),
            str(pair[1].get("representative_external_id") or ""),
        ),
        reverse=True,
    )
    top_signals, top_candidate = scored[0]
    top_score = int(top_signals["score"])
    strong = [
        pair
        for pair in scored
        if pair[0]["exact_normalized"]
        or pair[0]["base_normalized"]
        or pair[0]["parenthetical_match"]
        or pair[0]["first_and_surname"]
    ]
    tied_ids = {
        str(candidate.get("representative_external_id") or "")
        for signals, candidate in strong
        if int(signals["score"]) == top_score
    }
    if not strong or not top_candidate.get("representative_external_id"):
        return {
            "decision": "ambiguous",
            "candidate_external_id": None,
            "alias_kind": "other",
            "confidence": 0.0,
            "rationale": (
                "A triagem local encontrou apenas sobreposição parcial de palavras; "
                "a identidade permanece sem evidência suficiente."
            ),
            "evidence": [
                f"maior sobreposição de tokens: {top_signals['token_overlap']}"
            ],
            "validator_version": ALIAS_ASSIST_VALIDATOR_VERSION,
        }
    if len(tied_ids) != 1:
        return {
            "decision": "ambiguous",
            "candidate_external_id": None,
            "alias_kind": "other",
            "confidence": 0.0,
            "rationale": (
                "Mais de um candidato oficial recebeu a mesma pontuação; "
                "a hipótese exige revisão humana."
            ),
            "evidence": [
                "empate entre candidatos do conjunto oficial",
                f"pontuação local: {top_score}",
            ],
            "validator_version": ALIAS_ASSIST_VALIDATOR_VERSION,
        }

    if top_signals["exact_normalized"]:
        confidence = 0.96
        alias_kind = _variant_kind(
            observed_name,
            str(top_candidate.get("canonical_name") or ""),
        )
        rationale = "Nome normalizado coincide integralmente com o candidato oficial."
        evidence = ["igualdade após normalização de caixa, acentos e pontuação"]
    elif top_signals["base_normalized"]:
        confidence = 0.9
        alias_kind = "nickname" if _parenthetical_parts(observed_name) else "other"
        rationale = (
            "Nome-base coincide; conteúdo entre parênteses foi tratado apenas como "
            "possível apelido ou nome de urna."
        )
        evidence = ["nome-base igual após separar conteúdo entre parênteses"]
    elif top_signals["parenthetical_match"]:
        confidence = 0.82
        alias_kind = "nickname"
        rationale = (
            "O conteúdo entre parênteses coincide com alias informado no registro "
            "oficial do candidato; a confirmação continua humana."
        )
        evidence = ["alias entre parênteses coincide com candidato permitido"]
    else:
        confidence = 0.72
        alias_kind = "ballot_name"
        surnames = ", ".join(top_signals["surname_overlap"])
        rationale = (
            "Primeiro nome e pelo menos um sobrenome coincidem; isso é uma pista "
            "forte, mas não prova que se trata da mesma pessoa."
        )
        evidence = [
            "primeiro nome coincidente",
            f"sobrenome(s) coincidente(s): {surnames}",
        ]
    return {
        "decision": "match",
        "candidate_external_id": str(top_candidate["representative_external_id"]),
        "alias_kind": alias_kind,
        "confidence": confidence,
        "rationale": rationale,
        "evidence": evidence,
        "validator_version": ALIAS_ASSIST_VALIDATOR_VERSION,
    }


def rank_candidates(
    observed_name: str,
    candidates: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Ordena candidatos por tokens compartilhados sem eliminar nenhum.

    O ranking serve apenas para reduzir o texto enviado à IA. Mesmo quando a
    pontuação é alta, a sugestão continua pendente e nunca vira vínculo
    automaticamente.
    """

    observed_tokens = candidate_tokens(observed_name)
    scored: list[tuple[int, int, Mapping[str, Any]]] = []
    for index, candidate in enumerate(candidates):
        name = str(candidate.get("canonical_name") or "")
        signals = name_match_signals(observed_name, candidate)
        # Inclui o overlap legado para preservar uma ordem útil quando nenhum
        # sinal forte existe; o primeiro componente é sempre determinístico.
        overlap = len(observed_tokens & candidate_tokens(name))
        scored.append((max(int(signals["score"]), overlap), -index, candidate))
    scored.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
    return tuple(dict(candidate) for _score, _order, candidate in scored)


def build_alias_messages(
    observed_name: str,
    candidates: Sequence[Mapping[str, Any]],
    *,
    source_context: str,
    historical_candidates: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, str]]:
    """Constrói prompt fechado: a IA só pode escolher IDs fornecidos."""

    if not observed_name.strip():
        raise ValueError("observed_name vazio")
    if not candidates:
        raise ValueError("candidates vazio")
    candidate_json = "[" + ",".join(
        "{" + ",".join(
            f'"{key}": {json.dumps(str(value), ensure_ascii=False)}'
            for key, value in (
                (
                    "representative_external_id",
                    candidate.get("representative_external_id"),
                ),
                ("canonical_name", candidate.get("canonical_name")),
                ("party", candidate.get("party") or ""),
                ("candidate_id", candidate.get("candidate_id") or ""),
            )
        ) + "}"
        for candidate in rank_candidates(observed_name, candidates)
    ) + "]"
    historical_json = "[" + ",".join(
        "{" + ",".join(
            f'"{key}": {json.dumps(str(value), ensure_ascii=False)}'
            for key, value in (
                ("election_year", item.get("election_year") or ""),
                ("candidate_id", item.get("candidate_id") or ""),
                ("canonical_name", item.get("canonical_name") or ""),
                ("ballot_name", item.get("ballot_name") or ""),
                ("party", item.get("party") or ""),
                ("office", item.get("office") or ""),
            )
        ) + "}"
        for item in historical_candidates
    ) + "]"
    system = (
        "Você é um assistente de auditoria de dados públicos de Barreiras-BA. "
        "Sugira aliases somente para revisão humana. Nunca declare que duas "
        "grafias são a mesma pessoa por conhecimento externo. Responda apenas "
        "JSON válido. Se houver ambiguidade, use ambiguous ou no_match. "
        "A ausência na lista eleitoral atual não prova no_match: use ambiguous "
        "quando a autoria for histórica ou faltar evidência. Use no_match somente "
        "quando houver evidência positiva de conflito. "
        "candidate_external_id deve ser exatamente um ID da lista ou null."
    )
    user = (
        "Compare o nome de autoria publicado pela Câmara com os candidatos "
        "oficiais fornecidos. A decisão não publica nada e não altera a fonte. "
        "Considere nome de urna, apelido e caixa alta como hipóteses, não como "
        "prova. O rationale deve citar somente sinais observáveis no contexto.\n"
        'Formato: {"decision":"match|ambiguous|no_match", '
        '"candidate_external_id":"ID da lista" ou null, '
        '"alias_kind":"ballot_name|nickname|case_variant|spacing_variant|other", '
        '"confidence":0.0, "rationale":"...", "evidence":["..."]}\n'
        f"Nome publicado: {observed_name[:MAX_ALIAS_NAME]}\n"
        f"Contexto oficial: {source_context[:1200]}\n"
        f"Candidaturas históricas informativas (sem IDs aceitos): {historical_json}\n"
        f"Candidatos permitidos: {candidate_json}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def parse_alias_response(
    content: str,
    *,
    allowed_external_ids: set[str],
) -> dict[str, Any]:
    """Valida a resposta sem aceitar IDs ou certezas inventados pela IA."""

    parsed = _parse_content(content)
    decision = parsed.get("decision")
    if decision not in {"match", "ambiguous", "no_match"}:
        raise ValueError("decision fora do contrato")
    external_id = parsed.get("candidate_external_id")
    if external_id is not None and (
        not isinstance(external_id, str)
        or external_id not in allowed_external_ids
    ):
        raise ValueError("candidate_external_id não pertence aos candidatos")
    if decision == "no_match" and external_id is not None:
        raise ValueError("no_match não pode indicar candidato")
    alias_kind = parsed.get("alias_kind")
    allowed_alias_kinds = {
        "ballot_name",
        "nickname",
        "case_variant",
        "spacing_variant",
        "other",
    }
    # Modelos podem devolver uma taxonomia sinônima (por exemplo, "official_name").
    # Esse campo não decide a identidade; conservamos a sugestão e rebaixamos
    # somente a classificação para ``other``. IDs fora da lista continuam sendo
    # rejeitados acima, preservando o mundo fechado.
    if alias_kind not in allowed_alias_kinds:
        alias_kind = "other"
    confidence = parsed.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError("confidence deve ser número")
    if not 0 <= float(confidence) <= 1:
        raise ValueError("confidence fora do intervalo")
    rationale = parsed.get("rationale")
    if (
        not isinstance(rationale, str)
        or not rationale.strip()
        or len(rationale) > MAX_RATIONALE
    ):
        raise ValueError("rationale inválido")
    evidence = parsed.get("evidence")
    if not isinstance(evidence, list) or len(evidence) > MAX_EVIDENCE_ITEMS:
        raise ValueError("evidence inválida")
    if any(not isinstance(item, str) or not item.strip() for item in evidence):
        raise ValueError("evidence deve conter textos")
    if decision == "match" and external_id is None:
        raise ValueError("match precisa de candidato")
    return {
        "decision": decision,
        "candidate_external_id": external_id,
        "alias_kind": alias_kind,
        "confidence": round(float(confidence), 3),
        "rationale": rationale.strip(),
        "evidence": [item.strip() for item in evidence],
        "validator_version": ALIAS_ASSIST_VALIDATOR_VERSION,
    }


def run_alias_assistance(
    caller,
    environment: Mapping[str, str],
    observed_name: str,
    candidates: Sequence[Mapping[str, Any]],
    *,
    source_context: str,
    historical_candidates: Sequence[Mapping[str, Any]] = (),
    logger,
    attempts=None,
) -> tuple[str, str, dict[str, Any], str]:
    """Executa a cascata e retorna uma sugestão ainda pendente."""

    messages = build_alias_messages(
        observed_name,
        candidates,
        source_context=source_context,
        historical_candidates=historical_candidates,
    )
    provider, model, content = run_cascade_content(
        caller,
        environment,
        messages,
        logger,
        attempts,
    )
    allowed = {
        str(candidate["representative_external_id"])
        for candidate in candidates
        if candidate.get("representative_external_id")
    }
    try:
        result = parse_alias_response(content, allowed_external_ids=allowed)
    except ValueError as error:
        # A resposta continua preservada para auditoria, mas nunca pode
        # interromper a janela inteira nem carregar um ID histórico/inventado.
        # Quarentenamos como ambígua e sem candidato: a revisão humana verá o
        # bruto, mas a função de aceite não poderá criar vínculo.
        logger.warning(
            "representative_alias_response_quarantined: %s",
            str(error)[:240],
        )
        result = {
            "decision": "ambiguous",
            "candidate_external_id": None,
            "alias_kind": "other",
            "confidence": 0.0,
            "rationale": (
                "Resposta da IA retida para revisão: não passou pela validação "
                "de identidade fechada. Consulte a resposta bruta e as fontes."
            ),
            "evidence": [],
            "validator_version": ALIAS_ASSIST_VALIDATOR_VERSION,
        }
    return provider, model, result, content
