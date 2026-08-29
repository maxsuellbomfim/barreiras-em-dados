"""Deriva páginas canônicas dos PDFs TCM-BA já preservados."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

from barreiras_collectors.logging import log_event
from barreiras_collectors.persistence.storage import SupabaseStorageObjectStore
from barreiras_collectors.settings import CollectorSettings, PersistenceSettings

from ..canonical import CanonicalTextError
from ..postgres import PostgresExtractionRepository
from ..processing import ArtifactMismatchError
from ..tcm_ba_document_text import (
    JOB_TYPE,
    TcmBaDocumentTextService,
    job_idempotency_key,
)


def batch_exit_code(*, pending_found: int, failed: int) -> int:
    """Falha fechado se o estágio não tiver trabalho ou perder um PDF."""
    return 0 if pending_found > 0 and failed == 0 else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Confere o SHA-256 dos PDFs TCM-BA preservados e registra texto "
            "embutido página a página, sem classificar nem publicar valores."
        )
    )
    parser.add_argument("--limit", type=int, default=5)
    arguments = parser.parse_args(argv)
    if not 1 <= arguments.limit <= 50:
        parser.error("--limit deve estar entre 1 e 50.")

    collector_settings = CollectorSettings.from_env()
    persistence = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    if persistence.mode != "postgres-supabase":
        raise RuntimeError(
            "O processamento TCM-BA requer PERSISTENCE_MODE=postgres-supabase."
        )
    if (
        persistence.database_url is None
        or persistence.supabase_url is None
        or persistence.supabase_publishable_key is None
        or persistence.supabase_workload_email is None
        or persistence.supabase_workload_password is None
        or persistence.raw_artifacts_bucket is None
    ):
        raise RuntimeError("Configuração de nuvem incompleta.")

    try:
        from supabase import create_client
    except ImportError as error:
        raise RuntimeError(
            "Instale a dependência opcional 'storage' para processar PDFs."
        ) from error

    client = create_client(
        persistence.supabase_url,
        persistence.supabase_publishable_key,
    )
    try:
        authentication = client.auth.sign_in_with_password(
            {
                "email": persistence.supabase_workload_email,
                "password": persistence.supabase_workload_password,
            }
        )
    except Exception as error:
        raise RuntimeError(
            "Falha ao autenticar a identidade técnica do Storage."
        ) from error
    if authentication.session is None or authentication.user is None:
        raise RuntimeError("O Storage não forneceu uma sessão autenticada.")

    repository = PostgresExtractionRepository.from_dsn(
        persistence.database_url
    )
    service = TcmBaDocumentTextService(
        object_reader=SupabaseStorageObjectStore(
            client.storage.from_(persistence.raw_artifacts_bucket)
        ),
        repository=repository,
    )
    logger = logging.getLogger(__name__)
    pending = repository.pending_tcm_ba_pdf_artifacts(arguments.limit)
    processed = 0
    failed = 0
    pages_total = 0
    pages_with_embedded_text = 0
    pages_awaiting_ocr = 0
    for artifact in pending:
        try:
            result = service.process(artifact)
        except (ArtifactMismatchError, CanonicalTextError) as error:
            failed += 1
            repository.persist_extraction_failure(
                artifact,
                job_type=JOB_TYPE,
                job_idempotency_key=job_idempotency_key(artifact.sha256),
                error_code="invalid_tcm_ba_pdf",
                error_detail=str(error),
            )
            log_event(
                logger,
                logging.WARNING,
                "tcm_ba_document_text_failed",
                artifact_hash=artifact.sha256,
                error_code="invalid_tcm_ba_pdf",
            )
            continue
        except Exception as error:
            failed += 1
            try:
                repository.persist_extraction_failure(
                    artifact,
                    job_type=JOB_TYPE,
                    job_idempotency_key=job_idempotency_key(artifact.sha256),
                    error_code="processing_error",
                    error_detail=f"{type(error).__name__}: {error}",
                )
            except Exception:
                logger.debug(
                    "tcm_ba_document_text_failure_persistence_failed",
                    exc_info=True,
                )
            log_event(
                logger,
                logging.WARNING,
                "tcm_ba_document_text_failed",
                artifact_hash=artifact.sha256,
                error_code="processing_error",
                error_type=type(error).__name__,
            )
            continue

        processed += 1
        pages_total += result.pages_total
        pages_with_embedded_text += result.pages_with_embedded_text
        pages_awaiting_ocr += result.pages_awaiting_ocr
        log_event(
            logger,
            logging.INFO,
            "tcm_ba_document_text_processed",
            artifact_hash=artifact.sha256,
            pages_total=result.pages_total,
            pages_with_embedded_text=result.pages_with_embedded_text,
            pages_awaiting_ocr=result.pages_awaiting_ocr,
            job_created=result.job_created,
        )

    log_event(
        logger,
        logging.INFO,
        "tcm_ba_document_text_batch_completed",
        pending_found=len(pending),
        processed=processed,
        failed=failed,
        pages_total=pages_total,
        pages_with_embedded_text=pages_with_embedded_text,
        pages_awaiting_ocr=pages_awaiting_ocr,
    )
    return batch_exit_code(pending_found=len(pending), failed=failed)


if __name__ == "__main__":
    raise SystemExit(main())
