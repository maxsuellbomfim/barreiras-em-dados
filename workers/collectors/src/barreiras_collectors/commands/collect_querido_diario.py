"""Coleta uma janela curta do Querido Diário e preserva o bruto."""

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
from ..connectors.gazette_documents import (
    GazetteDocumentClient,
    PermanentHttpError,
    SourceContractError,
    SourceUnavailableError,
)
from ..connectors.querido_diario import QueridoDiarioClient
from ..http import ResponseTooLargeError
from ..logging import log_event
from ..persistence.filesystem import FilesystemCollectionRepository
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import COLLECTOR_VERSION, QueridoDiarioPersistenceService
from ..persistence.storage import (
    FilesystemArtifactObjectStore,
    SupabaseStorageObjectStore,
)
from ..resilience import CircuitOpenError, RetryPolicy
from ..settings import CollectorSettings, PersistenceSettings

MAX_WINDOW_DAYS = 7


@dataclass(frozen=True)
class QueridoDiarioCollectionSummary:
    pages: int
    inserted_records: int
    existing_records: int
    documents_persisted: int
    documents_skipped: int
    documents_failed: int

    @property
    def observed_records(self) -> int:
        return self.inserted_records + self.existing_records

    @property
    def outcome(self) -> CollectionOutcome:
        if self.documents_skipped or self.documents_failed:
            return CollectionOutcome.PARTIAL
        if self.observed_records == 0:
            return CollectionOutcome.EMPTY
        return CollectionOutcome.COMPLETE


def execute_controlled_querido_diario(
    *,
    control: CollectionControl,
    operation: Callable[[], QueridoDiarioCollectionSummary],
) -> QueridoDiarioCollectionSummary:
    """Abre o controle antes de autenticação, HTTP e persistência externa."""
    with control:
        summary = operation()
        control.complete(
            outcome=summary.outcome,
            observed_records=summary.observed_records,
            checkpoint={"pages": summary.pages},
            metrics={
                "inserted_records": summary.inserted_records,
                "existing_records": summary.existing_records,
                "documents_persisted": summary.documents_persisted,
                "documents_skipped": summary.documents_skipped,
                "documents_failed": summary.documents_failed,
            },
        )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preserva uma janela curta de metadados do Querido Diário para "
            "Barreiras no modo local ou no adaptador de nuvem configurado."
        )
    )
    parser.add_argument("--since", type=date.fromisoformat, required=True)
    parser.add_argument("--until", type=date.fromisoformat, required=True)
    parser.add_argument("--page-size", type=int, default=100)
    arguments = parser.parse_args(argv)

    if arguments.since > arguments.until:
        parser.error("--since não pode ser posterior a --until.")
    if (arguments.until - arguments.since).days >= MAX_WINDOW_DAYS:
        parser.error(f"A janela inicial não pode exceder {MAX_WINDOW_DAYS} dias.")
    if not 1 <= arguments.page_size <= 100:
        parser.error("--page-size deve estar entre 1 e 100.")

    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    logger = logging.getLogger(__name__)
    repository = None
    if persistence_settings.mode == "postgres-supabase":
        if persistence_settings.database_url is None:
            raise RuntimeError("Configuração de banco incompleta.")
        repository = PostgresCollectionRepository.from_dsn(
            persistence_settings.database_url
        )

    def operation() -> QueridoDiarioCollectionSummary:
        service = _build_persistence_service(
            persistence_settings,
            repository=repository,
        )
        source = QueridoDiarioClient(
            base_url=collector_settings.querido_diario_base_url,
            territory_id=collector_settings.querido_diario_territory_id,
            requests_per_minute=collector_settings.requests_per_minute,
            timeout_seconds=(
                collector_settings.connect_timeout_seconds
                + collector_settings.read_timeout_seconds
            ),
            retry_policy=RetryPolicy(max_attempts=collector_settings.max_attempts),
        )
        documents_client = GazetteDocumentClient(
            max_document_bytes=collector_settings.max_document_bytes,
            requests_per_minute=collector_settings.requests_per_minute,
            timeout_seconds=(
                collector_settings.connect_timeout_seconds
                + collector_settings.read_timeout_seconds
            ),
            retry_policy=RetryPolicy(max_attempts=collector_settings.max_attempts),
        )
        return _collect_window(
            service=service,
            source=source,
            documents_client=documents_client,
            since=arguments.since,
            until=arguments.until,
            page_size=arguments.page_size,
            max_documents=collector_settings.max_documents_per_run,
            logger=logger,
        )

    if repository is None:
        summary = operation()
    else:
        control = CollectionControl(
            repository=repository,
            source_code="querido-diario",
            endpoint_code="gazettes-api",
            idempotency_key=build_execution_idempotency_key("querido-diario"),
            collector_version=COLLECTOR_VERSION,
            parser_version="querido-diario-gazette-page/1.0.0",
            partition_key=(
                f"published:{arguments.since.isoformat()}:{arguments.until.isoformat()}"
            ),
            period_start=arguments.since,
            period_end=arguments.until,
        )
        summary = execute_controlled_querido_diario(
            control=control,
            operation=operation,
        )

    log_event(
        logger,
        logging.INFO,
        "collector_window_completed",
        source="querido-diario",
        territory_id=collector_settings.querido_diario_territory_id,
        window_start=arguments.since.isoformat(),
        window_end=arguments.until.isoformat(),
        pages=summary.pages,
        inserted_records=summary.inserted_records,
        existing_records=summary.existing_records,
        documents_persisted=summary.documents_persisted,
        documents_skipped=summary.documents_skipped,
        documents_failed=summary.documents_failed,
        coverage_status=summary.outcome.value,
        persistence_mode=persistence_settings.mode,
    )
    return 0


