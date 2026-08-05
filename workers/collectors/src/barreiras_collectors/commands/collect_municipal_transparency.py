"""Preserva uma janela limitada das APIs de dados abertos municipais."""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from itertools import islice
from zoneinfo import ZoneInfo

from ..collection_control import (
    CollectionControl,
    CollectionOutcome,
    build_execution_idempotency_key,
)
from ..connectors.gazette_documents import MunicipalTransparencyDocumentClient
from ..connectors.municipal_transparency import (
    CAMARA_BASE_URL,
    PREFEITURA_BASE_URL,
    MunicipalTransparencyAvailabilityError,
    iter_resource_pages,
)
from ..connectors.querido_diario import QueridoDiarioError
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import (
    MUNICIPAL_TRANSPARENCY_COLLECTOR_VERSION,
    MunicipalTransparencyPersistenceService,
)
from ..persistence.storage import SupabaseStorageObjectStore
from ..resilience import CircuitOpenError
from ..settings import CollectorSettings, PersistenceSettings

SOURCE_CONFIG = {
    "prefeitura": (
        "prefeitura-barreiras-transparencia",
        PREFEITURA_BASE_URL,
    ),
    "camara": (
        "camara-barreiras-transparencia",
        CAMARA_BASE_URL,
    ),
}
DEFAULT_RESOURCE = "pdc-resumo-execucao-da-receita"
MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
FINANCIAL_DOCUMENT_RESOURCES = frozenset(
    {
        "pdc-receita-tributaria",
        "pdc-recursos-extraordinarios",
        "pdc-resumo-execucao-da-receita",
        "pdc-resumo-execucao-da-despesa",
        "pdc-transferencia",
        "pdc-emendas-parlamentares-receitas",
        "rreo",
        "rgf",
    }
)
LEGISLATIVE_ENDPOINTS = {
    "leis": "leis-api",
    "indicacoes": "indicacoes-api",
}


def resolve_endpoint_code(source: str, resource: str) -> str:
    """Relaciona recursos legislativos aos endpoints inventariados."""

    if source == "camara":
        return LEGISLATIVE_ENDPOINTS.get(resource, "dados-abertos-api")
    return "dados-abertos-api"


@dataclass(frozen=True)
class MunicipalTransparencyCollectionSummary:
    pages: int
    inserted_records: int
    existing_records: int
    documents_persisted: int
    documents_failed: int
    pagination_capped: bool
    availability_partial: bool
    next_offset: int
    start_offset: int = 0

    @property
    def observed_records(self) -> int:
        return self.inserted_records + self.existing_records

    @property
    def outcome(self) -> CollectionOutcome:
        if self.documents_failed or self.pagination_capped or self.availability_partial:
            return CollectionOutcome.PARTIAL
        if self.observed_records == 0:
            return CollectionOutcome.EMPTY
        return CollectionOutcome.COMPLETE


def execute_controlled_municipal_transparency(
    *,
    control: CollectionControl,
    operation: Callable[[], MunicipalTransparencyCollectionSummary],
) -> MunicipalTransparencyCollectionSummary:
    """Registra a tentativa antes da autenticação e da primeira requisição."""
    with control:
        summary = operation()
        control.complete(
            outcome=summary.outcome,
            observed_records=summary.observed_records,
            checkpoint={"next_offset": summary.next_offset},
            metrics={
                "pages": summary.pages,
                "inserted_records": summary.inserted_records,
                "existing_records": summary.existing_records,
                "documents_persisted": summary.documents_persisted,
                "documents_failed": summary.documents_failed,
                "pagination_capped": summary.pagination_capped,
                "availability_partial": summary.availability_partial,
                "start_offset": summary.start_offset,
            },
        )
    return summary


def resolve_resume_offset(
    *,
    explicit_offset: int | None,
    checkpoint: Mapping[str, object] | None,
) -> int:
    """Prefere intervenção explícita e aceita só checkpoint inteiro não negativo."""
    if explicit_offset is not None:
        return explicit_offset
    value = checkpoint.get("next_offset") if checkpoint else None
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def _bounded_env_int(name: str, *, default: int, minimum: int, maximum: int) -> int:
    raw_value = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as error:
        raise RuntimeError(f"{name} deve ser inteiro.") from error
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} deve estar entre {minimum} e {maximum}.")
    return value


