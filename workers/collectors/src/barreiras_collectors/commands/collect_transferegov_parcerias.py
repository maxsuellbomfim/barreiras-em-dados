"""Preserva propostas, distribuicoes e parcerias do Transferegov."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from ..collection_control import (
    CollectionControl,
    CollectionOutcome,
    build_execution_idempotency_key,
)
from ..connectors.transferegov import (
    DEFAULT_PAGE_SIZE,
    SOURCE_CODE,
    TransferegovError,
    TransferegovPage,
    fetch_partnerships_page,
    fetch_proposals_page,
    fetch_resource_distributions_page,
)
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import (
    TRANSFEREGOV_COLLECTOR_VERSION,
    TRANSFEREGOV_PARSER_VERSION,
    TransferegovPersistenceService,
)
from ..resilience import CircuitBreaker
from ..settings import CollectorSettings, PersistenceSettings
from .pncp_runtime import build_authenticated_object_store

MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
MAX_PAGES_PER_RESOURCE = 100


@dataclass(frozen=True)
class TransferegovCollectionSummary:
    proposal_records: int
    related_records: int
    preserved_pages: int
    inserted_records: int
    existing_records: int

    @property
    def observed_records(self) -> int:
        return self.proposal_records + self.related_records

    @property
    def outcome(self) -> CollectionOutcome:
        if self.proposal_records == 0:
            return CollectionOutcome.EMPTY
        return CollectionOutcome.COMPLETE


def execute_controlled_transferegov(
    *,
    control: CollectionControl,
    operation: Callable[[], TransferegovCollectionSummary],
) -> TransferegovCollectionSummary:
    """Registra a tentativa antes de autenticar ou consultar a fonte."""
    with control:
        summary = operation()
        control.complete(
            outcome=summary.outcome,
            observed_records=summary.observed_records,
            checkpoint={
                "preserved_pages": summary.preserved_pages,
                "proposal_records": summary.proposal_records,
            },
            metrics={
                "proposal_records": summary.proposal_records,
                "related_records": summary.related_records,
                "preserved_pages": summary.preserved_pages,
                "inserted_records": summary.inserted_records,
                "existing_records": summary.existing_records,
            },
        )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preserva o retrato oficial das propostas destinadas a Barreiras "
            "e seus recursos relacionados, sem calcular totais financeiros."
        )
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help="Quantidade solicitada por pagina da API oficial.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=MAX_PAGES_PER_RESOURCE,
        help="Limite de seguranca por recurso e proposta.",
    )
    arguments = parser.parse_args(argv)
    if arguments.page_size < 1:
        parser.error("--page-size deve ser positivo.")
    if arguments.max_pages < 1:
        parser.error("--max-pages deve ser positivo.")

    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    if persistence_settings.mode != "postgres-supabase":
        raise RuntimeError(
            "A coleta Transferegov requer PERSISTENCE_MODE=postgres-supabase."
        )
    if persistence_settings.database_url is None:
        raise RuntimeError("Configuracao de banco incompleta.")

    repository = PostgresCollectionRepository.from_dsn(
        persistence_settings.database_url
    )
    today = datetime.now(MUNICIPAL_TIMEZONE).date()
    control = CollectionControl(
        repository=repository,
        source_code=SOURCE_CODE,
        endpoint_code="propostas-barreiras",
        idempotency_key=build_execution_idempotency_key(
            "transferegov-parcerias"
        ),
        collector_version=TRANSFEREGOV_COLLECTOR_VERSION,
        parser_version=TRANSFEREGOV_PARSER_VERSION,
        partition_key=f"snapshot:{today.isoformat()}",
        period_start=today,
        period_end=today,
    )
    logger = logging.getLogger(__name__)

    def operation() -> TransferegovCollectionSummary:
        service = TransferegovPersistenceService(
            object_store=build_authenticated_object_store(
                persistence_settings
            ),
            repository=repository,
        )
        return _collect_snapshot(
            service=service,
            page_size=arguments.page_size,
            max_pages=arguments.max_pages,
            logger=logger,
        )

    summary = execute_controlled_transferegov(
        control=control,
        operation=operation,
    )
    log_event(
        logger,
        logging.INFO,
        "collector_transferegov_completed",
        source=SOURCE_CODE,
        coverage_status=summary.outcome.value,
        proposal_records=summary.proposal_records,
        related_records=summary.related_records,
        preserved_pages=summary.preserved_pages,
        inserted_records=summary.inserted_records,
        existing_records=summary.existing_records,
    )
    return 0


def _collect_snapshot(
    *,
    service: TransferegovPersistenceService,
    page_size: int,
    max_pages: int,
    logger: logging.Logger,
) -> TransferegovCollectionSummary:
    breaker = CircuitBreaker(failure_threshold=4)
    proposal_records = related_records = 0
    preserved_pages = inserted_records = existing_records = 0
    proposal_ids: set[int] = set()

    def preserve(page: TransferegovPage) -> None:
        nonlocal preserved_pages, inserted_records, existing_records
        result = service.persist(page)
        preserved_pages += 1
        inserted_records += result.inserted_records
        existing_records += result.existing_records
        log_event(
            logger,
            logging.INFO,
            "collector_transferegov_page_persisted",
            source=SOURCE_CODE,
            endpoint=page.endpoint_code,
            page=page.cursor["page"],
            records=len(page.items),
            artifact_hash=page.body_sha256,
            inserted_records=result.inserted_records,
            existing_records=result.existing_records,
        )

    proposal_pages = _fetch_all_pages(
        fetch=lambda number: fetch_proposals_page(
            page=number,
            page_size=page_size,
            circuit_breaker=breaker,
            logger=logger,
        ),
        max_pages=max_pages,
        resource="propostas",
    )
    for page in proposal_pages:
        preserve(page)
        proposal_records += len(page.items)
        for item in page.items:
            identifier = item["id_proposta"]
            if identifier in proposal_ids:
                raise TransferegovError(
                    f"A proposta {identifier} apareceu mais de uma vez no retrato."
                )
            proposal_ids.add(identifier)

    validated_ids = frozenset(proposal_ids)
    for proposal_id in sorted(validated_ids):
        related_fetchers = (
            (
                "distribuicoes",
                lambda number, proposal_id=proposal_id: (
                    fetch_resource_distributions_page(
                        proposal_id=proposal_id,
                        validated_proposal_ids=validated_ids,
                        page=number,
                        page_size=page_size,
                        circuit_breaker=breaker,
                        logger=logger,
                    )
                ),
            ),
            (
                "parcerias",
                lambda number, proposal_id=proposal_id: fetch_partnerships_page(
                    proposal_id=proposal_id,
                    validated_proposal_ids=validated_ids,
                    page=number,
                    page_size=page_size,
                    circuit_breaker=breaker,
                    logger=logger,
                ),
            ),
        )
        for resource, fetcher in related_fetchers:
            pages = _fetch_all_pages(
                fetch=fetcher,
                max_pages=max_pages,
                resource=f"{resource}:{proposal_id}",
            )
            for page in pages:
                preserve(page)
                related_records += len(page.items)

    return TransferegovCollectionSummary(
        proposal_records=proposal_records,
        related_records=related_records,
        preserved_pages=preserved_pages,
        inserted_records=inserted_records,
        existing_records=existing_records,
    )


def _fetch_all_pages(
    *,
    fetch: Callable[[int], TransferegovPage],
    max_pages: int,
    resource: str,
) -> Iterator[TransferegovPage]:
    page_number = 1
    while page_number <= max_pages:
        page = fetch(page_number)
        yield page
        if page.total_pages == 0 or page_number >= page.total_pages:
            return
        page_number += 1
    raise TransferegovError(
        f"A paginacao de {resource} excedeu o limite seguro de {max_pages}."
    )


if __name__ == "__main__":
    raise SystemExit(main())
