"""Gera o resumo ancorado de cada edição direta do Diário (ADR 0013)."""

from __future__ import annotations

import argparse
import json
import logging
import os
from collections.abc import Sequence
from types import SimpleNamespace

from barreiras_collectors.logging import log_event
from barreiras_collectors.settings import CollectorSettings, PersistenceSettings

from .. import digest as digest_module
from ..assist import (
    PROVIDERS,
    CascadeUnavailableError,
    ContractViolationError,
    UrllibJsonCaller,
    run_cascade_content,
)
from ..candidates import defragment
from ..postgres import PostgresExtractionRepository

RATIONALE = (
    "Resumo por edição publicado automaticamente: cada item tem citação "
    f"literal conferida no texto oficial pelo {digest_module.ANCHOR_VERIFIER_VERSION} "
    "(ADR 0013); itens sem âncora foram descartados."
)
LOCAL_RATIONALE = (
    "Resumo por regras determinísticas, sem IA: cada item foi derivado de um "
    "candidato de ato de pessoal e preserva uma âncora do texto oficial."
)
LOCAL_DIGEST_VERSION = "edition-digest-deterministic/1.0.0"


def main(argv: Sequence[str] | None = None) -> int:
    """Falha aqui é estado explícito: não derruba os passos anteriores."""
    try:
        return _run(argv)
    except Exception as error:
        logging.getLogger(__name__).warning(
            json.dumps(
                {
                    "event": "digest_step_failed_gracefully",
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
            "Para cada edição direta com texto, pede à cascata de IA a "
            "lista traduzida dos atos publicados e só aceita itens cuja "
            "citação-âncora ocorre literalmente no texto oficial."
        )
    )
    parser.add_argument("--limit", type=int, default=2)
    arguments = parser.parse_args(argv)
    if not 1 <= arguments.limit <= 20:
        parser.error("--limit deve estar entre 1 e 20.")

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
        "digest_levels_available",
        providers=available,
        prompt_version=digest_module.DIGEST_PROMPT_VERSION,
    )
    if not available:
        log_event(
            logger,
            logging.WARNING,
            "digest_cascade_unavailable",
            reason="no_keys_configured_local_fallback_enabled",
        )
    if persistence_settings.database_url is None:
        raise RuntimeError(
            "O resumo por edição requer PERSISTENCE_MODE=postgres-supabase."
        )
    repository = PostgresExtractionRepository.from_dsn(
        persistence_settings.database_url
    )
    if not repository.automated_review_available():
        log_event(
            logger,
            logging.WARNING,
            "digest_unavailable",
            reason="migration_20260801190000_pendente",
        )
        return 0
    caller = UrllibJsonCaller()

    digested = 0
    attempts: list = []
    cascade_disabled = not available
    for artifact in repository.pending_digest_artifacts(
        arguments.limit,
        digest_module.job_idempotency_key,
    ):
        # A IA recebe o texto já reconstituído: pedir citação literal sobre
        # texto fragmentado ("MUN ICÍPIO") fazia a âncora nunca bater e
        # todos os itens serem descartados em silêncio.
        text = defragment(repository.edition_pages_text(artifact["artifact_id"]))
        if not text.strip():
            continue
        chunks = digest_module.chunk_text(text)
        partial = len(chunks) > digest_module.MAX_CHUNKS_PER_EDITION
        chunks = chunks[: digest_module.MAX_CHUNKS_PER_EDITION]

        items = []
        providers: list[str] = []
        chunks_failed = 0
        items_dropped = 0
        cascade_exhausted = False
        for chunk in chunks:
            if cascade_disabled:
                break
            try:
                provider, _model, content = run_cascade_content(
                    caller,
                    os.environ,
                    digest_module.build_digest_messages(chunk),
                    logger,
                    attempts,
                )
            except CascadeUnavailableError:
                cascade_exhausted = True
                break
            try:
                accepted, dropped = digest_module.parse_digest_items(content, chunk)
            except ContractViolationError as error:
                chunks_failed += 1
                log_event(
                    logger,
                    logging.WARNING,
                    "digest_chunk_contract_violation",
                    edition=artifact["edition"],
                    detail=str(error)[:200],
                )
                continue
            providers.append(provider)
            items.extend(accepted)
            items_dropped += dropped

        if cascade_exhausted or cascade_disabled:
            cascade_disabled = True
            items = digest_module.deterministic_digest_items(text)
            providers = ["local-deterministic"]
            attempts.append(
                SimpleNamespace(
                    provider="local-deterministic",
                    model="digest-rules-v1",
                    outcome="fallback_succeeded",
                    http_status=None,
                    detail="external_provider_unavailable",
                )
            )
            # O recorte local é deliberadamente parcial: o documento integral
            # continua preservado e itens não reconhecidos não são inventados.
            log_event(
                logger,
                logging.WARNING,
                "digest_local_fallback_used",
                reason="all_levels_exhausted",
                edition=artifact["edition"],
                items=len(items),
                digested=digested,
            )

        if not items:
            log_event(
                logger,
                logging.WARNING,
                "digest_edition_empty",
                edition=artifact["edition"],
                chunks_failed=chunks_failed,
            )
            continue

        payload = digest_module.digest_payload(
            edition=artifact["edition"],
            year=artifact["year"],
            items=items,
            chunks_total=len(chunks),
            chunks_failed=chunks_failed,
            items_dropped=items_dropped,
            partial=(
                partial
                or chunks_failed > 0
                or providers == ["local-deterministic"]
            ),
            providers=providers,
            prompt_version=(
                LOCAL_DIGEST_VERSION
                if providers == ["local-deterministic"]
                else digest_module.DIGEST_PROMPT_VERSION
            ),
        )
        result_id = repository.persist_digest(
            artifact_id=artifact["artifact_id"],
            job_idempotency_key=digest_module.job_idempotency_key(
                artifact["sha256"]
            ),
            extractor_version=(
                LOCAL_DIGEST_VERSION
                if providers == ["local-deterministic"]
                else digest_module.DIGEST_PROMPT_VERSION
            ),
            payload=payload,
        )
        if result_id is None:
            continue
        repository.record_automated_review(
            result_id=result_id,
            rationale=(
                LOCAL_RATIONALE
                if providers == ["local-deterministic"]
                else RATIONALE
            ),
            verification={
                "verifier": digest_module.ANCHOR_VERIFIER_VERSION,
                "items_total": len(items),
                "items_dropped": items_dropped,
                "chunks_failed": chunks_failed,
            },
        )
        digested += 1
        log_event(
            logger,
            logging.INFO,
            "digest_edition_published",
            edition=artifact["edition"],
            items=len(items),
            items_dropped=items_dropped,
            partial=payload["stats"]["partial"],
        )

    try:
        repository.record_assist_attempts(
            "digest_gazette_editions",
            attempts,
        )
    except Exception as error:
        log_event(
            logger,
            logging.WARNING,
            "digest_diagnostics_unavailable",
            detail=str(error)[:200],
        )

    log_event(
        logger,
        logging.INFO,
        "digest_batch_completed",
        digested=digested,
        attempts=len(attempts),
        prompt_version=digest_module.DIGEST_PROMPT_VERSION,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
