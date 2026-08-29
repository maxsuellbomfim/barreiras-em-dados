"""Reconcilia a cobertura privada dos campos contratuais TCM-BA."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from barreiras_collectors.logging import log_event
from barreiras_collectors.settings import CollectorSettings, PostgresSettings

from ..tcm_ba_contract_field_repository import (
    TcmBaContractFieldExtractionRepository,
)
from ..tcm_ba_contract_fields import TcmBaContractFieldCoverage


def coverage_exit_code(coverage: TcmBaContractFieldCoverage) -> int:
    return 0 if coverage.complete else 1


def main(_argv: Sequence[str] | None = None) -> int:
    collector_settings = CollectorSettings.from_env()
    postgres = PostgresSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    repository = TcmBaContractFieldExtractionRepository.from_dsn(
        postgres.database_url
    )
    coverage = repository.contract_field_coverage()
    exit_code = coverage_exit_code(coverage)
    log_event(
        logging.getLogger(__name__),
        logging.INFO if exit_code == 0 else logging.ERROR,
        "tcm_ba_contract_field_coverage",
        eligible_artifacts=coverage.eligible_artifacts,
        processed_artifacts=coverage.processed_artifacts,
        eligible_segments=coverage.eligible_segments,
        processed_segments=coverage.processed_segments,
        observed_fields=coverage.observed_fields,
        no_fields_observed=coverage.no_fields_observed,
        missing_segments=coverage.missing_segments,
        duplicate_results=coverage.duplicate_results,
        invalid_results=coverage.invalid_results,
        open_failures=coverage.open_failures,
        gate="PASS" if exit_code == 0 else "BLOCK",
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