def _collect_window(
    *,
    service: QueridoDiarioPersistenceService,
    source: QueridoDiarioClient,
    documents_client: GazetteDocumentClient,
    since: date,
    until: date,
    page_size: int,
    max_documents: int,
    logger: logging.Logger,
) -> QueridoDiarioCollectionSummary:
    pages = 0
    inserted_records = 0
    existing_records = 0
    documents_persisted = 0
    documents_skipped = 0
    documents_failed = 0
    for page in source.iter_gazette_pages(
        published_since=since,
        published_until=until,
        page_size=page_size,
    ):
        result = service.persist(page)
        pages += 1
        inserted_records += result.inserted_records
        existing_records += result.existing_records
        log_event(
            logger,
            logging.INFO,
            "collector_page_persisted",
            source=page.source_code,
            endpoint=page.endpoint_code,
            artifact_hash=result.sha256,
            object_created=result.object_created,
            inserted_records=result.inserted_records,
            existing_records=result.existing_records,
        )

        raw_records = service.gazette_records(page)
        for record, gazette in zip(raw_records, page.parsed.gazettes, strict=True):
            for role, url in (
                ("txt", gazette.txt_url),
                ("pdf", gazette.url),
            ):
                if not isinstance(url, str) or not url:
                    continue
                if documents_persisted >= max_documents:
                    documents_skipped += 1
                    continue
                try:
                    document = documents_client.fetch(url, role=role)
                    persisted = service.persist_document(
                        page_result=result,
                        record=record,
                        document=document,
                        source_code=page.source_code,
                        endpoint_code=page.endpoint_code,
                    )
                except (
                    CircuitOpenError,
                    OSError,
                    PermanentHttpError,
                    ResponseTooLargeError,
                    SourceContractError,
                    SourceUnavailableError,
                    TimeoutError,
                    ValueError,
                ) as error:
                    documents_failed += 1
                    log_event(
                        logger,
                        logging.WARNING,
                        "collector_document_failed",
                        source=page.source_code,
                        endpoint="gazette-documents",
                        document_role=role,
                        document_url=url,
                        error_type=type(error).__name__,
                        error=str(error)[:500],
                    )
                    continue
                documents_persisted += 1
                log_event(
                    logger,
                    logging.INFO,
                    "collector_document_persisted",
                    source=page.source_code,
                    endpoint="gazette-documents",
                    document_role=role,
                    artifact_hash=persisted.sha256,
                    object_created=persisted.object_created,
                    artifact_created=persisted.artifact_created,
                )

    if documents_skipped:
        # Nunca truncar em silêncio: o replay da mesma janela completa o resto.
        log_event(
            logger,
            logging.WARNING,
            "collector_documents_budget_exhausted",
            source="querido-diario",
            endpoint="gazette-documents",
            skipped_documents=documents_skipped,
            max_documents_per_run=max_documents,
        )

    if documents_failed:
        log_event(
            logger,
            logging.WARNING,
            "collector_documents_partial",
            source="querido-diario",
            endpoint="gazette-documents",
            failed_documents=documents_failed,
            documents_persisted=documents_persisted,
        )

    return QueridoDiarioCollectionSummary(
        pages=pages,
        inserted_records=inserted_records,
        existing_records=existing_records,
        documents_persisted=documents_persisted,
        documents_skipped=documents_skipped,
        documents_failed=documents_failed,
    )


def _build_persistence_service(
    settings: PersistenceSettings,
    *,
    repository: PostgresCollectionRepository | None = None,
) -> QueridoDiarioPersistenceService:
    if settings.mode == "filesystem":
        if settings.local_data_directory is None:
            raise RuntimeError("Diretório local não foi configurado.")
        root = settings.local_data_directory
        return QueridoDiarioPersistenceService(
            object_store=FilesystemArtifactObjectStore(root / "objects"),
            repository=FilesystemCollectionRepository(root / "manifests"),
        )

    if (
        settings.database_url is None
        or settings.supabase_url is None
        or settings.supabase_publishable_key is None
        or settings.supabase_workload_email is None
        or settings.supabase_workload_password is None
        or settings.raw_artifacts_bucket is None
    ):
        raise RuntimeError("Configuração de nuvem incompleta.")
    try:
        from supabase import create_client
    except ImportError as error:
        raise RuntimeError(
            "Instale a dependência opcional 'storage' para executar a coleta."
        ) from error

    supabase_client = create_client(
        settings.supabase_url,
        settings.supabase_publishable_key,
    )
    try:
        authentication = supabase_client.auth.sign_in_with_password(
            {
                "email": settings.supabase_workload_email,
                "password": settings.supabase_workload_password,
            }
        )
    except Exception as error:
        raise RuntimeError(
            "Falha ao autenticar a identidade técnica do Storage."
        ) from error
    if authentication.session is None or authentication.user is None:
        raise RuntimeError("O Storage não forneceu uma sessão autenticada.")

    bucket_client = supabase_client.storage.from_(settings.raw_artifacts_bucket)
    return QueridoDiarioPersistenceService(
        object_store=SupabaseStorageObjectStore(bucket_client),
        repository=(
            repository
            if repository is not None
            else PostgresCollectionRepository.from_dsn(settings.database_url)
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
