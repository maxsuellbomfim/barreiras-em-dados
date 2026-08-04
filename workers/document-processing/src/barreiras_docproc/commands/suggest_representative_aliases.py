"""Sugere aliases de autoria legislativa via IA, sempre em revisão."""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Sequence

from barreiras_collectors.logging import log_event
from barreiras_collectors.settings import PersistenceSettings

from ..alias_assist import ALIAS_ASSIST_PROMPT_VERSION, run_alias_assistance
from ..alias_repository import RepresentativeAliasRepository
from ..assist import (
    PROVIDERS,
    CascadeUnavailableError,
    ContractViolationError,
    UrllibJsonCaller,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Sugere aliases de autoria da Câmara para revisão humana. "
            "Nenhuma sugestão é publicada ou aceita automaticamente."
        )
    )
    parser.add_argument("--limit", type=int, default=20)
    arguments = parser.parse_args(argv)
    if not 1 <= arguments.limit <= 50:
        parser.error("--limit deve estar entre 1 e 50.")

    logging.basicConfig(level=logging.INFO, format="%(message)s", force=True)
    logger = logging.getLogger(__name__)
    available = [
        provider.name
        for provider in PROVIDERS
        if (os.environ.get(provider.env_key) or "").strip()
    ]
    log_event(
        logger,
        logging.INFO,
        "representative_alias_assist_available",
        providers=available,
        prompt_version=ALIAS_ASSIST_PROMPT_VERSION,
    )
    if not available:
        log_event(
            logger,
            logging.WARNING,
            "representative_alias_assist_unavailable",
            reason="no_keys_configured",
        )
        return 0

    persistence = PersistenceSettings.from_env()
    if persistence.database_url is None:
        raise RuntimeError(
            "A sugestão de aliases requer PERSISTENCE_MODE=postgres-supabase."
        )
    repository = RepresentativeAliasRepository.from_dsn(persistence.database_url)
    pending = repository.pending_author_aliases(arguments.limit)
    caller = UrllibJsonCaller()
    suggested = 0
    failures = 0
    attempts: list = []
    for alias in pending:
        candidates = alias["candidates"]
        context = (
            f"A autoria apareceu em {alias['item_count']} registro(s) oficiais. "
            f"Chaves dos registros preservados: "
            f"{', '.join(alias['source_record_keys'][:8])}."
        )
        try:
            provider, model, result, raw_response = run_alias_assistance(
                caller,
                os.environ,
                alias["observed_name"],
                candidates,
                source_context=context,
                logger=logger,
                attempts=attempts,
            )
        except CascadeUnavailableError:
            log_event(
                logger,
                logging.WARNING,
                "representative_alias_assist_exhausted",
                processed=suggested,
            )
            break
        except ContractViolationError as error:
            failures += 1
            log_event(
                logger,
                logging.WARNING,
                "representative_alias_assist_contract_failure",
                observed_name=alias["observed_name"],
                detail=str(error)[:240],
            )
            continue

        repository.persist_suggestion(
            observed_name=alias["observed_name"],
            source_record_keys=alias["source_record_keys"],
            item_count=alias["item_count"],
            candidates=candidates,
            provider=provider,
            model=model,
            result=result,
            raw_response=raw_response,
        )
        suggested += 1
        log_event(
            logger,
            logging.INFO,
            "representative_alias_suggestion_persisted",
            observed_name=alias["observed_name"],
            decision=result["decision"],
            candidate_external_id=result["candidate_external_id"],
            provider=provider,
            model=model,
        )

    log_event(
        logger,
        logging.INFO,
        "representative_alias_assist_completed",
        pending_found=len(pending),
        suggested=suggested,
        contract_failures=failures,
        attempts=len(attempts),
        prompt_version=ALIAS_ASSIST_PROMPT_VERSION,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

