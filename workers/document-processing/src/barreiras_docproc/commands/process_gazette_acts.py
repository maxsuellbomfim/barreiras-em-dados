"""Processa textos preservados e enfileira candidatos para revisão humana."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

from barreiras_collectors.logging import log_event
from barreiras_collectors.persistence.storage import SupabaseStorageObjectStore
from barreiras_collectors.settings import CollectorSettings, PersistenceSettings

from ..postgres import PostgresExtractionRepository
from ..processing import GazetteActExtractionService


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Deriva texto canônico dos artefatos de texto do Querido Diário e "
            "registra candidatos determinísticos de nomeação/exoneração em "
            "fila interna, sem publicar nada."
        )
    )
    parser.add_argument("--limit", type=int, default=20)
    arguments = parser.parse_args(argv)
    if not 1 <= arguments.limit <= 200:
        parser.error("--limit deve estar entre 1 e 200.")

    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    if persistence_settings.mode != "postgres-supabase":
        raise RuntimeError(
            "O processamento de documentos requer PERSISTENCE_MODE="
            "postgres-supabase."
        )
    if (
        persistence_settings.database_url is None
        or persistence_settings.supabase_url is None
        or persistence_settings.supabase_publishable_key is None
        or persistence_settings.supabase_workload_email is None
        or persistence_settings.supabase_workload_password is None
        or persistence_settings.raw_artifacts_bucket is None
    ):
        raise RuntimeError("Configuração de nuvem incompleta.")
    try:
        from supabase import create_client
    except ImportError as error:
        raise RuntimeError(
            "Instale a dependência opcional 'storage' para processar."
        ) from error

    supabase_client = create_client(
        persistence_settings.supabase_url,
        persistence_settings.supabase_publishable_key,
    )
    try:
        authentication = supabase_client.auth.sign_in_with_password(
            {
                "email": persistence_settings.supabase_workload_email,
                "password": persistence_settings.supabase_workload_password,
            }
        )
    except Exception as error:
        raise RuntimeError(
            "Falha ao autenticar a identidade técnica do Storage."
        ) from error
    if authentication.session is None or authentication.user is None:
        raise RuntimeError("O Storage não forneceu uma sessão autenticada.")

    bucket_client = supabase_client.storage.from_(
        persistence_settings.raw_artifacts_bucket
    )
    repository = PostgresExtractionRepository.from_dsn(
        persistence_settings.database_url
    )
    service = GazetteActExtractionService(
        object_reader=SupabaseStorageObjectStore(bucket_client),
        repository=repository,
    )

    logger = logging.getLogger(__name__)
    pending = repository.pending_text_artifacts(arguments.limit)
    processed = 0
    jobs_created = 0
    candidates_queued = 0
    for artifact in pending:
        result = service.process(artifact)
        processed += 1
        jobs_created += int(result.job_created)
        candidates_queued += result.results_inserted
        log_event(
            logger,
            logging.INFO,
            "docproc_artifact_processed",
            source="querido-diario",
            artifact_hash=artifact.sha256,
            job_created=result.job_created,
            candidates=result.results_inserted,
        )

    log_event(
        logger,
        logging.INFO,
        "docproc_batch_completed",
        source="querido-diario",
        pending_found=len(pending),
        processed=processed,
        jobs_created=jobs_created,
        candidates_queued=candidates_queued,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
