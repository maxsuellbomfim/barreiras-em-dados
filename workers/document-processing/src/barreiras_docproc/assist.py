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

PROMPT_VERSION = "assisted-inference/2.0.0"
# Limite do texto reescrito: um ato de pessoal cabe folgado.
MAX_CLEAN_TEXT_CHARS = 1200
# Teto de modelos testados por provedor numa execução.
MAX_MODELS_PER_PROVIDER = 4
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
    # Modelos gratuitos são descontinuados sem aviso: um nome fixo morre em
    # silêncio. A cascata consulta o catálogo do provedor e só cai para
    # estes nomes se o catálogo estiver indisponível.
    fallback_models: tuple[str, ...] = ()
    catalog_url: str = ""
    # Preferência por substring, em ordem: modelos de instrução baratos e
    # bons em português vêm primeiro.
    preferred: tuple[str, ...] = ()
    require: str = ""

    @property
    def models(self) -> tuple[str, ...]:
        return (self.model, *self.fallback_models)


PROVIDERS: tuple[Provider, ...] = (
    Provider(
        "groq",
        "GROQ_API_KEY",
        "https://api.groq.com/openai/v1/chat/completions",
        "llama-3.3-70b-versatile",
        ("llama-3.1-8b-instant", "openai/gpt-oss-120b"),
        catalog_url="https://api.groq.com/openai/v1/models",
        preferred=("llama", "gpt-oss", "gemma", "qwen"),
    ),
    Provider(
        "openrouter",
        "OPENROUTER_API_KEY",
        "https://openrouter.ai/api/v1/chat/completions",
        "google/gemma-4-26b-a4b-it:free",
        ("inclusionai/ling-3.0-flash:free",),
        catalog_url="https://openrouter.ai/api/v1/models",
        preferred=("gemma", "llama", "qwen", "mistral", "ling"),
        # Só modelos gratuitos: a plataforma não pode gerar custo silencioso.
        require=":free",
    ),
    Provider(
        "gemini",
        "GEMINI_API_KEY",
        "https://generativelanguage.googleapis.com/v1beta/openai/"
        "chat/completions",
        "gemini-flash-latest",
        ("gemini-2.5-flash", "gemini-2.0-flash"),
        catalog_url=(
            "https://generativelanguage.googleapis.com/v1beta/openai/models"
        ),
        preferred=("flash-latest", "flash"),
    ),
)


def discover_models(
    caller: JsonCaller,
    provider: Provider,
    api_key: str,
    logger: logging.Logger,
    attempts: list[AttemptRecord] | None = None,
) -> tuple[str, ...]:
    """Modelos vivos do provedor, em ordem de preferência.

    Nomes de modelo gratuito somem sem aviso — em 01/08/2026 os quatro
    modelos fixos do OpenRouter já não existiam. Perguntar ao catálogo
    evita que a plataforma emudeça por causa disso.
    """
    if not provider.catalog_url or not hasattr(caller, "get"):
        return provider.models
    catalog_status: int | None = None
    try:
        catalog_status, body = caller.get(
            provider.catalog_url,
            {"Authorization": f"Bearer {api_key}"},
        )
        if catalog_status != 200:
            # 401/403 aqui significa credencial inválida — diagnóstico que
            # separa "chave errada" de "modelo descontinuado".
            raise ValueError(
                f"HTTP {catalog_status}: "
                f"{body[:200].decode('utf-8', errors='replace')}"
            )
        payload = json.loads(body)
        identifiers = [
            str(entry["id"])
            for entry in payload.get("data", [])
            if isinstance(entry, dict) and entry.get("id")
        ]
    except (OSError, ValueError, KeyError, TypeError) as error:
        if attempts is not None:
            attempts.append(
                AttemptRecord(
                    provider.name,
                    "(catálogo)",
                    "transient",
                    catalog_status,
                    f"catálogo indisponível: {error}"[:500],
                )
            )
        log_event(
            logger,
            logging.WARNING,
            "assist_catalog_unavailable",
            provider=provider.name,
            status=catalog_status,
            detail=str(error)[:200],
        )
        return provider.models

    available = [
        identifier
        for identifier in identifiers
        if not provider.require or provider.require in identifier
    ]
    if not available:
        return provider.models

    ordered: list[str] = []
    for hint in provider.preferred:
        for identifier in available:
            if hint in identifier.lower() and identifier not in ordered:
                ordered.append(identifier)
    # Preferido configurado primeiro, se ainda existir no catálogo.
    for configured in provider.models:
        if configured in available:
            if configured in ordered:
                ordered.remove(configured)
            ordered.insert(0, configured)
            break
    for identifier in available:
        if identifier not in ordered:
            ordered.append(identifier)
    return tuple(ordered[:MAX_MODELS_PER_PROVIDER])