def _cloud_client(settings: PersistenceSettings):
    if settings.mode != "postgres-supabase":
        raise RuntimeError(
            "A coleta de transparência municipal requer "
            "PERSISTENCE_MODE=postgres-supabase."
        )
    required = (
        settings.database_url,
        settings.supabase_url,
        settings.supabase_publishable_key,
        settings.supabase_workload_email,
        settings.supabase_workload_password,
        settings.raw_artifacts_bucket,
    )
    if any(value is None for value in required):
        raise RuntimeError("Configuração de nuvem incompleta.")
    try:
        from supabase import create_client
    except ImportError as error:
        raise RuntimeError(
            "Instale as dependências opcionais 'postgres' e 'storage'."
        ) from error

    client = create_client(settings.supabase_url, settings.supabase_publishable_key)
    try:
        authentication = client.auth.sign_in_with_password(
            {
                "email": settings.supabase_workload_email,
                "password": settings.supabase_workload_password,
            }
        )
    except Exception as error:
        raise RuntimeError(
            "Falha ao autenticar a identidade técnica municipal."
        ) from error
    if authentication.session is None or authentication.user is None:
        raise RuntimeError("O Storage não forneceu uma sessão autenticada.")
    return client


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preserva uma janela limitada da Prefeitura ou Câmara de Barreiras "
            "como evidência bruta, sem calcular valores."
        )
    )
    parser.add_argument("--source", choices=sorted(SOURCE_CONFIG), default="prefeitura")
    parser.add_argument("--resource", default=DEFAULT_RESOURCE)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--offset", type=int, default=None)
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="aceita indisponibilidade após persistir ao menos uma página",
    )
    parser.add_argument(
        "--download-documents",
        action="store_true",
        help="baixa e preserva PDFs oficiais apontados pelos registros financeiros",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 500:
        parser.error("--limit deve estar entre 1 e 500.")
    if args.offset is not None and args.offset < 0:
        parser.error("--offset não pode ser negativo.")
    if not 1 <= args.max_pages <= 1000:
        parser.error("--max-pages deve estar entre 1 e 1000.")
    if args.download_documents and args.resource not in FINANCIAL_DOCUMENT_RESOURCES:
        parser.error("--download-documents só pode ser usado em recurso financeiro.")

    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=collector_settings.log_level,
        format="%(message)s",
        force=True,
    )
    logger = logging.getLogger(__name__)
    source_code, base_url = SOURCE_CONFIG[args.source]
    endpoint_code = resolve_endpoint_code(args.source, args.resource)
    if persistence_settings.database_url is None:
        raise RuntimeError("Configuração de banco incompleta.")
    repository = PostgresCollectionRepository.from_dsn(
        persistence_settings.database_url
    )
    snapshot_date = datetime.now(MUNICIPAL_TIMEZONE).date()
    resource_namespace = sha256(args.resource.encode("utf-8")).hexdigest()[:12]
    partition_key = (
        f"snapshot:{args.resource}:limit:{args.limit}:pages:{args.max_pages}"
    )
    control = CollectionControl(
        repository=repository,
        source_code=source_code,
        endpoint_code=endpoint_code,
        idempotency_key=build_execution_idempotency_key(
            f"municipal-{resource_namespace}"
        ),
        collector_version=MUNICIPAL_TRANSPARENCY_COLLECTOR_VERSION,
        parser_version="municipal-transparency-api-response/1.0.0",
        partition_key=partition_key,
        period_start=snapshot_date,
        period_end=snapshot_date,
    )

    def operation() -> MunicipalTransparencyCollectionSummary:
        checkpoint = repository.collection_partition_checkpoint(
            source_code=source_code,
            endpoint_code=endpoint_code,
            partition_key=partition_key,
        )
        effective_offset = resolve_resume_offset(
            explicit_offset=args.offset,
            checkpoint=checkpoint,
        )
        client = _cloud_client(persistence_settings)
        service = MunicipalTransparencyPersistenceService(
            object_store=SupabaseStorageObjectStore(
                client.storage.from_(persistence_settings.raw_artifacts_bucket)
            ),
            repository=repository,
        )
        return _collect_resource(
            service=service,
            source_code=source_code,
            endpoint_code=endpoint_code,
            base_url=base_url,
            resource=args.resource,
            limit=args.limit,
            offset=effective_offset,
            max_pages=args.max_pages,
            allow_partial=args.allow_partial,
            download_documents=args.download_documents,
            collector_settings=collector_settings,
            logger=logger,
        )

    summary = execute_controlled_municipal_transparency(
        control=control,
        operation=operation,
    )

    log_event(
        logger,
        logging.INFO,
        "collector_municipal_transparency_completed",
        source=source_code,
        resource=args.resource,
        pages=summary.pages,
        inserted_records=summary.inserted_records,
        existing_records=summary.existing_records,
        max_pages=args.max_pages,
        documents_persisted=summary.documents_persisted,
        documents_failed=summary.documents_failed,
        pagination_capped=summary.pagination_capped,
        availability_partial=summary.availability_partial,
        start_offset=summary.start_offset,
        next_offset=summary.next_offset,
        coverage_status=summary.outcome.value,
    )
    return 0


