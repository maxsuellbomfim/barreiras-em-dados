"""Anota por IA as páginas da amostra de qualidade de atos (ADR 0091)."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import time
from collections.abc import Callable, Sequence

from barreiras_collectors.logging import log_event
from barreiras_collectors.persistence.storage import SupabaseStorageObjectStore
from barreiras_collectors.settings import CollectorSettings, PersistenceSettings

from ..act_quality_ai import (
    GEMINI_MODELS,
    GEMINI_URL,
    PROMPT_VERSION,
    annotator_id,
    build_payload,
    page_image_data_uri,
    parse_annotation,
    response_sha256,
)
from ..assist import UrllibJsonCaller
from ..ocr import rasterize_page
from ..postgres import PostgresExtractionRepository

# Cota gratuita do Gemini: ~10 requisições por minuto.
SECONDS_BETWEEN_CALLS = 7.0


def annotate_page(
    *,
    caller,
    api_key: str,
    image_uri: str,
    acts: Sequence[dict],
    sleep: Callable[[float], None] = time.sleep,
):
    """Tenta os modelos em ordem; resposta fora do contrato passa ao próximo."""
    expected = [str(act["result_id"]) for act in acts]
    last_error = "sem modelo"
    for model in GEMINI_MODELS:
        status, body = caller.post(
            GEMINI_URL,
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            build_payload(model, image_uri, acts),
        )
        sleep(SECONDS_BETWEEN_CALLS)
        if status != 200:
            last_error = f"HTTP {status}"
            continue
        try:
            return model, parse_annotation(body, expected), response_sha256(body)
        except (ValueError, KeyError, IndexError, TypeError) as error:
            last_error = type(error).__name__
    raise RuntimeError(f"Nenhum modelo respondeu dentro do contrato ({last_error}).")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=120)
    arguments = parser.parse_args(argv)
    if not 1 <= arguments.limit <= 500:
        parser.error("--limit deve estar entre 1 e 500.")
    collector_settings = CollectorSettings.from_env()
    persistence = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    logger = logging.getLogger(__name__)
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Defina GEMINI_API_KEY.")
    if persistence.mode != "postgres-supabase" or persistence.database_url is None:
        raise RuntimeError("A anotação requer PERSISTENCE_MODE=postgres-supabase.")

    from supabase import create_client

    client = create_client(
        persistence.supabase_url, persistence.supabase_publishable_key
    )
    session = client.auth.sign_in_with_password(
        {
            "email": persistence.supabase_workload_email,
            "password": persistence.supabase_workload_password,
        }
    )
    if session.session is None:
        raise RuntimeError("O Storage não forneceu uma sessão autenticada.")
    objects = SupabaseStorageObjectStore(
        client.storage.from_(persistence.raw_artifacts_bucket)
    )
    connect = PostgresExtractionRepository.from_dsn(
        persistence.database_url
    ).connection_factory

    connection = connect()
    try:
        pages = connection.execute(
            "select * from editorial.get_act_quality_pages_for_ai(%s, %s)",
            (PROMPT_VERSION, arguments.limit),
        ).fetchall()
    finally:
        connection.close()

    caller = UrllibJsonCaller(timeout_seconds=120.0)
    recorded = failed = 0
    pdf_cache: dict[str, bytes] = {}
    for page in pages:
        try:
            key = str(page["object_key"])
            if key not in pdf_cache:
                body = objects.read(key)
                if hashlib.sha256(body).hexdigest() != page["artifact_sha256"]:
                    raise RuntimeError("PDF diverge do hash registrado.")
                pdf_cache = {key: body}
            image_uri = page_image_data_uri(
                rasterize_page(pdf_cache[key], int(page["page_number"]))
            )
            acts = list(page["acts"] or [])
            model, annotation, raw_sha = annotate_page(
                caller=caller, api_key=api_key, image_uri=image_uri, acts=acts
            )
            connection = connect()
            try:
                with connection.transaction():
                    connection.execute(
                        "select editorial.record_ai_act_quality_annotation("
                        "%s::uuid, %s::jsonb, %s, %s, %s, %s)",
                        (
                            str(page["sample_page_id"]),
                            json.dumps(annotation.verdicts),
                            annotation.missed_nomeacoes,
                            annotation.missed_exoneracoes,
                            annotator_id(model),
                            raw_sha,
                        ),
                    )
            finally:
                connection.close()
            recorded += 1
        except Exception as error:
            failed += 1
            log_event(
                logger,
                logging.WARNING,
                "act_quality_ai_page_failed",
                page=str(page["sample_page_id"]),
                error_type=type(error).__name__,
            )
    log_event(
        logger,
        logging.INFO,
        "act_quality_ai_batch_completed",
        pending=len(pages),
        recorded=recorded,
        failed=failed,
        prompt_version=PROMPT_VERSION,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
