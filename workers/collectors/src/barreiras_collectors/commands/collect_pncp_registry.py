"""Preserva o cadastro do PNCP (órgão e unidades) como bruto verificado."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from ..collection_control import (
    CollectionControl,
    CollectionOutcome,
    build_execution_idempotency_key,
)
from ..connectors.pncp import (
    REGISTRY_RESOURCES,
    SOURCE_CODE,
    fetch_registry_snapshot,
)
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import PncpRegistryPersistenceService
from ..settings import CollectorSettings, PersistenceSettings
from .pncp_runtime import build_authenticated_object_store

MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")


@dataclass(frozen=True)
class PncpRegistryCollectionSummary:
    expected_resources: int
    preserved_resources: int
    created_resources: int

    @property
    def outcome(self) -> CollectionOutcome:
        if self.preserved_resources < self.expected_resources:
            return CollectionOutcome.PARTIAL
        if self.expected_resources == 0:
            return CollectionOutcome.EMPTY
        return CollectionOutcome.COMPLETE


def execute_controlled_pncp_registry(
    *,
    control: CollectionControl,
    operation: Callable[[], PncpRegistryCollectionSummary],
) -> PncpRegistryCollectionSummary:
    """Registra a execução antes da autenticação ou requisição externa."""
    with control:
        summary = operation()
        control.complete(
            outcome=summary.outcome,
            observed_records=summary.preserved_resources,
            checkpoint={
                "expected_resources": summary.expected_resources,
                "preserved_resources": summary.preserved_resources,
            },
            metrics={
                "expected_resources": summary.expected_resources,
                "preserved_resources": summary.preserved_resources,
                "created_resources": summary.created_resources,
            },
        )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preserva as respostas do cadastro do PNCP para Barreiras como "
            "artefatos brutos endereçados por hash."
        )
    )
    parser.parse_args(argv)

    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    if persistence_settings.mode != "postgres-supabase":
        raise RuntimeError(
            "A coleta PNCP requer PERSISTENCE_MODE=postgres-supabase."
        )
    if persistence_settings.database_url is None:
        raise RuntimeError("Configuração de banco incompleta.")
    repository = PostgresCollectionRepository.from_dsn(
        persistence_settings.database_url
    )
    logger = logging.getLogger(__name__)
    today = datetime.now(MUNICIPAL_TIMEZONE).date()
    control = CollectionControl(
        repository=repository,
        source_code=SOURCE_CODE,
        endpoint_code="registry-api",
        idempotency_key=build_execution_idempotency_key("pncp-registry"),
        collector_version=collector_settings.collector_version,
        parser_version="pncp-registry/1.0.0",
        partition_key="registry:current",
        period_start=today,
        period_end=today,
    )

    def operation() -> PncpRegistryCollectionSummary:
        service = PncpRegistryPersistenceService(
            object_store=build_authenticated_object_store(persistence_settings),
            repository=repository,
        )
        return _collect_registry(service=service, logger=logger)

    summary = execute_controlled_pncp_registry(
        control=control,
        operation=operation,
    )
    log_event(
        logger,
        logging.INFO,
        "collector_pncp_registry_completed",
        source=SOURCE_CODE,
        resources=summary.preserved_resources,
        created_resources=summary.created_resources,
        coverage_status=summary.outcome.value,
    )
    return 0


def _collect_registry(
    *,
    service: PncpRegistryPersistenceService,
    logger: logging.Logger,
) -> PncpRegistryCollectionSummary:
    preserved = created = 0
    for resource, url in REGISTRY_RESOURCES:
        snapshot = fetch_registry_snapshot(resource, url, logger=logger)
        result = service.persist(snapshot)
        preserved += 1
        created += int(result.created)
        log_event(
            logger,
            logging.INFO,
            "collector_pncp_snapshot_persisted",
            source=SOURCE_CODE,
            resource=resource,
            artifact_hash=snapshot.body_sha256,
            created=result.created,
        )

    return PncpRegistryCollectionSummary(
        expected_resources=len(REGISTRY_RESOURCES),
        preserved_resources=preserved,
        created_resources=created,
    )


if __name__ == "__main__":
    raise SystemExit(main())
