"""Reconcilia a cobertura privada dos candidatos de empenho TCM-BA."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from barreiras_collectors.logging import log_event
from barreiras_collectors.settings import CollectorSettings, PostgresSettings

from ..tcm_ba_commitment_repository import TcmBaCommitmentExtractionRepository
from ..tcm_ba_commitments import (
    TcmBaCommitmentCoverage,
    TcmBaCommitmentFieldBreakdown,
)


def coverage_exit_code(coverage: TcmBaCommitmentCoverage) -> int:
    return 0 if coverage.complete else 1


def field_breakdown_matches_coverage(
    coverage: TcmBaCommitmentCoverage,
    breakdown: TcmBaCommitmentFieldBreakdown,
) -> bool:
    return (
        breakdown.total_candidates == coverage.candidate_results
        and breakdown.complete_candidates == coverage.complete_candidates
    )


def field_breakdown_payload(
    breakdown: TcmBaCommitmentFieldBreakdown,
) -> dict[str, object]:
    return {
        "total_candidates": breakdown.total_candidates,
        "complete_candidates": breakdown.complete_candidates,
        "spatial_budget_allocations": breakdown.spatial_budget_allocations,
        "missing_field_counts": {
            "issue_date": breakdown.missing_issue_date,
            "creditor_name": breakdown.missing_creditor_name,
            "amount_text": breakdown.missing_amount_text,
            "budget_allocation": breakdown.missing_budget_allocation,
        },
        "missing_combinations": [
            {
                "missing_fields": list(group.missing_fields),
                "candidates": group.candidates,
            }
            for group in breakdown.groups
        ],
    }


def main(_argv: Sequence[str] | None = None) -> int:
    collector_settings = CollectorSettings.from_env()
    postgres = PostgresSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    repository = TcmBaCommitmentExtractionRepository.from_dsn(postgres.database_url)
    coverage = repository.commitment_coverage()
    breakdown = repository.commitment_missing_field_breakdown()
    exit_code = coverage_exit_code(coverage)
    if not field_breakdown_matches_coverage(coverage, breakdown):
        exit_code = 1
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
    log_event(
        logging.getLogger(__name__),
        logging.INFO,
        "tcm_ba_commitment_missing_field_breakdown",
        **field_breakdown_payload(breakdown),
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
