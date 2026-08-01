"""Cascata de inferência assistida (ADR 0011).

A IA sugere, nunca decide: toda saída vira inferência `needs_review` ao lado
do trecho original. Cota esgotada promove o próximo provedor; resposta fora
do contrato é falha registrada do nível, sem repasse cego; cascata esgotada
é estado explícito — o fluxo determinístico nunca depende disto.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from barreiras_collectors.logging import log_event

PROMPT_VERSION = "assisted-inference/1.0.0"
SUGGESTION_FIELDS = (
    "person_name",
    "position",
    "position_symbol",
    "organization",
    "act_number",
    "act_date",
)


@dataclass(frozen=True)
class Provider:
    name: str
    env_key: str
    url: str
    model: str


PROVIDERS: tuple[Provider, ...] = (
    Provider(
        "groq",
        "GROQ_API_KEY",
        "https://api.groq.com/openai/v1/chat/completions",
        "llama-3.3-70b-versatile",
    ),
    Provider(
        "openrouter",
        "OPENROUTER_API_KEY",
        "https://openrouter.ai/api/v1/chat/completions",
        "meta-llama/llama-3.3-70b-instruct:free",
    ),
    Provider(
        "gemini",
        "GEMINI_API_KEY",
        "https://generativelanguage.googleapis.com/v1beta/openai/"
        "chat/completions",
        "gemini-2.0-flash",
    ),
)


class QuotaExhaustedError(RuntimeError):
    """O provedor recusou por cota; o próximo nível assume."""


class ProviderTransientError(RuntimeError):
    """Falha transitória do provedor; o próximo nível assume."""


class ContractViolationError(RuntimeError):
    """Resposta fora do contrato JSON: falha do nível, sem repasse cego."""


class CascadeUnavailableError(RuntimeError):
    """Nenhum provedor disponível; estado explícito, não silêncio."""


@dataclass(frozen=True)
class AssistOutcome:
    provider: str
    model: str
    suggestions: dict[str, str | None]
    summary: str | None
    raw_response: str


class JsonCaller(Protocol):
    def post(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: dict[str, Any],
    ) -> tuple[int, bytes]: ...


class UrllibJsonCaller:
    def __init__(self, timeout_seconds: float = 60.0) -> None:
        self.timeout_seconds = timeout_seconds

    def post(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: dict[str, Any],
    ) -> tuple[int, bytes]:
        request = urllib.request.Request(  # noqa: S310 - HTTPS fixo por provedor.
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(  # noqa: S310
                request,
                timeout=self.timeout_seconds,
            ) as response:
                return response.status, response.read(1_048_576)
        except urllib.error.HTTPError as error:
            return error.code, error.read(1_048_576)


def build_messages(
    act_type: str,
    excerpt: str,
    current_fields: Mapping[str, Any],
) -> list[dict[str, str]]:
    missing = [
        field
        for field in SUGGESTION_FIELDS
        if not (
            isinstance(current_fields.get(field), Mapping)
            and current_fields[field].get("value")
        )
    ]
    system = (
        "Você lê trechos do Diário Oficial de Barreiras-BA. Responda "
        "SOMENTE um objeto JSON, sem comentários. Regra absoluta: se a "
        "informação não estiver literalmente no trecho, use null. Nunca "
        "deduza, nunca invente, nunca complete de memória."
    )
    user = (
        f"Ato do tipo: {act_type}.\n"
        f"Campos a sugerir (null se ausentes): {', '.join(missing)}.\n"
        'Inclua também "summary": uma frase simples e neutra explicando o '
        "ato para qualquer cidadão, sem opinião.\n"
        "Datas no formato AAAA-MM-DD.\n"
        f"Trecho oficial:\n---\n{excerpt}\n---"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _parse_content(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    try:
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ContractViolationError(
            "A resposta do provedor não é JSON válido."
        ) from error
    if not isinstance(parsed, dict):
        raise ContractViolationError("A resposta deve ser um objeto JSON.")
    return parsed


def call_provider(
    caller: JsonCaller,
    provider: Provider,
    api_key: str,
    messages: list[dict[str, str]],
) -> AssistOutcome:
    status, body = caller.post(
        provider.url,
        {"Authorization": f"Bearer {api_key}"},
        {
            "model": provider.model,
            "messages": messages,
            "temperature": 0,
        },
    )
    if status in (402, 429):
        raise QuotaExhaustedError(f"{provider.name} respondeu HTTP {status}.")
    if status != 200:
        raise ProviderTransientError(
            f"{provider.name} respondeu HTTP {status}."
        )
    try:
        envelope = json.loads(body)
        content = envelope["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
        raise ContractViolationError(
            f"{provider.name} devolveu envelope inesperado."
        ) from error

    parsed = _parse_content(str(content))
    suggestions: dict[str, str | None] = {}
    for field in SUGGESTION_FIELDS:
        value = parsed.get(field)
        suggestions[field] = (
            value.strip() if isinstance(value, str) and value.strip() else None
        )
    summary = parsed.get("summary")
    return AssistOutcome(
        provider=provider.name,
        model=provider.model,
        suggestions=suggestions,
        summary=(
            summary.strip()
            if isinstance(summary, str) and summary.strip()
            else None
        ),
        raw_response=str(content),
    )


def run_cascade(
    caller: JsonCaller,
    environment: Mapping[str, str],
    messages: list[dict[str, str]],
    logger: logging.Logger,
) -> AssistOutcome:
    for provider in PROVIDERS:
        api_key = (environment.get(provider.env_key) or "").strip()
        if not api_key:
            log_event(
                logger,
                logging.INFO,
                "assist_level_skipped",
                provider=provider.name,
                reason="missing_key",
            )
            continue
        try:
            return call_provider(caller, provider, api_key, messages)
        except QuotaExhaustedError:
            log_event(
                logger,
                logging.WARNING,
                "assist_level_promoted",
                provider=provider.name,
                reason="quota_exhausted",
            )
            continue
        except ProviderTransientError as error:
            log_event(
                logger,
                logging.WARNING,
                "assist_level_promoted",
                provider=provider.name,
                reason=f"transient: {error}",
            )
            continue
    raise CascadeUnavailableError(
        "Nenhum provedor de inferência assistida disponível."
    )
