"""Extração determinística das emendas da LOA estadual destinadas a Barreiras.

Os anexos de 2022 a 2025 organizam as linhas por município. O anexo de 2026
organiza as linhas por autor e pode publicar o cabeçalho do parlamentar em uma
página anterior. O parser mantém esses contratos separados e nunca interpreta
uma simples menção a Barreiras no objeto como chave territorial.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

LOA_BARREIRAS_PARSER_VERSION = "bahia-state-loa-barreiras/1.1.0"

_TARGET_ROW = re.compile(r"^Barreiras\s+(?P<number>\d{1,6})\s+(?P<body>.+)$", re.I)
_PRE_2026_TERRITORIAL_CANDIDATE = re.compile(
    r"^Barreiras(?:\s+|\s*[-|:\u2013\u2014]\s*)\d{1,6}\s+\S",
    re.I,
)
_MUNICIPAL_ROW = re.compile(
    r"^[A-ZÁÀÂÃÉÊÍÓÔÕÚÜÇ][A-Za-zÁÀÂÃÉÊÍÓÔÕÚÜÇáàâãéêíóôõúüç'\u2019.-]*"
    r"(?:\s+(?:d[aeo]s?|[A-ZÁÀÂÃÉÊÍÓÔÕÚÜÇ]"
    r"[A-Za-zÁÀÂÃÉÊÍÓÔÕÚÜÇáàâãéêíóôõúüç'\u2019.-]*)){0,6}"
    r"\s+\d{1,6}\s+\S"
)
_PRE_2026_CODES = re.compile(
    r"^(?P<author>.+?)\s+"
    r"(?P<agency>[A-ZÁÀÂÃÉÊÍÓÔÕÚÜÇ]{2,12})\s+"
    r"(?P<unit>[A-ZÁÀÂÃÉÊÍÓÔÕÚÜÇ][A-Z0-9ÁÀÂÃÉÊÍÓÔÕÚÜÇ/.-]{1,20})\s+"
    r"(?P<description>.+)$"
)
_AMOUNT_AT_END = re.compile(
    r"(?<![\d./-])"
    r"(?P<amount>(?:\d{1,3}(?:\s*\.\s*\d{3})+|\d{1,12})(?:,\d{2})?)\s*$"
)
_TAX_IDENTIFIER_AT_END = re.compile(
    r"(?<!\d)(?:"
    r"\d{3}\s*\.\s*\d{3}\s*\.\s*\d{3}|"
    r"\d{2}\s*\.\s*\d{3}\s*\.\s*\d{3}\s*/\s*\d{4}"
    r")\s*-\s*\d{2}\s*$"
)
_AUTHOR_HEADER_2026 = re.compile(
    r"^(?P<name>.+?)\s+-\s+(?P<code>\d{5,7})\s+\d[\d .]*$"
)
_ROW_2026 = re.compile(
    r"^(?P<number>\d{1,6})\s+"
    r"(?P<agency>[A-ZÁÀÂÃÉÊÍÓÔÕÚÜÇ]{2,12})\s+"
    r"(?P<unit>[A-ZÁÀÂÃÉÊÍÓÔÕÚÜÇ][A-Z0-9ÁÀÂÃÉÊÍÓÔÕÚÜÇ/.-]{1,20})\s+"
    r"(?P<action>\d{1,8})\s+(?P<description>.+)$"
)
_TARGET_MUNICIPALITY_VALUE = re.compile(
    r"^Barreiras\s+"
    r"(?P<amount>(?:\d{1,3}(?:\s*\.\s*\d{3})+|\d{1,12})(?:,\d{2})?)"
    r"\s*$",
    re.I,
)
_TARGET_MUNICIPALITY_CANDIDATE = re.compile(
    r"^Barreiras\s*(?:[-|:\u2013\u2014]\s*)?"
    r"(?:R\$\s*)?\d[\d .]*(?:,\d{2})?\s*$",
    re.I,
)
_TOTAL_LINE = re.compile(r"^Total\b", re.I)


class LoaParseError(ValueError):
    """O documento não satisfaz o contrato necessário para publicação."""


@dataclass(frozen=True)
class LoaPage:
    page_number: int
    text: str

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValueError("A página da evidência deve ser positiva.")


@dataclass(frozen=True)
class AuthorizedLoaAmendment:
    fiscal_year: int
    annex_code: str
    amendment_number: str
    author_name: str
    author_external_code: str | None
    agency_code: str
    budget_unit_code: str
    action_code: str | None
    official_description: str
    municipality: str
    authorized_amount: Decimal
    page_number: int
    evidence_text: str
    evidence_sha256: str
    parser_version: str = LOA_BARREIRAS_PARSER_VERSION


@dataclass
class _Pending2026Row:
    page_number: int
    lines: list[str]
    author_name: str | None
    author_external_code: str | None


def parse_barreiras_loa_pages(
    *,
    fiscal_year: int,
    annex_code: str,
    pages: tuple[LoaPage, ...],
) -> tuple[AuthorizedLoaAmendment, ...]:
    """Extrai somente linhas cujo campo municipal oficial seja Barreiras."""
    _validate_contract(fiscal_year=fiscal_year, annex_code=annex_code)
    ordered_pages = tuple(sorted(pages, key=lambda page: page.page_number))
    if len({page.page_number for page in ordered_pages}) != len(ordered_pages):
        raise LoaParseError("O documento contém página duplicada.")

    if fiscal_year == 2026:
        rows = _parse_2026(ordered_pages, fiscal_year, annex_code)
    else:
        rows = _parse_pre_2026(ordered_pages, fiscal_year, annex_code)
    _reject_duplicate_rows(rows)
    return tuple(rows)


def _validate_contract(*, fiscal_year: int, annex_code: str) -> None:
    expected = "I" if fiscal_year == 2026 else "III"
    if fiscal_year not in {2022, 2023, 2024, 2025, 2026}:
        raise LoaParseError("O exercício não possui contrato de extração.")
    if annex_code != expected:
        raise LoaParseError("O código do anexo diverge do exercício.")


def _lines(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return [line.strip() for line in normalized.split("\n") if line.strip()]


def _parse_pre_2026(
    pages: tuple[LoaPage, ...],
    fiscal_year: int,
    annex_code: str,
) -> list[AuthorizedLoaAmendment]:
    rows: list[AuthorizedLoaAmendment] = []
    for page in pages:
        lines = _lines(page.text)
        territorial_candidates = [
            line for line in lines if _PRE_2026_TERRITORIAL_CANDIDATE.match(line)
        ]
        malformed_candidates = [
            line for line in territorial_candidates if _TARGET_ROW.match(line) is None
        ]
        if malformed_candidates:
            raise LoaParseError(
                "Uma linha territorial de Barreiras não corresponde ao layout "
                "esperado do anexo."
            )
        starts = [index for index, line in enumerate(lines) if _TARGET_ROW.match(line)]
        for start in starts:
            end = start + 1
            while end < len(lines) and not _MUNICIPAL_ROW.match(lines[end]):
                end += 1
            evidence_lines = lines[start:end]
            rows.append(
                _parse_pre_2026_row(
                    evidence_lines,
                    fiscal_year=fiscal_year,
                    annex_code=annex_code,
                    page_number=page.page_number,
                )
            )
    return rows


def _parse_pre_2026_row(
    lines: list[str],
    *,
    fiscal_year: int,
    annex_code: str,
    page_number: int,
) -> AuthorizedLoaAmendment:
    first = _TARGET_ROW.match(lines[0])
    if first is None:
        raise LoaParseError("A linha municipal perdeu seu início.")
    body = " ".join([first.group("body"), *lines[1:]])
    if _TAX_IDENTIFIER_AT_END.search(body):
        raise LoaParseError("A linha de Barreiras não possui valor autorizado.")
    amount_match = _AMOUNT_AT_END.search(body)
    if amount_match is None:
        raise LoaParseError("A linha de Barreiras não possui valor autorizado.")
    amount = _parse_brl_units(amount_match.group("amount"))
    without_amount = body[: amount_match.start()].strip()
    codes = _PRE_2026_CODES.match(without_amount)
    if codes is None:
        raise LoaParseError("A linha de Barreiras não separa autor, órgão e unidade.")
    evidence = "\n".join(lines)
    return AuthorizedLoaAmendment(
        fiscal_year=fiscal_year,
        annex_code=annex_code,
        amendment_number=first.group("number"),
        author_name=_collapse(codes.group("author")),
        author_external_code=None,
        agency_code=codes.group("agency"),
        budget_unit_code=codes.group("unit"),
        action_code=None,
        official_description=_collapse(codes.group("description")),
        municipality="Barreiras",
        authorized_amount=amount,
        page_number=page_number,
        evidence_text=evidence,
        evidence_sha256=_sha256(evidence),
    )


def _parse_2026(
    pages: tuple[LoaPage, ...],
    fiscal_year: int,
    annex_code: str,
) -> list[AuthorizedLoaAmendment]:
    rows: list[AuthorizedLoaAmendment] = []
    author_name: str | None = None
    author_code: str | None = None
    pending: _Pending2026Row | None = None

    def flush() -> None:
        nonlocal pending
        if pending is None:
            return
        parsed = _parse_2026_row(
            pending,
            fiscal_year=fiscal_year,
            annex_code=annex_code,
        )
        if parsed is not None:
            rows.append(parsed)
        pending = None

    for page in pages:
        for line in _lines(page.text):
            header = _AUTHOR_HEADER_2026.match(line)
            if header is not None:
                flush()
                author_name = _collapse(header.group("name"))
                author_code = header.group("code")
                continue
            if _TOTAL_LINE.match(line):
                flush()
                continue
            if _ROW_2026.match(line):
                flush()
                pending = _Pending2026Row(
                    page_number=page.page_number,
                    lines=[line],
                    author_name=author_name,
                    author_external_code=author_code,
                )
                continue
            if pending is not None:
                pending.lines.append(line)
    flush()
    return rows


def _parse_2026_row(
    pending: _Pending2026Row,
    *,
    fiscal_year: int,
    annex_code: str,
) -> AuthorizedLoaAmendment | None:
    first = _ROW_2026.match(pending.lines[0])
    if first is None:
        raise LoaParseError("A linha de 2026 perdeu seu início estruturado.")
    territorial_index: int | None = None
    territorial_match: re.Match[str] | None = None
    territorial_candidates = 0
    for index, line in enumerate(pending.lines[1:], start=1):
        if _TARGET_MUNICIPALITY_CANDIDATE.match(line):
            territorial_candidates += 1
        match = _TARGET_MUNICIPALITY_VALUE.match(line)
        if match is not None:
            if territorial_match is not None:
                raise LoaParseError(
                    "A emenda de 2026 possui mais de uma linha territorial de "
                    "Barreiras."
                )
            territorial_index = index
            territorial_match = match
    if territorial_candidates > 1:
        raise LoaParseError(
            "A emenda de 2026 possui mais de uma linha territorial candidata "
            "para Barreiras."
        )
    if territorial_candidates and territorial_match is None:
        raise LoaParseError(
            "Uma linha territorial de Barreiras não corresponde ao layout "
            "esperado do anexo de 2026."
        )
    if territorial_index is None or territorial_match is None:
        return None
    if pending.author_name is None or pending.author_external_code is None:
        raise LoaParseError(
            "A linha de Barreiras em 2026 não possui autor comprovado pelo cabeçalho."
        )
    description = _collapse(
        " ".join(
            [
                first.group("description"),
                *pending.lines[1:territorial_index],
            ]
        )
    )
    if not description:
        raise LoaParseError("A emenda de 2026 não possui descrição oficial.")
    evidence = "\n".join(pending.lines[: territorial_index + 1])
    return AuthorizedLoaAmendment(
        fiscal_year=fiscal_year,
        annex_code=annex_code,
        amendment_number=first.group("number"),
        author_name=pending.author_name,
        author_external_code=pending.author_external_code,
        agency_code=first.group("agency"),
        budget_unit_code=first.group("unit"),
        action_code=first.group("action"),
        official_description=description,
        municipality="Barreiras",
        authorized_amount=_parse_brl_units(territorial_match.group("amount")),
        page_number=pending.page_number,
        evidence_text=evidence,
        evidence_sha256=_sha256(evidence),
    )


def _parse_brl_units(raw: str) -> Decimal:
    canonical = raw.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        value = Decimal(canonical)
    except InvalidOperation as error:
        raise LoaParseError("O valor autorizado não é decimal válido.") from error
    if value <= 0:
        raise LoaParseError("O valor autorizado deve ser positivo.")
    return value


def _collapse(value: str) -> str:
    return " ".join(value.split())


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _reject_duplicate_rows(rows: list[AuthorizedLoaAmendment]) -> None:
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row.author_name.casefold(), row.amendment_number)
        if key in seen:
            raise LoaParseError(
                "A mesma emenda foi extraída de forma duplicada para o autor."
            )
        seen.add(key)
