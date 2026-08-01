"""Sugere campos e resumos por IA em cascata, sob revisão humana (ADR 0011)."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from collections.abc import Sequence

from barreiras_collectors.logging import log_event
from barreiras_collectors.settings import CollectorSettings, PersistenceSettings

from ..assist import (
    PROMPT_VERSION,
    PROVIDERS,
    CascadeUnavailableError,
    ContractViolationError,
    UrllibJsonCaller,
    build_messages,
    run_cascade,
)
from ..postgres import PostgresExtractionRepository


def main(argv: Sequence[str] | None = None) -> int:
    """Nunca derruba o workflow: falha aqui é estado explícito e logado.

    Antes, qualquer exceção neste passo abortava também a publicação
    verificada e o resumo por edição, que vinham depois — a plataforma
    inteira parava por causa de um provedor de IA instável.
    """
    try:
        return _run(argv)
    except Exception as error:  # noqa: BLE001 - fronteira de processo
        logging.getLogger(__name__).warning(
            json.dumps(
                {
                    "event": "assist_step_failed_gracefully",
                    "error_type": type(error).__name__,
                    "detail": str(error)[:300],
                },
                ensure_ascii=False,
            )
        )
        return 0


def _run(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Para candidatos pendentes, sugere campos ausentes e um resumo "
            "em linguagem simples via cascata de provedores gratuitos. "
            "Nada é publicado: toda sugestão nasce como inferência em "
            "revisão."
        )
    )
    parser.add_argument("--limit", type=int, default=10)
    arguments = parser.parse_args(argv)
    if not 1 <= arguments.limit <= 50:
        parser.error("--limit deve estar entre 1 e 50.")

    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    logger = logging.getLogger(__name__)

    available = [
        provider.name
        for provider in PROVIDERS
        if (os.environ.get(provider.env_key) or "").strip()
    ]
    log_event(
        logger,
        logging.INFO,
        "assist_levels_available",
        providers=available,
        prompt_version=PROMPT_VERSION,
    )
    if not available:
        log_event(
            logger,
            logging.WARNING,
            "assist_cascade_unavailable",
            reason="no_keys_configured",
        )
        return 0

    if persistence_settings.database_url is None:
        raise RuntimeError(
            "A inferência assistida requer PERSISTENCE_MODE=postgres-supabase."
        )
    repository = PostgresExtractionRepository.from_dsn(
        persistence_settings.database_url
    )
    caller = UrllibJsonCaller()

    pending = repository.pending_enrichment_candidates(arguments.limit)
    suggested = 0
    contract_failures = 0
    attempts: list = []
    for candidate in pending:
        payload = candidate["payload"]
        excerpt = str(payload.get("excerpt") or "")
        if not excerpt:
            continue
        fields = payload.get("fields") or {}
        messages = build_messages(
            candidate["candidate_type"],
            excerpt,
            fields if isinstance(fields, dict) else {},
        )
        try:
            outcome = run_cascade(
                caller,
                os.environ,
                messages,
                logger,
                attempts,
            )
        except CascadeUnavailableError:
            log_event(
                logger,
                logging.WARNING,
                "assist_cascade_unavailable",
                reason="all_levels_exhausted",
                suggested=suggested,
            )
            break
        except ContractViolationError as error:
            contract_failures += 1
            log_event(
                logger,
                logging.WARNING,
                "assist_contract_violation",
                source_result_id=candidate["result_id"],
                detail=str(error)[:200],
            )
            continue

        repository.persist_enrichment(
            source_result_id=candidate["result_id"],
            extraction_job_id=candidate["job_id"],
            extractor_version=PROMPT_VERSION,
            payload={
                "schema_name": "assisted-enrichment",
                "schema_version": "2.0.0",
                "prompt_version": PROMPT_VERSION,
                "provider": outcome.provider,
                "model": outcome.model,
                "source_result_id": candidate["result_id"],
                "input_excerpt_sha256": hashlib.sha256(
                    excerpt.encode("utf-8")
                ).hexdigest(),
                "suggestions": outcome.suggestions,
                "summary": outcome.summary,
                "clean_text": outcome.clean_text,
                "raw_response": outcome.raw_response,
            },
        )
        suggested += 1
        log_event(
            logger,
            logging.INFO,
            "assist_enrichment_persisted",
            source_result_id=candidate["result_id"],
            provider=outcome.provider,
            model=outcome.model,
        )

    # Diagnóstico persistido: a causa de "nada sugerido" fica legível no
    # banco, sem depender do log do Actions.
    try:
        repository.record_assist_attempts(
            "assist_extraction_candidates",
            attempts,
        )
    except Exception as error:  # noqa: BLE001 - diagnóstico é best effort
        log_event(
            logger,
            logging.WARNING,
            "assist_diagnostics_unavailable",
            detail=str(error)[:200],
        )

    log_event(
        logger,
        logging.INFO,
        "assist_batch_completed",
        pending_found=len(pending),
        suggested=suggested,
        contract_failures=contract_failures,
        attempts=len(attempts),
        prompt_version=PROMPT_VERSION,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
