"""Comentário mensal assistido por IA, sem cálculo ou conclusão reputacional.

Os fatos chegam prontos do fechamento determinístico. A resposta aceita pelo
contrato é deliberadamente sem números: os valores permanecem nos cartões
gerados pelo código e a IA apenas melhora a compreensão do contexto.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from barreiras_docproc.assist import _parse_content, run_cascade_content

MONTHLY_ASSIST_PROMPT_VERSION = "monthly-finance-assist/1.1.0"
MONTHLY_ASSIST_VALIDATOR_VERSION = "monthly-finance-assist-literal-safe/1.1.0"
MAX_COMMENTARY_CHARS = 900

_DIGIT = re.compile(r"\d")
_FORBIDDEN_CLAIMS = re.compile(
    r"\b(corrup[cç][aã]o|irregularidade|crime|desvio|fraude|super[aá]vit|d[eé]ficit)\b",
    re.IGNORECASE,
)
_ALLOWED_CLASSES = frozenset({"fact", "methodology"})
_MISSING_COVERAGE_CLAIM = re.compile(
    r"(?:relat[óo]rios? compar[aá]veis .*n[aã]o .*dispon[ií]veis|"
    r"aguard(?:a|ando).{0,80}relat[óo]rios?|"
    r"falta(?:m)?.{0,40}(?:dados|relat[óo]rios?|cobertura)|"
    r"dados parciais|cobertura .*incompleta)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MonthlyFinanceFacts:
    closure_id: str
    period_start: str
    period_end: str
    public_body_name: str
    closure_status: str
    coverage_note: str
    revenue_report_amount: str | None
    expense_paid_amount: str | None
    operational_difference_amount: str | None


@dataclass(frozen=True)
class MonthlyAssistOutcome:
    commentary: str
    statement_class: str
    raw_response: str
    provider: str | None = None
    model: str | None = None
    prompt_version: str = MONTHLY_ASSIST_PROMPT_VERSION
    validator_version: str = MONTHLY_ASSIST_VALIDATOR_VERSION


def _facts_payload(facts: MonthlyFinanceFacts) -> dict[str, Any]:
    return {
        "period_start": facts.period_start,
        "period_end": facts.period_end,
        "public_body_name": facts.public_body_name,
        "closure_status": facts.closure_status,
        "coverage_note": facts.coverage_note,
        "revenue_report_amount": facts.revenue_report_amount,
        "expense_paid_amount": facts.expense_paid_amount,
        "operational_difference_amount": facts.operational_difference_amount,
    }


def build_monthly_assist_messages(
    facts: MonthlyFinanceFacts,
) -> list[dict[str, str]]:
    system = (
        "Você é um redator de transparência pública municipal. "
        "Responda somente JSON válido com as chaves commentary e statement_class. "
        "Explique em português simples o estado do fechamento recebido. "
        "Não faça contas, não repita valores, não invente datas, não atribua "
        "causas e não sugira corrupção, crime, fraude, desvio, superávit ou déficit. "
        "Use statement_class fact ou methodology. Se closure_status for needs_data, "
        "diga apenas que os relatórios comparáveis ainda não estão disponíveis. "
        "Se closure_status for operational, diga que os relatórios foram comparados "
        "e nunca afirme que faltam dados ou relatórios."
    )
    user = (
        "Fatos determinísticos já publicados (somente leitura):\n"
        f"{json.dumps(_facts_payload(facts), ensure_ascii=False, sort_keys=True)}\n\n"
        "Escreva uma única explicação curta, sem algarismos e sem símbolos monetários. "
        "Os números serão exibidos separadamente pelos cálculos do sistema."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def parse_monthly_assist_response(
    content: str,
    *,
    facts: MonthlyFinanceFacts,
) -> MonthlyAssistOutcome:
    parsed = _parse_content(content)
    commentary = parsed.get("commentary")
    statement_class = parsed.get("statement_class")
    if not isinstance(commentary, str) or not commentary.strip():
        raise ValueError("commentary ausente")
    commentary = commentary.strip()
    if len(commentary) > MAX_COMMENTARY_CHARS:
        raise ValueError("commentary excede o limite")
    if _DIGIT.search(commentary):
        raise ValueError("commentary contém algarismos; valores ficam fora da IA")
    if _FORBIDDEN_CLAIMS.search(commentary):
        raise ValueError("commentary contém conclusão proibida")
    if statement_class not in _ALLOWED_CLASSES:
        raise ValueError("statement_class inválido")
    if facts.closure_status == "needs_data" and not re.search(
        r"cobertura|relat[óo]ri|dispon[ií]v", commentary, re.IGNORECASE
    ):
        raise ValueError("comentário não explica a falta de cobertura")
    if facts.closure_status == "operational" and _MISSING_COVERAGE_CLAIM.search(
        commentary
    ):
        raise ValueError("comentário contradiz o fechamento operacional")
    return MonthlyAssistOutcome(
        commentary=commentary,
        statement_class=statement_class,
        raw_response=content,
    )


def run_monthly_assistance(
    caller,
    environment,
    facts: MonthlyFinanceFacts,
    logger,
    attempts=None,
) -> MonthlyAssistOutcome:
    provider, model, content = run_cascade_content(
        caller,
        environment,
        build_monthly_assist_messages(facts),
        logger,
        attempts,
    )
    outcome = parse_monthly_assist_response(content, facts=facts)
    return MonthlyAssistOutcome(
        commentary=outcome.commentary,
        statement_class=outcome.statement_class,
        raw_response=outcome.raw_response,
        provider=provider,
        model=model,
        prompt_version=outcome.prompt_version,
        validator_version=outcome.validator_version,
    )
