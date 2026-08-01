"""Aplica OCR às páginas escaneadas pendentes, com origem declarada."""

from __future__ import annotations

import argparse
import hashlib
import logging
from collections.abc import Sequence

from barreiras_collectors.logging import log_event
from barreiras_collectors.persistence.storage import SupabaseStorageObjectStore
from barreiras_collectors.settings import CollectorSettings, PersistenceSettings

from ..ocr import OCR_PARSER_VERSION, OcrError, TesseractEngine, ocr_page
from ..postgres import PostgresExtractionRepository
from ..processing import PageInput


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Renderiza e reconhece as páginas sem texto embutido, gravando o "
            "resultado com método OCR declarado."
        )
    )
    parser.add_argument("--limit-pages", type=int, default=30)
    arguments = parser.parse_args(argv)
    if not 1 <= arguments.limit_pages <= 200:
        parser.error("--limit-pages deve estar entre 1 e 200.")

    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    if persistence_settings.mode != "postgres-supabase":
        raise RuntimeError("O OCR requer PERSISTENCE_MODE=postgres-supabase.")
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
            "Instale a dependência opcional 'storage' para o OCR."
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

    object_store = SupabaseStorageObjectStore(
        supabase_client.storage.from_(
            persistence_settings.raw_artifacts_bucket
        )
    )
    repository = PostgresExtractionRepository.from_dsn(
        persistence_settings.database_url
    )
    engine = TesseractEngine()

    logger = logging.getLogger(__name__)
    pending = repository.pending_ocr_pages(arguments.limit_pages)
    pages_done = 0
    artifacts_touched = 0
    for artifact, page_numbers in pending:
        raw_body = object_store.read(artifact.object_key)
        if hashlib.sha256(raw_body).hexdigest() != artifact.sha256:
            raise OcrError(
                "O PDF restaurado diverge do hash registrado do artefato."
            )
        results = []
        for page_number in page_numbers:
            outcome = ocr_page(engine, raw_body, page_number)
            results.append(
                PageInput(
                    page_number=outcome.page_number,
                    parser_version=OCR_PARSER_VERSION,
                    text=outcome.text,
                    sha256=outcome.sha256,
                    extraction_method="ocr",
                )
            )
            pages_done += 1
        repository.persist_pages(artifact, tuple(results))
        artifacts_touched += 1
        log_event(
            logger,
            logging.INFO,
            "docproc_ocr_pages_persisted",
            source="querido-diario",
            artifact_hash=artifact.sha256,
            pages=len(results),
        )

    log_event(
        logger,
        logging.INFO,
        "docproc_ocr_batch_completed",
        source="querido-diario",
        artifacts=artifacts_touched,
        pages=pages_done,
        limit_pages=arguments.limit_pages,
        parser_version=OCR_PARSER_VERSION,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