def _collect_resource(
    *,
    service: MunicipalTransparencyPersistenceService,
    source_code: str,
    endpoint_code: str,
    base_url: str,
    resource: str,
    limit: int,
    offset: int,
    max_pages: int,
    allow_partial: bool,
    download_documents: bool,
    collector_settings: CollectorSettings,
    logger: logging.Logger,
) -> MunicipalTransparencyCollectionSummary:
    document_client = None
    if download_documents:
        if resource not in FINANCIAL_DOCUMENT_RESOURCES:
            raise ValueError(
                "download de documentos só é permitido em recurso financeiro."
            )
        document_client = MunicipalTransparencyDocumentClient(
            max_document_bytes=_bounded_env_int(
                "MUNICIPAL_TRANSPARENCY_MAX_DOCUMENT_BYTES",
                default=64 * 1024 * 1024,
                minimum=1024,
                maximum=128 * 1024 * 1024,
            ),
            requests_per_minute=_bounded_env_int(
                "MUNICIPAL_TRANSPARENCY_DOCUMENT_REQUESTS_PER_MINUTE",
                default=6,
                minimum=1,
                maximum=30,
            ),
            timeout_seconds=collector_settings.read_timeout_seconds,
            logger=logger,
        )

    pages = iter_resource_pages(
        base_url=base_url,
        source_code=source_code,
        endpoint_code=endpoint_code,
        resource=resource,
        limit=limit,
        offset=offset,
        requests_per_minute=_bounded_env_int(
            "MUNICIPAL_TRANSPARENCY_REQUESTS_PER_MINUTE",
            default=10,
            minimum=1,
            maximum=60,
        ),
        timeout_seconds=collector_settings.read_timeout_seconds,
        max_body_bytes=_bounded_env_int(
            "MUNICIPAL_TRANSPARENCY_MAX_BODY_BYTES",
            default=16 * 1024 * 1024,
            minimum=1024,
            maximum=64 * 1024 * 1024,
        ),
        logger=logger,
    )
    persisted_pages = 0
    inserted_records = 0
    existing_records = 0
    persisted_documents = 0
    failed_documents = 0
    last_page_size = 0
    availability_partial = False
    try:
        for page in islice(pages, max_pages):
            result = service.persist(page)
            persisted_pages += 1
            last_page_size = len(page.items)
            inserted_records += result.inserted_records
            existing_records += result.existing_records
            if document_client is not None:
                for index, item in enumerate(page.items):
                    document_url = item.get("url")
                    if not isinstance(document_url, str) or not document_url.strip():
                        continue
                    try:
                        document = document_client.fetch(
                            document_url.strip(),
                            role="pdf",
                        )
                        service.persist_document(
                            page_result=result,
                            record=service.record_input(
                                page,
                                index=index,
                                item=item,
                            ),
                            document=document,
                            source_code=source_code,
                            endpoint_code=endpoint_code,
                        )
                        persisted_documents += 1
                    except (
                        CircuitOpenError,
                        OSError,
                        QueridoDiarioError,
                        TimeoutError,
                        ValueError,
                    ) as error:
                        failed_documents += 1
                        log_event(
                            logger,
                            logging.ERROR,
                            "collector_municipal_transparency_document_failed",
                            source=source_code,
                            resource=page.resource,
                            document_url=document_url,
                            error_type=type(error).__name__,
                            error=str(error)[:500],
                        )
                        if not allow_partial:
                            raise
            log_event(
                logger,
                logging.INFO,
                "collector_municipal_transparency_page_persisted",
                source=source_code,
                resource=page.resource,
                page_offset=page.cursor["offset"],
                page_size=len(page.items),
                artifact_hash=page.body_sha256,
                inserted_records=result.inserted_records,
                existing_records=result.existing_records,
                documents_persisted=persisted_documents,
                documents_failed=failed_documents,
            )
    except MunicipalTransparencyAvailabilityError as error:
        if not allow_partial or persisted_pages == 0:
            raise
        availability_partial = True
        log_event(
            logger,
            logging.WARNING,
            "collector_municipal_transparency_partial",
            source=source_code,
            resource=resource,
            pages=persisted_pages,
            inserted_records=inserted_records,
            existing_records=existing_records,
            max_pages=max_pages,
            error=str(error),
            documents_persisted=persisted_documents,
            documents_failed=failed_documents,
        )

    pagination_capped = persisted_pages == max_pages and last_page_size == limit
    next_offset = (
        offset + (persisted_pages * limit)
        if pagination_capped or availability_partial
        else 0
    )
    return MunicipalTransparencyCollectionSummary(
        pages=persisted_pages,
        inserted_records=inserted_records,
        existing_records=existing_records,
        documents_persisted=persisted_documents,
        documents_failed=failed_documents,
        pagination_capped=pagination_capped,
        availability_partial=availability_partial,
        next_offset=next_offset,
        start_offset=offset,
    )


if __name__ == "__main__":
    raise SystemExit(main())
