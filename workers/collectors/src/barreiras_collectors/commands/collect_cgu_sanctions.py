"""Consulta sanções CEIS/CNEP para os fornecedores publicados de Barreiras."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from ..collection_control import (
    CollectionControl,
    CollectionOutcome,
    build_execution_idempotency_key,
)
from ..connectors.cgu_sanctions import (
    ENDPOINT_CODE,
    SOURCE_CODE,
    CGUSanctionError,
    fetch_cgu_supplier_sanctions,
)
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import (
    CGU_SANCTION_COLLECTOR_VERSION,
    CGU_SANCTION_PARSER_VERSION,
    CGUSanctionPersistenceService,
)
from ..settings import CollectorSettings, PersistenceSettings
from .pncp_runtime import build_authenticated_object_store

MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
EXECUTION_NAMESPACE = "cgu-sanctions"
API_KEY_ENV = "TRANSPARENCIA_API_KEY"


@dataclass(frozen=True)
class CGUSanctionCollectionSummary:
    queried_cnpjs: int
    sanctions: int
    sanctioned_cnpjs: int
    skipped_natural_persons: int
    bundle_bytes: int
    inserted_records: int
    existing_records: int
    bundle_sha256: str


def build_sanction_execution_key(
    *, environment: Mapping[str, str] | None = None
) -> str:
    return build_execution_idempotency_key(
        EXECUTION_NAMESPACE,
        environment=environment,
    )


def execute_controlled_sanction_collection(
    *,
    control: CollectionControl,
    operation: Callable[[], CGUSanctionCollectionSummary],
) -> CGUSanctionCollectionSummary:
    with control:
        summary = operation()
        control.complete(
            outcome=(
                CollectionOutcome.COMPLETE
                if summary.queried_cnpjs > 0
                else CollectionOutcome.EMPTY
            ),
            observed_records=summary.sanctions,
            checkpoint={
                "bundle_sha256": summary.bundle_sha256,
                "queried_cnpjs": summary.queried_cnpjs,
            },
            metrics={
                "queried_cnpjs": summary.queried_cnpjs,
                "sanctions": summary.sanctions,
                "sanctioned_cnpjs": summary.sanctioned_cnpjs,
                "skipped_natural_persons": summary.skipped_natural_persons,
                "bundle_bytes": summary.bundle_bytes,
                "inserted_records": summary.inserted_records,
                "existing_records": summary.existing_records,
                "bundle_sha256": summary.bundle_sha256,
            },
        )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    collected_on = datetime.now(MUNICIPAL_TIMEZONE).date()
    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    api_key = os.environ.get(API_KEY_ENV, "")
    if not api_key.strip():
        raise CGUSanctionError(
            "Defina o secret TRANSPARENCIA_API_KEY no ambiente de execução."
        )
    if persistence_settings.mode != "postgres-supabase":
        raise RuntimeError(
            "As sanções federais requerem PERSISTENCE_MODE=postgres-supabase."
        )
    if persistence_settings.database_url is None:
        raise RuntimeError("Configuração de banco incompleta.")

    repository = PostgresCollectionRepository.from_dsn(
        persistence_settings.database_url
    )
    control = CollectionControl(
        repository=repository,
        source_code=SOURCE_CODE,
        endpoint_code=ENDPOINT_CODE,
        idempotency_key=build_sanction_execution_key(),
        collector_version=CGU_SANCTION_COLLECTOR_VERSION,
        parser_version=CGU_SANCTION_PARSER_VERSION,
        partition_key="sanctions:published-suppliers:barreiras",
        period_start=date(2021, 1, 1),
        period_end=collected_on,
    )

    def operation() -> CGUSanctionCollectionSummary:
        cnpjs = sorted(repository.published_supplier_cnpjs())
        snapshot = fetch_cgu_supplier_sanctions(
            cnpjs=cnpjs,
            api_key=api_key,
            logger=logging.getLogger(__name__),
        )
        result = CGUSanctionPersistenceService(
            object_store=build_authenticated_object_store(persistence_settings),
            repository=repository,
        ).persist(snapshot)
        return CGUSanctionCollectionSummary(
            queried_cnpjs=snapshot.queried_cnpjs,
            sanctions=snapshot.total_items,
            sanctioned_cnpjs=snapshot.sanctioned_cnpjs,
            skipped_natural_persons=snapshot.skipped_natural_persons,
            bundle_bytes=snapshot.body_size_bytes,
            inserted_records=result.inserted_records,
            existing_records=result.existing_records,
            bundle_sha256=result.sha256,
        )

    summary = execute_controlled_sanction_collection(
        control=control,
        operation=operation,
    )
    log_event(
        logging.getLogger(__name__),
        logging.INFO,
        "collector_cgu_sanctions_completed",
        source=SOURCE_CODE,
        queried_cnpjs=summary.queried_cnpjs,
        sanctions=summary.sanctions,
        sanctioned_cnpjs=summary.sanctioned_cnpjs,
        skipped_natural_persons=summary.skipped_natural_persons,
        inserted_records=summary.inserted_records,
        existing_records=summary.existing_records,
        artifact_hash=summary.bundle_sha256,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
