"""Ligação determinística empenho → contrato municipal (ADR 0086).

Um empenho só se liga a um contrato quando o histórico escrito pela Prefeitura
cita o número do contrato, esse número (com sufixo de órgão e ano) aponta para
exatamente um contrato preservado e o favorecido corresponde ao contratado.
Valor, data ou nome aproximado nunca criam ligação. Todo caso que não fecha
fica como ``citacao_sem_confirmacao`` com o motivo, para revisão humana.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

RULE_VERSION = "commitment-contract-link/1.0.0"

LINKED = "ligado"
UNCONFIRMED = "citacao_sem_confirmacao"
NO_CITATION = "sem_citacao"
OUT_OF_SCOPE = "fora_do_escopo"

# "Contrato nº 070-FMS/2025", "contrato de nº 260/2021", "CONTRATO N°133/2026",
# "contrato 071-FMS/2025". Não casa "Contratação", "Contrato de Financiamento"
# nem "CONTRATO (C.C. 123456)", que não citam número de contrato.
_CITATION = re.compile(
    r"\bcontrato\s+(?:de\s+)?(?:n\s*[º°o.]{0,2}\s*)?"
    r"(?P<number>\d{1,4}(?:\s*-?\s*[a-z]{1,3})?\s*/\s*\d{2,5}(?:\s?fms\b)?)",
    re.IGNORECASE,
)
_CONTRACT_NUMBER = re.compile(
    r"^0*(?P<seq>\d{1,4})(?:\s*-?\s*(?P<pre>[A-Z]{1,3}))?"
    r"\s*/\s*(?P<year>\d{4})(?P<post>FMS)?$"
)
_AMENDMENT = re.compile(r"ADITIV|TERMO|CESS|SUPRESS", re.IGNORECASE)
_ORGAN_SUFFIXES = frozenset({"FMS"})
_LEGAL_FORMS = frozenset({"LTDA", "EIRELI", "ME", "EPP", "SA", "S", "A", "MEI"})
_STOPWORDS = frozenset({"E", "DE", "DA", "DO", "DAS", "DOS"})
FIELD_KEY = "field1144631"
FIELD_HISTORY = "field1144634"
FIELD_CREDITOR = "field1144629"


@dataclass(frozen=True)
class ContractKey:
    sequence: int
    letter: str
    organ: str
    year: int


@dataclass(frozen=True)
class MunicipalContract:
    record_key: str
    number: str
    contractor: str
    portal_id: str = ""


@dataclass(frozen=True)
class LinkDecision:
    commitment_key: str
    state: str
    reason: str
    cited_excerpt: str
    contract_record_key: str | None
    rule_version: str = RULE_VERSION
    contract_portal_id: str | None = None


def contract_number_key(text: str) -> ContractKey | None:
    """Chave comparável sem perder sufixo de órgão, letra nem ano."""
    compact = re.sub(r"\s+", "", text.upper())
    match = _CONTRACT_NUMBER.match(compact)
    if match is None:
        return None
    year = int(match["year"])
    if not 2000 <= year <= 2099:
        return None
    suffixes = [value for value in (match["pre"], match["post"]) if value]
    organs = [value for value in suffixes if value in _ORGAN_SUFFIXES]
    letters = [value for value in suffixes if value not in _ORGAN_SUFFIXES]
    if len(organs) > 1 or len(letters) > 1:
        return None
    if letters and len(letters[0]) != 1:
        return None
    return ContractKey(
        sequence=int(match["seq"]),
        letter=letters[0] if letters else "",
        organ=organs[0] if organs else "",
        year=year,
    )


def contract_citations(history: str) -> tuple[tuple[str, ContractKey | None], ...]:
    """Trechos citados, na ordem do texto, com a chave quando legível."""
    return tuple(
        (match.group(0), contract_number_key(match["number"]))
        for match in _CITATION.finditer(history)
    )


def party_name_key(name: str) -> frozenset[str]:
    """Nome sem acento, pontuação, forma societária e preposições."""
    ascii_name = (
        unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    )
    tokens = re.sub(r"[^A-Z0-9]+", " ", ascii_name.upper()).split()
    return frozenset(
        token for token in tokens if token not in _LEGAL_FORMS | _STOPWORDS
    )


def index_contracts(
    contracts: Iterable[MunicipalContract],
) -> Mapping[ContractKey, tuple[MunicipalContract, ...]]:
    """Contratos-base por chave; termos aditivos não são contratos distintos."""
    index: dict[ContractKey, dict[str, MunicipalContract]] = {}
    for contract in contracts:
        if _AMENDMENT.search(contract.number):
            continue
        key = contract_number_key(contract.number)
        if key is None:
            continue
        index.setdefault(key, {})[contract.record_key] = contract
    return {key: tuple(found.values()) for key, found in index.items()}


REVIEWABLE_REASONS = frozenset({"favorecido_divergente", "varios_contratos"})


def candidate_contracts(
    row: Mapping[str, str],
    contracts: Mapping[ContractKey, tuple[MunicipalContract, ...]],
) -> tuple[MunicipalContract, ...]:
    """Contratos que o número citado aponta, para a revisão humana decidir."""
    citations = contract_citations(row.get(FIELD_HISTORY, ""))
    keys = {key for _, key in citations}
    if len(keys) != 1 or None in keys:
        return ()
    return contracts.get(keys.pop(), ())


def link_commitment(
    row: Mapping[str, str],
    contracts: Mapping[ContractKey, tuple[MunicipalContract, ...]],
) -> LinkDecision:
    commitment_key = row[FIELD_KEY]
    if not commitment_key.startswith("O-"):
        return LinkDecision(
            commitment_key, OUT_OF_SCOPE, "extra_orcamentario", "", None
        )
    citations = contract_citations(row.get(FIELD_HISTORY, ""))
    if not citations:
        return LinkDecision(commitment_key, NO_CITATION, "", "", None)
    excerpt = " | ".join(text for text, _ in citations)
    keys = {key for _, key in citations}
    if None in keys:
        return LinkDecision(
            commitment_key, UNCONFIRMED, "numero_ilegivel", excerpt, None
        )
    if len(keys) > 1:
        return LinkDecision(
            commitment_key, UNCONFIRMED, "multiplas_citacoes", excerpt, None
        )
    candidates = contracts.get(keys.pop(), ())
    if not candidates:
        return LinkDecision(
            commitment_key, UNCONFIRMED, "nenhum_contrato", excerpt, None
        )
    if len(candidates) > 1:
        return LinkDecision(
            commitment_key, UNCONFIRMED, "varios_contratos", excerpt, None
        )
    contract = candidates[0]
    if party_name_key(row.get(FIELD_CREDITOR, "")) != party_name_key(
        contract.contractor
    ):
        return LinkDecision(
            commitment_key, UNCONFIRMED, "favorecido_divergente", excerpt, None
        )
    return LinkDecision(
        commitment_key,
        LINKED,
        "",
        excerpt,
        contract.record_key,
        contract_portal_id=contract.portal_id or None,
    )
