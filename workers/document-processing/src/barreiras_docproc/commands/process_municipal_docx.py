"""Processa DOCX municipais preservados sem publicar seu conteúdo."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

from barreiras_collectors.logging import log_event
from barreiras_collectors.persistence.storage import SupabaseStorageObjectStore
from barreiras_collectors.settings import CollectorSettings, PersistenceSettings

from ..docx_text import DocxStructureError
from ..municipal_docx_text import (
    JOB_TYPE,
    MunicipalDocxTextService,
    job_idempotency_key,
)
from ..postgres import PostgresExtractionRepository
from ..processing import ArtifactMismatchError


def batch_exit_code(
    *,
    failed: int,
    processed_total: int,
    minimum_total: int,
) -> int:
    return 0 if failed == 0 and processed_total >= minimum_total else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Confere o SHA-256 dos DOCX municipais preservados e registra "
            "o texto literal em uma unidade privada, sem publicar valores."
        )
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--minimum-total", type=int, default=1)
    arguments = parser.parse_args(argv)
    if not 1 <= arguments.limit <= 50:
        parser.error("--limit deve estar entre 1 e 50.")
    if not 1 <= arguments.minimum_total <= 50:
        parser.error("--minimum-total deve estar entre 1 e 50.")

    collector_settings = CollectorSettings.from_env()
    persistence = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    if persistence.mode != "postgres-supabase":
        raise RuntimeError(
            "O processamento DOCX requer PERSISTENCE_MODE=postgres-supabase."
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
            "Instale a dependência opcional 'storage' para processar DOCX."
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
    service = MunicipalDocxTextService(
        object_reader=SupabaseStorageObjectStore(
            client.storage.from_(persistence.raw_artifacts_bucket)
        ),
        repository=repository,
    )
    logger = logging.getLogger(__name__)
    pending = repository.pending_municipal_docx_artifacts(arguments.limit)
    processed = 0
    failed = 0
    text_characters = 0
    blocks_total = 0
    for artifact in pending:
        try:
            result = service.process(artifact)
        except (ArtifactMismatchError, DocxStructureError) as error:
            failed += 1
            repository.persist_extraction_failure(
                artifact,
                job_type=JOB_TYPE,
                job_idempotency_key=job_idempotency_key(artifact.sha256),
                error_code="invalid_municipal_docx",
                error_detail=str(error),
            )
            log_event(
                logger,
                logging.WARNING,
                "municipal_docx_text_failed",
                artifact_hash=artifact.sha256,
                error_code="invalid_municipal_docx",
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
                    "municipal_docx_text_failure_persistence_failed",
                    exc_info=True,
                )
            log_event(
                logger,
                logging.WARNING,
                "municipal_docx_text_failed",
                artifact_hash=artifact.sha256,
                error_code="processing_error",
                error_type=type(error).__name__,
            )
            continue

        processed += 1
        text_characters += result.text_characters
        blocks_total += result.blocks_total
        log_event(
            logger,
            logging.INFO,
            "municipal_docx_text_processed",
            artifact_hash=artifact.sha256,
            text_characters=result.text_characters,
            blocks_total=result.blocks_total,
            job_created=result.job_created,
        )

    processed_total = repository.municipal_docx_processed_total()
    coverage_complete = processed_total >= arguments.minimum_total
    log_event(
        logger,
        logging.INFO,
        "municipal_docx_text_batch_completed",
        pending_found=len(pending),
        processed=processed,
        failed=failed,
        text_characters=text_characters,
        blocks_total=blocks_total,
        processed_total=processed_total,
        minimum_total=arguments.minimum_total,
        coverage_complete=coverage_complete,
    )
    return batch_exit_code(
        failed=failed,
        processed_total=processed_total,
        minimum_total=arguments.minimum_total,
    )


if __name__ == "__main__":
    raise SystemExit(main())
