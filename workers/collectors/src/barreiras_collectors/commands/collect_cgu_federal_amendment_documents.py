"""Preserva documentos anuais da execução federal de emendas."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from ..collection_control import (
    CollectionControl,
    CollectionOutcome,
    build_execution_idempotency_key,
)
from ..connectors.cgu_federal_amendment_documents import (
    ENDPOINT_CODE,
    SOURCE_CODE,
    fetch_cgu_federal_amendment_documents,
)
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import (
    CGU_FEDERAL_AMENDMENT_DOCUMENT_COLLECTOR_VERSION,
    CGU_FEDERAL_AMENDMENT_DOCUMENT_PARSER_VERSION,
    CGUFederalAmendmentDocumentPersistenceService,
)
from ..settings import CollectorSettings, PersistenceSettings
from .pncp_runtime import build_authenticated_object_store

MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
EXECUTION_NAMESPACE = "cgu-federal-amendment-documents"


@dataclass(frozen=True)
class CGUFederalAmendmentDocumentCollectionSummary:
    archive_year: int
    documents: int
    amendments: int
    authors: int
    payments: int
    archive_bytes: int
    inserted_records: int
    existing_records: int
    archive_sha256: str
    source_etag: str


def build_cgu_document_execution_key(
    archive_year: int,
    *,
    environment: Mapping[str, str] | None = None,
) -> str:
    return build_execution_idempotency_key(
        f"{EXECUTION_NAMESPACE}-{archive_year}",
        environment=environment,
    )


def execute_controlled_cgu_document_collection(
    *,
    control: CollectionControl,
    operation: Callable[[], CGUFederalAmendmentDocumentCollectionSummary],
) -> CGUFederalAmendmentDocumentCollectionSummary:
    with control:
        summary = operation()
        control.complete(
            outcome=(
                CollectionOutcome.COMPLETE
                if summary.documents > 0
                else CollectionOutcome.EMPTY
            ),
            observed_records=summary.documents,
            checkpoint={
                "archive_year": summary.archive_year,
                "archive_sha256": summary.archive_sha256,
                "source_etag": summary.source_etag,
            },
            metrics={
                "archive_year": summary.archive_year,
                "documents": summary.documents,
                "amendments": summary.amendments,
                "authors": summary.authors,
                "payments": summary.payments,
                "archive_bytes": summary.archive_bytes,
                "inserted_records": summary.inserted_records,
                "existing_records": summary.existing_records,
                "archive_sha256": summary.archive_sha256,
                "source_etag": summary.source_etag,
            },
        )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    collected_on = datetime.now(MUNICIPAL_TIMEZONE).date()
    parser = argparse.ArgumentParser(
        description=(
            "Preserva os arquivos anuais de documentos de emendas da CGU "
            "e materializa apenas o IBGE 2903201."
        )
    )
    parser.add_argument("--year-from", type=int, default=2021)
    parser.add_argument("--year-to", type=int, default=collected_on.year)
    args = parser.parse_args(argv)
    if args.year_from < 2021:
        parser.error("year-from deve ser igual ou posterior a 2021")
    if args.year_to < args.year_from or args.year_to > collected_on.year:
        parser.error("intervalo anual documental inválido")

    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    if persistence_settings.mode != "postgres-supabase":
        raise RuntimeError(
            "Os documentos federais requerem PERSISTENCE_MODE=postgres-supabase."
        )
    if persistence_settings.database_url is None:
        raise RuntimeError("Configuração de banco incompleta.")

    repository = PostgresCollectionRepository.from_dsn(
        persistence_settings.database_url
    )
    object_store = build_authenticated_object_store(persistence_settings)
    total_documents = 0
    for archive_year in range(args.year_from, args.year_to + 1):
        control = CollectionControl(
            repository=repository,
            source_code=SOURCE_CODE,
            endpoint_code=ENDPOINT_CODE,
            idempotency_key=build_cgu_document_execution_key(archive_year),
            collector_version=(
                CGU_FEDERAL_AMENDMENT_DOCUMENT_COLLECTOR_VERSION
            ),
            parser_version=CGU_FEDERAL_AMENDMENT_DOCUMENT_PARSER_VERSION,
            partition_key=f"federal-amendment-documents:{archive_year}:2903201",
            period_start=date(archive_year, 1, 1),
            period_end=date(archive_year, 12, 31),
        )

        def operation(
            year: int = archive_year,
        ) -> CGUFederalAmendmentDocumentCollectionSummary:
            snapshot = fetch_cgu_federal_amendment_documents(
                year,
                logger=logging.getLogger(__name__),
            )
            result = CGUFederalAmendmentDocumentPersistenceService(
                object_store=object_store,
                repository=repository,
            ).persist(snapshot)
            return CGUFederalAmendmentDocumentCollectionSummary(
                archive_year=year,
                documents=len(snapshot.items),
                amendments=len(
                    {str(item["amendment_code"]) for item in snapshot.items}
                ),
                authors=len(
                    {str(item["author_name"]) for item in snapshot.items}
                ),
                payments=sum(
                    item["expense_stage"] == "payment"
                    for item in snapshot.items
                ),
                archive_bytes=snapshot.body_size_bytes,
                inserted_records=result.inserted_records,
                existing_records=result.existing_records,
                archive_sha256=result.sha256,
                source_etag=snapshot.source_etag,
            )

        summary = execute_controlled_cgu_document_collection(
            control=control,
            operation=operation,
        )
        total_documents += summary.documents
        log_event(
            logging.getLogger(__name__),
            logging.INFO,
            "collector_cgu_federal_amendment_documents_year_completed",
            source=SOURCE_CODE,
            archive_year=summary.archive_year,
            documents=summary.documents,
            amendments=summary.amendments,
            authors=summary.authors,
            payments=summary.payments,
            inserted_records=summary.inserted_records,
            existing_records=summary.existing_records,
            artifact_hash=summary.archive_sha256,
            source_etag=summary.source_etag,
        )
    log_event(
        logging.getLogger(__name__),
        logging.INFO,
        "collector_cgu_federal_amendment_documents_completed",
        source=SOURCE_CODE,
        year_from=args.year_from,
        year_to=args.year_to,
        documents=total_documents,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
