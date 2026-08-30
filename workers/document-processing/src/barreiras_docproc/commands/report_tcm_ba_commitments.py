"""Reconcilia a cobertura privada dos candidatos de empenho TCM-BA."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from barreiras_collectors.logging import log_event
from barreiras_collectors.settings import CollectorSettings, PostgresSettings

from ..tcm_ba_commitment_repository import TcmBaCommitmentExtractionRepository
from ..tcm_ba_commitments import TcmBaCommitmentCoverage


def coverage_exit_code(coverage: TcmBaCommitmentCoverage) -> int:
    return 0 if coverage.complete else 1


def main(_argv: Sequence[str] | None = None) -> int:
    collector_settings = CollectorSettings.from_env()
    postgres = PostgresSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    repository = TcmBaCommitmentExtractionRepository.from_dsn(
        postgres.database_url
    )
    coverage = repository.commitment_coverage()
    exit_code = coverage_exit_code(coverage)
    log_event(
        logging.getLogger(__name__),
        logging.INFO if exit_code == 0 else logging.ERROR,
        "tcm_ba_commitment_coverage",
        eligible_artifacts=coverage.eligible_artifacts,
        processed_artifacts=coverage.processed_artifacts,
        candidate_results=coverage.candidate_results,
        complete_candidates=coverage.complete_candidates,
        incomplete_candidates=coverage.incomplete_candidates,
        zero_candidate_artifacts=coverage.zero_candidate_artifacts,
        missing_artifacts=coverage.missing_artifacts,
        duplicate_results=coverage.duplicate_results,
        invalid_results=coverage.invalid_results,
        open_failures=coverage.open_failures,
        gate="PASS" if exit_code == 0 else "BLOCK",
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
