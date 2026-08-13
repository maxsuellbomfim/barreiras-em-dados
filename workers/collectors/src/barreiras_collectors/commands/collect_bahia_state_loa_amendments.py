"""Preserva anexos oficiais anuais da LOA com emendas estaduais."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date

from ..collection_control import (
    CollectionControl,
    CollectionOutcome,
    build_execution_idempotency_key,
)
from ..connectors.bahia_state_loa_amendments import (
    BLOCKED_YEAR_REASONS,
    ENDPOINT_CODE,
    SOURCE_CODE,
    fetch_state_loa_amendment_annex,
)
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import (
    BAHIA_STATE_LOA_ANNEX_COLLECTOR_VERSION,
    BAHIA_STATE_LOA_ANNEX_PARSER_VERSION,
    BahiaStateLoaAmendmentAnnexPersistenceService,
)
from ..settings import CollectorSettings, PersistenceSettings
from .pncp_runtime import build_authenticated_object_store


@dataclass(frozen=True)
class StateLoaAnnexCollectionSummary:
    fiscal_year: int
    annex_code: str
    status: str
    document_bytes: int
    inserted_records: int
    existing_records: int
    body_sha256: str


def execute_controlled_state_loa_year(
    *,
    year: int,
    control: CollectionControl,
    operation: Callable[[], StateLoaAnnexCollectionSummary],
) -> StateLoaAnnexCollectionSummary:
    """Fecha cada ano como completo ou bloqueado, nunca como zero inferido."""
    with control:
        blocked_reason = BLOCKED_YEAR_REASONS.get(year)
        if blocked_reason:
            summary = StateLoaAnnexCollectionSummary(
                fiscal_year=year,
                annex_code="III",
                status="blocked",
                document_bytes=0,
                inserted_records=0,
                existing_records=0,
                body_sha256="",
            )
            control.complete(
                outcome=CollectionOutcome.BLOCKED,
                observed_records=0,
                checkpoint={
                    "fiscal_year": year,
                    "budget_stage": "authorized",
                    "territorial_scope": "municipality_explicit",
                    "source_document_status": "official_link_points_to_wrong_year",
                },
                metrics={"documents_preserved": 0},
                block_reason=blocked_reason,
            )
            return summary

        summary = operation()
        if summary.fiscal_year != year or summary.status != "complete":
            raise RuntimeError("O resultado anual da LOA diverge da particao.")
        control.complete(
            outcome=CollectionOutcome.COMPLETE,
            observed_records=1,
            checkpoint={
                "fiscal_year": year,
                "annex_code": summary.annex_code,
                "budget_stage": "authorized",
                "territorial_scope": "municipality_explicit",
                "artifact_sha256": summary.body_sha256,
            },
            metrics={
                "documents_preserved": 1,
                "document_bytes": summary.document_bytes,
                "inserted_records": summary.inserted_records,
                "existing_records": summary.existing_records,
            },
        )
        return summary


def _years(year_from: int, year_to: int) -> tuple[int, ...]:
    if year_from > year_to or year_from < 2021 or year_to > 2026:
        raise ValueError("O intervalo da LOA deve estar entre 2021 e 2026.")
    return tuple(range(year_from, year_to + 1))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preserva PDFs oficiais da LOA da Bahia com municipio e autor; "
            "nao extrai nem soma valores nesta etapa."
        )
    )
    parser.add_argument("--year-from", type=int, default=2021)
    parser.add_argument("--year-to", type=int, default=2026)
    args = parser.parse_args(argv)
    requested_years = _years(args.year_from, args.year_to)

    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    if persistence_settings.mode != "postgres-supabase":
        raise RuntimeError(
            "Os anexos da LOA requerem PERSISTENCE_MODE=postgres-supabase."
        )
    if persistence_settings.database_url is None:
        raise RuntimeError("Configuracao de banco incompleta.")

    repository = PostgresCollectionRepository.from_dsn(
        persistence_settings.database_url
    )
    object_store = None
    summaries: list[StateLoaAnnexCollectionSummary] = []
    errors: list[tuple[int, BaseException]] = []
    for year in requested_years:
        control = CollectionControl(
            repository=repository,
            source_code=SOURCE_CODE,
            endpoint_code=ENDPOINT_CODE,
            idempotency_key=build_execution_idempotency_key(
                f"bahia-loa-{year}"
            ),
            collector_version=BAHIA_STATE_LOA_ANNEX_COLLECTOR_VERSION,
            parser_version=BAHIA_STATE_LOA_ANNEX_PARSER_VERSION,
            partition_key=f"loa-annex:{year}",
            period_start=date(year, 1, 1),
            period_end=date(year, 12, 31),
        )

        def operation(active_year: int = year) -> StateLoaAnnexCollectionSummary:
            nonlocal object_store
            if object_store is None:
                object_store = build_authenticated_object_store(
                    persistence_settings
                )
            snapshot = fetch_state_loa_amendment_annex(
                active_year,
                logger=logging.getLogger(__name__),
            )
            result = BahiaStateLoaAmendmentAnnexPersistenceService(
                object_store=object_store,
                repository=repository,
            ).persist(snapshot)
            return StateLoaAnnexCollectionSummary(
                fiscal_year=active_year,
                annex_code=snapshot.annex_code,
                status="complete",
                document_bytes=snapshot.body_size_bytes,
                inserted_records=result.inserted_records,
                existing_records=result.existing_records,
                body_sha256=snapshot.body_sha256,
            )

        try:
            summary = execute_controlled_state_loa_year(
                year=year,
                control=control,
                operation=operation,
            )
            summaries.append(summary)
            log_event(
                logging.getLogger(__name__),
                logging.INFO,
                "collector_bahia_state_loa_year_completed",
                source=SOURCE_CODE,
                fiscal_year=year,
                coverage_status=summary.status,
                annex_code=summary.annex_code,
                document_bytes=summary.document_bytes,
                artifact_hash=summary.body_sha256 or None,
                budget_stage="authorized",
                territorial_scope="municipality_explicit",
            )
        except Exception as error:
            errors.append((year, error))
            log_event(
                logging.getLogger(__name__),
                logging.ERROR,
                "collector_bahia_state_loa_year_failed",
                source=SOURCE_CODE,
                fiscal_year=year,
                error_type=type(error).__name__,
            )

    if errors:
        years = ", ".join(str(year) for year, _error in errors)
        raise RuntimeError(
            f"Falha ao preservar anexos da LOA: {years}"
        ) from errors[0][1]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
