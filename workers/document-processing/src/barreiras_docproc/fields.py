"""Extração determinística de campos de atos de pessoal.

Regras fixas e versionadas sobre o texto canônico, aplicadas ao redor do
verbo do ato. Cada campo tem estado explícito: `matched` com a regra que o
encontrou ou `not_found` — nunca um palpite. Nenhum LLM participa e nenhuma
probabilidade é inventada.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

FIELDSET_VERSION = "gazette-act-fields/1.5.0"
# O ato inteiro cabe na janela: os diários quebram a frase em várias linhas
# e o nome costuma vir depois de apostos ("a servidora ...", "o (a) ...").
FIELD_WINDOW = 1200
HEADING_WINDOW = 600

# Palavras institucionais que nunca são nome de pessoa (comparação sem
# acentos). Conectores DA/DE/DO/E não contam como palavra significativa.
_PERSON_STOPWORDS = frozenset(
    {
        "ESTADO", "BAHIA", "MUNICIPIO", "BARREIRAS", "PREFEITO", "PREFEITA",
        "PREFEITURA", "MUNICIPAL", "SECRETARIA", "SECRETARIO", "PORTARIA",
        "DECRETO", "GABINETE", "RESOLVE", "CONSIDERANDO", "DIARIO", "OFICIAL",
        "LEI", "ART", "ARTIGO", "PARAGRAFO", "UNICO", "PROVA", "OBJETIVA",
        "ADMINISTRACAO", "DIRETA", "AUTARQUIAS", "FUNDACOES", "PUBLICAS",
        "PUBLICA", "PUBLICO", "SERVIDOR", "SERVIDORA", "SERVIDORES", "CIVIS",
        "CARGO", "COMISSAO", "SIMBOLO", "FUNCAO", "CONCURSO", "EDITAL",
        "CN", "PDF", "READER", "FOXIT", "VERSAO", "CERTIFICADO", "DIGITAL",
        "VIDEOCONFERENCIA", "SYNGULARID", "MULTIPLA", "AC", "PF", "CPF",
        # Cabeçalhos e siglas que viraram "pessoa" em produção.
        "JUSTIFICATIVA", "EXTRATO", "TERMO", "ADITIVO", "CONTRATO",
        "CONTRATACAO", "CONTRATACOES", "NAO", "SIM",
        "HOMOLOGACAO", "RATIFICACAO", "INEXIGIBILIDADE", "DISPENSA",
        "RESULTADO", "ANEXO", "TITULAR", "SUPLENTE", "OBJETO", "VALOR",
        "SMS", "SEMED", "SEMMAS", "SEINFRA", "SEMAS", "SEFAZ", "SESAU",
    }
)
_CONNECTORS = frozenset({"DA", "DE", "DO", "DAS", "DOS", "E"})

_MONTHS = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}

_UPPER = "A-ZÁÀÂÃÉÈÊÍÏÓÔÕÖÚÜÇ"
# Travessão e apóstrofo tipográfico ocorrem nos textos reais dos diários.
_PERSON_PATTERN = re.compile(
    rf"^[\s,:–-]*(?:a\s+pedido\s*,?\s*)?"  # noqa: RUF001
    rf"((?:[{_UPPER}][{_UPPER}'’-]+)"  # noqa: RUF001
    rf"(?:\s+(?:D[AEO]S?\s+|E\s+)?[{_UPPER}][{_UPPER}'’-]+)+)"  # noqa: RUF001
)
# Fallback 1.2.0: nos textos reais há preposições e apostos entre o verbo e
# o nome ("Nomear a candidata habilitada ..., FULANA DE TAL, ..."), então o
# nome é buscado em qualquer ponto da janela, filtrado por stoplist.
_PERSON_ANYWHERE_PATTERN = re.compile(
    rf"\b((?:[{_UPPER}][{_UPPER}'’-]+)"  # noqa: RUF001
    rf"(?:\s+(?:D[AEO]S?\s+|E\s+)?[{_UPPER}][{_UPPER}'’-]+)+)"  # noqa: RUF001
)
# 1.3.0: os diários escrevem tanto "MARIA DAS DORES" quanto "Maria Amélia
# Gonçalves Mariano". Uma palavra de nome começa em maiúscula; conectores
# minúsculos (da, de, dos, e) ligam as partes.
_NAME_WORD = rf"[{_UPPER}][{_UPPER}a-zà-üç'’-]+"  # noqa: RUF001
_NAME = (
    rf"{_NAME_WORD}"
    rf"(?:\s+(?:d[aeo]s?|e|D[AEO]S?|E)\s+{_NAME_WORD}|\s+{_NAME_WORD})+"
)
# Marcador explícito de pessoa: a forma que aparece nos atos reais
# ("a servidora X", "o (a) servidor (a) Y", "a candidata Z").
# A flag de caixa vale só para o marcador: o nome PRECISA começar em
# maiúscula, senão "o servidor conforme documento" viraria nome.
_PERSON_MARKED_PATTERN = re.compile(
    r"(?i:servidor|servidora|candidato|candidata|senhor|senhora|"
    r"sr|sra|srª)\s*\(?\s*(?i:a)?\s*\)?\s*[,:]?\s+"
    rf"({_NAME})",
)
_NUMBERED_PERSON_PATTERN = re.compile(
    rf"(?:^|[;\n])\s*\(?\d{{1,3}}[.)-]\)?\s+({_NAME})"
    rf"(?=\s*,?\s+(?:para|no|do)\s+o?\s*cargo\b)",
    re.IGNORECASE,
)
_PERSON_BEFORE_POSITION_PATTERN = re.compile(
    rf"(?:^\s*|\b(?:NOMEAR|NOMEIA|NOMEIO|EXONERAR|EXONERA|EXONERO)\s+"
    rf"|\be\s+|[;,]\s*)({_NAME})"
    rf"(?=\s*,?\s+(?:para|no|do)\s+o?\s*cargo\b)",
    re.IGNORECASE,
)
# O ponto de abreviação ("Escola Municipal Dr. Fulano") não encerra o
# cargo; só o ponto que fecha a frase encerra.
_POSITION_PATTERN = re.compile(
    r"(?:para|d[oa]|n[oa])\s+o?\s*cargo(?:\s+em\s+comiss[ãa]o)?\s+de\s+"
    r"([^,\n]{3,160}?)"
    r"(?=,|\s+s[íi]mbolo|\s+d[ao]\s+Secretaria|\s+matr[íi]cula"
    r"|(?<!\bDr)(?<!\bDra)(?<!\bSr)(?<!\bSra)(?<!\bProf)(?<!\bProfa)\.|\n)",
    re.IGNORECASE,
)
# "do cargo de provimento efetivo de Professor V" → o cargo é o que vem
# depois da fórmula de provimento.
_PROVISION_PREFIX = re.compile(
    r"^provimento\s+(?:efetivo|em\s+comiss[ãa]o)\s+d[eo]\s+",
    re.IGNORECASE,
)
_SYMBOL_PATTERN = re.compile(
    r"s[íi]mbolo\s+([A-Z]{1,5}\s*-\s*\d+)",
    re.IGNORECASE,
)
_ORGANIZATION_PATTERN = re.compile(
    r"(Secretaria(?:\s+Municipal)?\s+d[eao]\s+[^,.\n\d]{3,90})",
    re.IGNORECASE,
)
# Sem este corte a captura invadia o ato seguinte do diário
# ("... e Trabalho BARREIRAS - BAHIA CONVOCAÇÃO 003/2026 ...").
_ORGANIZATION_STOP = re.compile(
    r"\s+(?:EXTRATO|PORTARIA|CONVOCA\w*|EDITAL|DECRETO|AVISO|RESOLVE|"
    r"BARREIRAS|BAHIA|ESTADO|MUNIC[ÍI]PIO|Lei)\b.*",
    re.IGNORECASE,
)
_HEADING_PATTERN = re.compile(
    r"PORTARIA\s+N\s*[°ºo.]*\s*([\d./-]{1,20})\s*,?\s*"
    r"DE\s+(\d{1,2})\s+DE\s+([A-ZÀ-Üa-zà-ü]+)\s+DE\s+(\d{4})",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FieldExtraction:
    value: str | None
    status: str
    rule_id: str


@dataclass(frozen=True)
class ActFields:
    fieldset_version: str
    person_name: FieldExtraction
    person_names: tuple[FieldExtraction, ...]
    position: FieldExtraction
    position_symbol: FieldExtraction
    organization: FieldExtraction
    act_number: FieldExtraction
    act_date: FieldExtraction


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" ,;:–-")  # noqa: RUF001


def _matched(rule_id: str, value: str) -> FieldExtraction:
    return FieldExtraction(
        value=_normalize(value),
        status="matched",
        rule_id=rule_id,
    )


def _not_found(rule_id: str) -> FieldExtraction:
    return FieldExtraction(value=None, status="not_found", rule_id=rule_id)


def _strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    return "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )


def _heading_fields(
    heading_window: str,
) -> tuple[FieldExtraction, FieldExtraction]:
    """Último cabeçalho de Portaria antes do verbo: número e data do ato."""
    matches = list(_HEADING_PATTERN.finditer(heading_window))
    if not matches:
        return (
            _not_found("act-number-portaria-heading"),
            _not_found("act-date-portaria-heading"),
        )

    heading = matches[-1]
    number = _matched("act-number-portaria-heading", heading.group(1))
    month = _MONTHS.get(_strip_accents(heading.group(3)).lower())
    if month is None:
        return number, _not_found("act-date-portaria-heading")
    try:
        act_date = date(int(heading.group(4)), month, int(heading.group(2)))
    except ValueError:
        return number, _not_found("act-date-portaria-heading")
    return number, _matched(
        "act-date-portaria-heading",
        act_date.isoformat(),
    )


def _flatten(value: str) -> str:
    """Junta as quebras de linha do PDF para a frase voltar a ser uma só."""
    return re.sub(r"\s+", " ", value)


def _plausible_person(candidate: str) -> bool:
    words = [
        _strip_accents(word.strip("'’-")).upper()  # noqa: RUF001
        for word in candidate.split()
    ]
    significant = [word for word in words if word not in _CONNECTORS]
    if len(significant) < 2:
        return False
    return not any(word in _PERSON_STOPWORDS for word in significant)


def _person_in_window(window: str) -> str | None:
    """Primeiro nome próprio plausível na janela, ignorando institucionais."""
    for match in _PERSON_ANYWHERE_PATTERN.finditer(window):
        tail = window[match.end() : match.end() + 2]
        if tail.startswith(":"):
            # Bloco de assinatura digital: "NOME COMPLETO:92731767553".
            continue
        if _plausible_person(match.group(1)):
            return match.group(1)
    return None


def extract_act_fields(
    text: str,
    *,
    match_start: int,
    match_end: int,
) -> ActFields:
    """Extrai campos ao redor do verbo do ato, com offsets absolutos."""
    # O PDF quebra a mesma frase em várias linhas; sem normalizar, o cargo
    # sai cortado ("provimento efetivo de") e o nome se perde na quebra.
    window = _flatten(text[match_end : match_end + FIELD_WINDOW])
    heading_window = _flatten(
        text[max(0, match_start - HEADING_WINDOW) : match_start]
    )

    person = _PERSON_PATTERN.search(window)
    persons = _extract_persons(person, window)
    position = _POSITION_PATTERN.search(window)
    symbol = _SYMBOL_PATTERN.search(window)
    organization = _ORGANIZATION_PATTERN.search(window)
    act_number, act_date = _heading_fields(heading_window)

    return ActFields(
        fieldset_version=FIELDSET_VERSION,
        person_name=(
            persons[0]
            if persons
            else _not_found("person-uppercase-in-window")
        ),
        person_names=persons,
        position=_extract_position(position),
        position_symbol=(
            _matched("symbol-after-simbolo", symbol.group(1))
            if symbol
            else _not_found("symbol-after-simbolo")
        ),
        organization=_extract_organization(organization),
        act_number=act_number,
        act_date=act_date,
    )


def _extract_person(
    anchored: re.Match[str] | None,
    window: str,
) -> FieldExtraction:
    # 1) Marcador explícito ("a servidora X"): aceita caixa mista e é a
    # forma dominante nos atos reais.
    for match in _PERSON_MARKED_PATTERN.finditer(window):
        candidate = match.group(1).strip()
        if _plausible_person(candidate):
            return _matched("person-after-role-marker", candidate)
    # 2) Nome em maiúsculas logo após o verbo.
    if anchored and _plausible_person(anchored.group(1)):
        return _matched("person-uppercase-after-verb", anchored.group(1))
    # 3) Qualquer nome em maiúsculas na janela, filtrado por stoplist.
    fallback = _person_in_window(window)
    if fallback:
        return _matched("person-uppercase-in-window", fallback)
    return _not_found("person-uppercase-in-window")


def _extract_persons(
    anchored: re.Match[str] | None,
    window: str,
) -> tuple[FieldExtraction, ...]:
    """Retorna pessoas explicitamente marcadas dentro do mesmo ato.

    O campo legado ``person_name`` continua sendo o primeiro nome para manter
    compatibilidade com a API. A lista adicional existe para impedir que um
    ato que nomeia várias pessoas seja publicado como se tivesse uma só. A
    regra é deliberadamente conservadora: só multiplica quando o texto repete
    um marcador inequívoco (servidor(a), candidato(a), senhor(a)).
    """
    found: list[FieldExtraction] = []

    def add(value: str, rule_id: str) -> None:
        candidate = _normalize(value)
        if not _plausible_person(candidate):
            return
        normalized = _strip_accents(candidate).casefold()
        if any(
            _strip_accents(existing.value or "").casefold() == normalized
            for existing in found
        ):
            return
        found.append(_matched(rule_id, candidate))

    for match in _PERSON_MARKED_PATTERN.finditer(window):
        add(match.group(1), "person-after-role-marker")

    # Listas numeradas e várias cláusulas de cargo também identificam mais de
    # uma pessoa de forma suficientemente explícita para exigir revisão.
    for match in _NUMBERED_PERSON_PATTERN.finditer(window):
        add(match.group(1), "person-numbered-list")
    for match in _PERSON_BEFORE_POSITION_PATTERN.finditer(window):
        candidate = match.group(1)
        # Preserva a regra histórica para nomes em caixa alta; consumidores
        # já usam esse identificador para explicar a origem da captura.
        rule_id = (
            "person-uppercase-in-window"
            if candidate == candidate.upper()
            else "person-before-position"
        )
        add(candidate, rule_id)

    if not found and anchored and _plausible_person(anchored.group(1)):
        add(anchored.group(1), "person-uppercase-after-verb")

    if not found:
        fallback = _person_in_window(window)
        if fallback:
            add(fallback, "person-uppercase-in-window")

    return tuple(found)


def _extract_organization(match: re.Match[str] | None) -> FieldExtraction:
    if match is None:
        return _not_found("organization-secretaria")
    value = _ORGANIZATION_STOP.sub("", match.group(1)).strip(" ,;:-")
    if len(value) < 12:
        return _not_found("organization-secretaria")
    return _matched("organization-secretaria", value)


def _extract_position(match: re.Match[str] | None) -> FieldExtraction:
    if match is None:
        return _not_found("position-after-cargo-de")
    value = _PROVISION_PREFIX.sub("", match.group(1).strip())
    if len(value.strip(" ,;:-")) < 3:
        return _not_found("position-after-cargo-de")
    return _matched("position-after-cargo-de", value)


def fields_payload(fields: ActFields) -> dict[str, object]:
    def entry(extraction: FieldExtraction) -> dict[str, object]:
        return {
            "value": extraction.value,
            "status": extraction.status,
            "rule_id": extraction.rule_id,
        }

    return {
        "fieldset_version": fields.fieldset_version,
        "person_name": entry(fields.person_name),
        "person_names": [entry(person) for person in fields.person_names],
        "multiple_persons_detected": len(fields.person_names) > 1,
        "position": entry(fields.position),
        "position_symbol": entry(fields.position_symbol),
        "organization": entry(fields.organization),
        "act_number": entry(fields.act_number),
        "act_date": entry(fields.act_date),
    }
