"""Materializa os totais anuais literais da DCA/SICONFI."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from barreiras_collectors.logging import log_event
from barreiras_collectors.settings import CollectorSettings, PersistenceSettings

from ..siconfi_annual_totals import (
    SiconfiAnnualTotalsError,
    normalize_siconfi_annual_snapshot,
)
from ..siconfi_annual_totals_repository import SiconfiAnnualTotalsRepository


@dataclass(frozen=True)
class SiconfiAnnualBatchSummary:
    pending_found: int
    processed: int
    failed: int
    totals_inserted: int
    totals_existing: int


def run_batch(*, repository, limit: int, logger=None) -> SiconfiAnnualBatchSummary:
    log = logger or logging.getLogger(__name__)
    snapshots = repository.pending_snapshots(limit)
    processed = 0
    failed = 0
    inserted = 0
    existing = 0
    for snapshot in snapshots:
        try:
            totals = normalize_siconfi_annual_snapshot(snapshot)
            result = repository.persist_totals(snapshot, totals)
        except Exception as error:
            failed += 1
            error_code = (
                "parser_contract"
                if isinstance(error, SiconfiAnnualTotalsError)
                else "processing_error"
            )
            safe_detail = (
                "estrutura anual incompatível com as sete métricas oficiais"
                if error_code == "parser_contract"
                else "falha inesperada na materialização anual"
            )
            try:
                repository.persist_failure(
                    snapshot,
                    error_code=error_code,
                    error_detail=f"{type(error).__name__}: {safe_detail}",
                )
            except Exception:
                log.debug("siconfi_annual_failure_persistence_failed", exc_info=True)
            log_event(
                log,
                logging.ERROR,
                "normalization_siconfi_annual_failed",
                source="siconfi-barreiras",
                fiscal_year=snapshot.fiscal_year,
                artifact_hash=snapshot.artifact_sha256,
                error_code=error_code,
                error_type=type(error).__name__,
            )
            continue
        processed += 1
        inserted += result.totals_inserted
        existing += result.totals_existing
        log_event(
            log,
            logging.INFO,
            "normalization_siconfi_annual_processed",
            source="siconfi-barreiras",
            fiscal_year=snapshot.fiscal_year,
            artifact_hash=snapshot.artifact_sha256,
            totals_inserted=result.totals_inserted,
            totals_existing=result.totals_existing,
        )

    summary = SiconfiAnnualBatchSummary(
        pending_found=len(snapshots),
        processed=processed,
        failed=failed,
        totals_inserted=inserted,
        totals_existing=existing,
    )
    log_event(
        log,
        logging.INFO,
        "normalization_siconfi_annual_batch_completed",
        source="siconfi-barreiras",
        pending_found=summary.pending_found,
        processed=summary.processed,
        failed=summary.failed,
        totals_inserted=summary.totals_inserted,
        totals_existing=summary.totals_existing,
    )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Materializa sete totais anuais literais da DCA/SICONFI."
    )
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 20:
        parser.error("--limit deve estar entre 1 e 20.")

    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    if persistence_settings.mode != "postgres-supabase":
        raise RuntimeError(
            "A normalização SICONFI requer PERSISTENCE_MODE=postgres-supabase."
        )
    if persistence_settings.database_url is None:
        raise RuntimeError("DATABASE_URL não configurada.")

    repository = SiconfiAnnualTotalsRepository.from_dsn(
        persistence_settings.database_url
    )
    summary = run_batch(repository=repository, limit=args.limit)
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
