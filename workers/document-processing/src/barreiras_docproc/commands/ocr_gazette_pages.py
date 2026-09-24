"""Aplica OCR às páginas escaneadas pendentes da fonte declarada."""

from __future__ import annotations

import argparse
import hashlib
import logging
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from itertools import repeat

from barreiras_collectors.logging import log_event
from barreiras_collectors.persistence.storage import SupabaseStorageObjectStore
from barreiras_collectors.settings import CollectorSettings, PersistenceSettings

from ..ocr import (
    OcrError,
    TesseractEngine,
    ocr_page,
    parser_version_for_source,
)
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
    parser.add_argument(
        "--source",
        choices=("querido-diario", "tcm-ba"),
        default="querido-diario",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Páginas reconhecidas em paralelo (processos Tesseract).",
    )
    arguments = parser.parse_args(argv)
    if not 1 <= arguments.limit_pages <= 1000:
        parser.error("--limit-pages deve estar entre 1 e 1000.")
    if not 1 <= arguments.workers <= 8:
        parser.error("--workers deve estar entre 1 e 8.")

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
    parser_version = parser_version_for_source(arguments.source)

    logger = logging.getLogger(__name__)
    pending = repository.pending_ocr_pages(
        arguments.limit_pages,
        source=arguments.source,
    )
    pages_done = 0
    artifacts_touched = 0
    pool = ThreadPoolExecutor(max_workers=arguments.workers)
    for artifact, page_numbers in pending:
        raw_body = object_store.read(artifact.object_key)
        if hashlib.sha256(raw_body).hexdigest() != artifact.sha256:
            raise OcrError(
                "O PDF restaurado diverge do hash registrado do artefato."
            )
        # map preserva a ordem das páginas; qualquer falha interrompe o
        # artefato inteiro antes de gravar, como no laço sequencial.
        outcomes = list(
            pool.map(ocr_page, repeat(engine), repeat(raw_body), page_numbers)
        )
        results = tuple(
            PageInput(
                page_number=outcome.page_number,
                parser_version=parser_version,
                text=outcome.text,
                sha256=outcome.sha256,
                extraction_method="ocr",
            )
            for outcome in outcomes
        )
        pages_done += len(results)
        repository.persist_pages(artifact, results)
        artifacts_touched += 1
        log_event(
            logger,
            logging.INFO,
            "docproc_ocr_pages_persisted",
            source=arguments.source,
            artifact_hash=artifact.sha256,
            pages=len(results),
        )
    pool.shutdown()

    log_event(
        logger,
        logging.INFO,
        "docproc_ocr_batch_completed",
        source=arguments.source,
        artifacts=artifacts_touched,
        pages=pages_done,
        limit_pages=arguments.limit_pages,
        workers=arguments.workers,
        parser_version=parser_version,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
