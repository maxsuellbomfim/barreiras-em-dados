"""Assistencia de IA para documentos financeiros, sem calculo de valores.

A cascata pode ajudar a reconhecer o tipo de relatorio, recompor uma linha
fragmentada e sugerir uma explicacao em linguagem simples. O resultado nunca
e uma linha financeira canonica: cada valor sugerido precisa aparecer no
trecho, e a normalizacao deterministica continua sendo a fonte do numero.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from logging import Logger
from typing import Any

from .assist import _parse_content, run_cascade_content
from .verify import value_in_excerpt

FINANCIAL_ASSIST_PROMPT_VERSION = "financial-assist/1.0.0"
FINANCIAL_ASSIST_VALIDATOR_VERSION = "financial-assist-literal-check/1.0.0"
MAX_FINANCIAL_ASSIST_TEXT = 18_000
MAX_FINANCIAL_ASSIST_ROWS = 250
MAX_ASSIST_EXPLANATION = 800

_DOCUMENT_KINDS = frozenset(
    {
        "revenue_statement",
        "expense_statement",
        "fiscal_report",
        "transfer_report",
        "unknown",
    }
)
_CODE = re.compile(r"^\d+(?:\.\d+){9}$")
_MONEY = re.compile(r"^-?(?:\d{1,3}(?:\.\d{3})*|\d+),\d{2}$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class FinancialAssistRow:
    code: str
    description: str
    forecast: str
    period: str
    accumulated: str
    difference_more: str
    difference_less: str
    evidence: str


@dataclass(frozen=True)
class FinancialAssistOutcome:
    provider: str
    model: str
    document_kind: str
    period_start: str | None
    period_end: str | None
    explanation: str | None
    rows: tuple[FinancialAssistRow, ...]
    raw_response: str
    prompt_version: str = FINANCIAL_ASSIST_PROMPT_VERSION
    validator_version: str = FINANCIAL_ASSIST_VALIDATOR_VERSION


def build_financial_messages(text: str) -> list[dict[str, str]]:
    """Constroi o prompt de assistencia com limites explicitos de seguranca."""

    excerpt = text[:MAX_FINANCIAL_ASSIST_TEXT]
    system = (
        "Voce auxilia a leitura de documentos financeiros publicos de Barreiras-BA. "
        "Responda SOMENTE JSON valido. Nunca some, subtraia, converta, arredonde "
        "ou corrija valores. Copie os valores exatamente como aparecem no trecho. "
        "Nao crie linhas, codigos, datas ou categorias ausentes. O sistema ira "
        "validar cada campo literalmente e calcular totais fora da IA."
    )
    user = (
        "Classifique o documento e sugira linhas apenas para revisao humana. "
        "Use null quando nao souber. O campo evidence deve ser uma linha literal "
        "do trecho, incluindo codigo, descricao e valores.\n"
        'Formato obrigatorio: {"document_kind": "revenue_statement|expense_statement|'
        'fiscal_report|transfer_report|unknown", "period_start": "AAAA-MM-DD" ou null, '
        '"period_end": "AAAA-MM-DD" ou null, "explanation": "frase neutra" ou null, '
        '"rows": [{"code": "...", "description": "...", "forecast": "...", '
        '"period": "...", "accumulated": "...", "difference_more": "...", '
        '"difference_less": "...", "evidence": "linha literal"}]}\n'
        f"Trecho oficial:\n---\n{excerpt}\n---"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _optional_iso_date(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value.strip()):
        raise ValueError(f"{field} deve ser uma data ISO ou null")
    try:
        date.fromisoformat(value.strip())
    except ValueError as error:
        raise ValueError(f"{field} invalida") from error
    return value.strip()


def _money(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _MONEY.fullmatch(value.strip()):
        raise ValueError(f"{field} deve ser valor monetario literal brasileiro")
    integer, _, decimals = value.strip().lstrip("-").partition(",")
    try:
        Decimal(f"{'-' if value.strip().startswith('-') else ''}"
                f"{integer.replace('.', '')}.{decimals}")
    except InvalidOperation as error:
        raise ValueError(f"{field} invalido") from error
    return value.strip()


def parse_financial_assist_response(
    content: str,
    *,
    excerpt: str,
) -> dict[str, Any]:
    """Valida a sugestao da IA sem transforma-la em dado canonico."""

    parsed = _parse_content(content)
    kind = parsed.get("document_kind")
    if kind not in _DOCUMENT_KINDS:
        raise ValueError("document_kind fora do contrato")
    period_start = _optional_iso_date(parsed.get("period_start"), "period_start")
    period_end = _optional_iso_date(parsed.get("period_end"), "period_end")
    if period_start and period_end and period_start > period_end:
        raise ValueError("periodo invertido")
    explanation = parsed.get("explanation")
    if explanation is not None and (
        not isinstance(explanation, str)
        or not explanation.strip()
        or len(explanation.strip()) > MAX_ASSIST_EXPLANATION
    ):
        raise ValueError("explanation fora do contrato")
    rows = parsed.get("rows")
    if not isinstance(rows, list) or len(rows) > MAX_FINANCIAL_ASSIST_ROWS:
        raise ValueError("rows fora do contrato")

    normalized_rows: list[dict[str, str]] = []
    seen_codes: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"rows[{index}] deve ser objeto")
        code = row.get("code")
        description = row.get("description")
        evidence = row.get("evidence")
        if (
            not isinstance(code, str)
            or not _CODE.fullmatch(code.strip())
            or code.strip() in seen_codes
            or not isinstance(description, str)
            or not description.strip()
            or not isinstance(evidence, str)
            or len(evidence.strip()) < 20
        ):
            raise ValueError(f"rows[{index}] possui identificacao invalida")
        code = code.strip()
        description = description.strip()
        evidence = evidence.strip()
        if not value_in_excerpt(code, excerpt) or not value_in_excerpt(
            description, excerpt
        ):
            raise ValueError(f"rows[{index}] nao possui ancora no trecho")
        if not value_in_excerpt(evidence, excerpt):
            raise ValueError(f"rows[{index}] evidence nao ocorre no trecho")
        row_values = {
            "code": code,
            "description": description,
            "forecast": _money(row.get("forecast"), f"rows[{index}].forecast"),
            "period": _money(row.get("period"), f"rows[{index}].period"),
            "accumulated": _money(
                row.get("accumulated"), f"rows[{index}].accumulated"
            ),
            "difference_more": _money(
                row.get("difference_more"), f"rows[{index}].difference_more"
            ),
            "difference_less": _money(
                row.get("difference_less"), f"rows[{index}].difference_less"
            ),
            "evidence": evidence,
        }
        for field in (
            "forecast",
            "period",
            "accumulated",
            "difference_more",
            "difference_less",
        ):
            if not value_in_excerpt(row_values[field], evidence):
                raise ValueError(f"rows[{index}].{field} nao esta na evidence")
        seen_codes.add(code)
        normalized_rows.append(row_values)
    return {
        "document_kind": kind,
        "period_start": period_start,
        "period_end": period_end,
        "explanation": explanation.strip() if isinstance(explanation, str) else None,
        "rows": normalized_rows,
        "validator_version": FINANCIAL_ASSIST_VALIDATOR_VERSION,
    }


def run_financial_assistance(
    caller,
    environment: Mapping[str, str],
    text: str,
    logger: Logger,
    attempts=None,
) -> tuple[str, str, dict[str, Any]]:
    """Executa a cascata e retorna somente uma sugestao validada para revisao."""

    provider, model, content = run_cascade_content(
        caller,
        environment,
        build_financial_messages(text),
        logger,
        attempts,
    )
    return provider, model, parse_financial_assist_response(content, excerpt=text)