@dataclass(frozen=True)
class AttemptRecord:
    """Uma tentativa da cascata, para diagnóstico persistido."""

    provider: str
    model: str | None
    outcome: str
    http_status: int | None
    detail: str | None


class QuotaExhaustedError(RuntimeError):
    """O provedor recusou por cota; o próximo nível assume."""

    def __init__(self, message: str, http_status: int | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status


class ProviderTransientError(RuntimeError):
    """Falha transitória do provedor; o próximo nível assume."""

    def __init__(self, message: str, http_status: int | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status


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
    # Reescrita legível do ato: o texto extraído do PDF vem fragmentado e
    # fora de ordem; a IA recompõe a redação oficial sem inventar conteúdo.
    clean_text: str | None
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

    def get(
        self,
        url: str,
        headers: Mapping[str, str],
    ) -> tuple[int, bytes]:
        request = urllib.request.Request(  # noqa: S310 - HTTPS fixo.
            url,
            headers={**headers, "Accept": "application/json"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(  # noqa: S310
                request,
                timeout=self.timeout_seconds,
            ) as response:
                return response.status, response.read(4_194_304)
        except urllib.error.HTTPError as error:
            return error.code, error.read(4_194_304)

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
        "Você lê trechos do Diário Oficial de Barreiras-BA extraídos de "
        "PDF. O texto chega SUJO: palavras partidas no meio "
        "('MUN ICÍPIO DE BA RREIRAS'), linhas fora de ordem e ruído de "
        "assinatura digital. Sua tarefa é reconstituir o que está escrito, "
        "sem acrescentar nada. Responda SOMENTE um objeto JSON, sem "
        "comentários. Regra absoluta: se a informação não estiver no "
        "trecho, use null. Nunca deduza, nunca invente, nunca complete de "
        "memória."
    )
    user = (
        f"Ato do tipo: {act_type}.\n"
        f"Campos a sugerir (null se ausentes): {', '.join(missing)}.\n"
        'Inclua "texto_limpo": a redação do ato reconstituída em português '
        "correto — junte as palavras partidas, ponha as frases na ordem, "
        "remova cabeçalho de assinatura digital e rodapé. Mantenha os "
        "termos oficiais (número da portaria, nomes, cargos) exatamente "
        "como aparecem depois de recompostos; não resuma nem interprete "
        "aqui.\n"
        'Inclua "summary": uma frase simples e neutra explicando o ato '
        "para qualquer cidadão, sem opinião.\n"
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


def provider_content(
    caller: JsonCaller,
    provider: Provider,
    api_key: str,
    messages: list[dict[str, str]],
    model: str | None = None,
) -> str:
    """Conteúdo textual de um provedor, com falhas mapeadas por classe."""
    chosen = model or provider.model
    try:
        status, body = caller.post(
            provider.url,
            {"Authorization": f"Bearer {api_key}"},
            {
                "model": chosen,
                "messages": messages,
                "temperature": 0,
            },
        )
    except OSError as error:
        # URLError/timeout de rede não podem derrubar o passo: o próximo
        # nível da cascata assume, como qualquer falha transitória.
        raise ProviderTransientError(
            f"{provider.name} indisponível na rede: {error}"
        ) from error
    if status in (402, 429):
        raise QuotaExhaustedError(
            f"{provider.name} respondeu HTTP {status}.",
            status,
        )
    if status != 200:
        detail = body[:200].decode("utf-8", errors="replace")
        raise ProviderTransientError(
            f"{provider.name}/{chosen} respondeu HTTP {status}: {detail}",
            status,
        )
    try:
        envelope = json.loads(body)
        content = envelope["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
        raise ContractViolationError(
            f"{provider.name} devolveu envelope inesperado."
        ) from error
    return str(content)


def call_provider(
    caller: JsonCaller,
    provider: Provider,
    api_key: str,
    messages: list[dict[str, str]],
    model: str | None = None,
) -> AssistOutcome:
    content = provider_content(caller, provider, api_key, messages, model)
    parsed = _parse_content(str(content))
    suggestions: dict[str, str | None] = {}
    for field in SUGGESTION_FIELDS:
        value = parsed.get(field)
        suggestions[field] = (
            value.strip() if isinstance(value, str) and value.strip() else None
        )
    summary = parsed.get("summary")
    clean_text = parsed.get("texto_limpo")
    return AssistOutcome(
        provider=provider.name,
        model=model or provider.model,
        suggestions=suggestions,
        summary=(
            summary.strip()
            if isinstance(summary, str) and summary.strip()
            else None
        ),
        clean_text=(
            clean_text.strip()[:MAX_CLEAN_TEXT_CHARS]
            if isinstance(clean_text, str) and clean_text.strip()
            else None
        ),
        raw_response=str(content),
    )


def _walk_cascade(
    caller: JsonCaller,
    environment: Mapping[str, str],
    messages: list[dict[str, str]],
    logger: logging.Logger,
    attempts: list[AttemptRecord],
    invoke,
):
    """Percorre provedores e, dentro de cada um, os modelos alternativos."""
    for provider in PROVIDERS:
        api_key = (environment.get(provider.env_key) or "").strip()
        if not api_key:
            attempts.append(
                AttemptRecord(provider.name, None, "missing_key", None, None)
            )
            log_event(
                logger,
                logging.INFO,
                "assist_level_skipped",
                provider=provider.name,
                reason="missing_key",
            )
            continue
        for model in discover_models(
            caller,
            provider,
            api_key,
            logger,
            attempts,
        ):
            try:
                result = invoke(provider, api_key, model)
            except QuotaExhaustedError as error:
                attempts.append(
                    AttemptRecord(
                        provider.name,
                        model,
                        "quota_exhausted",
                        error.http_status,
                        str(error)[:500],
                    )
                )
                log_event(
                    logger,
                    logging.WARNING,
                    "assist_level_promoted",
                    provider=provider.name,
                    model=model,
                    reason="quota_exhausted",
                )
                # Cota é do provedor, não do modelo: promove o próximo nível.
                break
            except ProviderTransientError as error:
                attempts.append(
                    AttemptRecord(
                        provider.name,
                        model,
                        "transient",
                        error.http_status,
                        str(error)[:500],
                    )
                )
                log_event(
                    logger,
                    logging.WARNING,
                    "assist_model_promoted",
                    provider=provider.name,
                    model=model,
                    reason=f"transient: {error}",
                )
                continue
            attempts.append(
                AttemptRecord(provider.name, model, "succeeded", 200, None)
            )
            return result
    attempts.append(
        AttemptRecord("cascade", None, "exhausted", None, None)
    )
    raise CascadeUnavailableError(
        "Nenhum provedor de inferência assistida disponível."
    )


def run_cascade(
    caller: JsonCaller,
    environment: Mapping[str, str],
    messages: list[dict[str, str]],
    logger: logging.Logger,
    attempts: list[AttemptRecord] | None = None,
) -> AssistOutcome:
    return _walk_cascade(
        caller,
        environment,
        messages,
        logger,
        attempts if attempts is not None else [],
        lambda provider, api_key, model: call_provider(
            caller, provider, api_key, messages, model
        ),
    )


def run_cascade_content(
    caller: JsonCaller,
    environment: Mapping[str, str],
    messages: list[dict[str, str]],
    logger: logging.Logger,
    attempts: list[AttemptRecord] | None = None,
) -> tuple[str, str, str]:
    """Cascata em nível de conteúdo: (provedor, modelo, texto da resposta).

    Para contratos JSON diferentes do de campos de ato (ex.: resumo por
    edição), o chamador faz o próprio parse e validação do conteúdo.
    """
    return _walk_cascade(
        caller,
        environment,
        messages,
        logger,
        attempts if attempts is not None else [],
        lambda provider, api_key, model: (
            provider.name,
            model,
            provider_content(caller, provider, api_key, messages, model),
        ),
    )
