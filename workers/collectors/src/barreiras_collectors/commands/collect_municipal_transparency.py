"""Preserva uma janela limitada das APIs de dados abertos municipais."""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Sequence
from itertools import islice

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
from ..persistence.service import MunicipalTransparencyPersistenceService
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
    parser.add_argument("--offset", type=int, default=0)
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
    if args.offset < 0:
        parser.error("--offset não pode ser negativo.")
    if not 1 <= args.max_pages <= 1000:
        parser.error("--max-pages deve estar entre 1 e 1000.")

    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=collector_settings.log_level,
        format="%(message)s",
        force=True,
    )
    logger = logging.getLogger(__name__)
    client = _cloud_client(persistence_settings)
    source_code, base_url = SOURCE_CONFIG[args.source]
    service = MunicipalTransparencyPersistenceService(
        object_store=SupabaseStorageObjectStore(
            client.storage.from_(persistence_settings.raw_artifacts_bucket)
        ),
        repository=PostgresCollectionRepository.from_dsn(
            persistence_settings.database_url
        ),
    )

    document_client = None
    if args.download_documents:
        if args.resource not in FINANCIAL_DOCUMENT_RESOURCES:
            parser.error(
                "--download-documents so pode ser usado em recurso financeiro."
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
        resource=args.resource,
        limit=args.limit,
        offset=args.offset,
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
    try:
        for page in islice(pages, args.max_pages):
            result = service.persist(page)
            persisted_pages += 1
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
                            endpoint_code="dados-abertos-api",
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
                        if not args.allow_partial:
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
        if not args.allow_partial or persisted_pages == 0:
            raise
        log_event(
            logger,
            logging.WARNING,
            "collector_municipal_transparency_partial",
            source=source_code,
            resource=args.resource,
            pages=persisted_pages,
            inserted_records=inserted_records,
            existing_records=existing_records,
            max_pages=args.max_pages,
            error=str(error),
            documents_persisted=persisted_documents,
            documents_failed=failed_documents,
        )
        return 0

    log_event(
        logger,
        logging.INFO,
        "collector_municipal_transparency_completed",
        source=source_code,
        resource=args.resource,
        pages=persisted_pages,
        inserted_records=inserted_records,
        existing_records=existing_records,
        max_pages=args.max_pages,
        documents_persisted=persisted_documents,
        documents_failed=failed_documents,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
