"""Publica automaticamente candidatos verificados por código (ADR 0012)."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

from barreiras_collectors.logging import log_event
from barreiras_collectors.settings import CollectorSettings, PersistenceSettings

from ..postgres import PostgresExtractionRepository
from ..verify import VERIFIER_VERSION, verify_candidate

RATIONALE = (
    "Publicação automática: pessoa, número e data da Portaria conferidos "
    f"literalmente no trecho oficial pelo {VERIFIER_VERSION} (ADR 0012)."
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Publica candidatos cujo essencial foi conferido literalmente "
            "no trecho oficial; o restante permanece na fila humana. "
            "Toda publicação é auditada e reversível."
        )
    )
    parser.add_argument("--limit", type=int, default=20)
    arguments = parser.parse_args(argv)
    if not 1 <= arguments.limit <= 100:
        parser.error("--limit deve estar entre 1 e 100.")

    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    logger = logging.getLogger(__name__)
    if persistence_settings.database_url is None:
        raise RuntimeError(
            "A publicação automática requer PERSISTENCE_MODE=postgres-supabase."
        )
    repository = PostgresExtractionRepository.from_dsn(
        persistence_settings.database_url
    )
    if not repository.automated_review_available():
        # Estado explícito, não falha: a migration ainda não foi aplicada.
        log_event(
            logger,
            logging.WARNING,
            "publish_unavailable",
            reason="migration_20260801190000_pendente",
        )
        return 0

    published = 0
    kept = 0
    for candidate in repository.publishable_candidates(arguments.limit):
        assisted = candidate["assisted"] or {}
        suggestions = assisted.get("suggestions")
        summary = assisted.get("summary")
        outcome = verify_candidate(
            candidate["payload"],
            suggestions if isinstance(suggestions, dict) else None,
            summary if isinstance(summary, str) else None,
        )
        if not outcome.publishable:
            kept += 1
            log_event(
                logger,
                logging.INFO,
                "publish_candidate_kept_for_review",
                result_id=candidate["result_id"],
                missing=list(outcome.missing),
            )
            continue

        review_id = repository.record_automated_review(
            result_id=candidate["result_id"],
            rationale=RATIONALE,
            verification={
                "verifier": VERIFIER_VERSION,
                "fields": outcome.verified_fields,
                "summary_provider": assisted.get("provider"),
            },
        )
        published += 1
        log_event(
            logger,
            logging.INFO,
            "publish_candidate_published",
            result_id=candidate["result_id"],
            review_id=review_id,
            fields=sorted(outcome.verified_fields),
        )

    log_event(
        logger,
        logging.INFO,
        "publish_batch_completed",
        verifier=VERIFIER_VERSION,
        published=published,
        kept_for_review=kept,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
