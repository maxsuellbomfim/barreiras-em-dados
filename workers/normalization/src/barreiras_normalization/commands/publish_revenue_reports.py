"""Publica automaticamente relatórios de receitas já preservados."""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections.abc import Sequence
from datetime import date

from barreiras_docproc.canonical import CanonicalTextError

from ..revenue_publication import RevenuePublicationError
from ..revenue_publisher import (
    ArtifactMismatchError,
    PostgresRevenuePublicationRepository,
    RevenueReportPublisher,
)


def completion_exit_code(
    *,
    needs_review: int,
    artifacts: int = 0,
    require_artifact: bool = False,
) -> int:
    """Falha quando houve revisão ou um backfill exigido ficou vazio."""

    return 1 if needs_review or (require_artifact and artifacts == 0) else 0


def build_completion_event(
    *,
    artifact_sha256: str | None,
    artifacts: int,
    published_rows: int,
    already_published: int,
    needs_review: int,
) -> dict[str, str | int | None]:
    """Emite um contrato sanitizado para o gate do replay exato."""

    return {
        "event": "revenue_publication_completed",
        "artifact_sha256": artifact_sha256,
        "artifacts": artifacts,
        "published_rows": published_rows,
        "already_published": already_published,
        "needs_review": needs_review,
    }


def _cloud_client(settings):
    if settings.mode != "postgres-supabase":
        raise RuntimeError("PERSISTENCE_MODE=postgres-supabase é obrigatório")
    required = (
        settings.database_url,
        settings.supabase_url,
        settings.supabase_publishable_key,
        settings.supabase_workload_email,
        settings.supabase_workload_password,
        settings.raw_artifacts_bucket,
    )
    if any(value is None for value in required):
        raise RuntimeError("configuração de nuvem financeira incompleta")
    from supabase import create_client

    client = create_client(settings.supabase_url, settings.supabase_publishable_key)
    authentication = client.auth.sign_in_with_password(
        {
            "email": settings.supabase_workload_email,
            "password": settings.supabase_workload_password,
        }
    )
    if authentication.session is None or authentication.user is None:
        raise RuntimeError("sessão do Storage não foi criada")
    return client


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Publica linhas determinísticas de relatórios municipais."
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--fiscal-year-from", type=int, default=2021)
    parser.add_argument("--fiscal-year-to", type=int, default=date.today().year)
    parser.add_argument("--artifact-sha256", default="")
    parser.add_argument("--require-artifact", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 100:
        parser.error("--limit deve estar entre 1 e 100")
    if not 1900 <= args.fiscal_year_from <= args.fiscal_year_to <= 2200:
        parser.error("intervalo fiscal inválido")
    artifact_sha256 = args.artifact_sha256.strip().lower() or None
    if artifact_sha256 is not None and not re.fullmatch(
        r"[0-9a-f]{64}", artifact_sha256
    ):
        parser.error("--artifact-sha256 deve ser um SHA-256 hexadecimal")

    from barreiras_collectors.persistence.storage import SupabaseStorageObjectStore
    from barreiras_collectors.settings import PersistenceSettings

    settings = PersistenceSettings.from_env()
    logging.basicConfig(level="INFO", format="%(message)s", force=True)
    client = _cloud_client(settings)
    repository = PostgresRevenuePublicationRepository.from_dsn(settings.database_url)
    reader = SupabaseStorageObjectStore(
        client.storage.from_(settings.raw_artifacts_bucket)
    )
    publisher = RevenueReportPublisher(object_reader=reader, repository=repository)

    published = 0
    already_published = 0
    needs_review = 0
    artifacts = repository.pending_documents(
        limit=args.limit,
        fiscal_year_from=args.fiscal_year_from,
        fiscal_year_to=args.fiscal_year_to,
        artifact_sha256=artifact_sha256,
    )
    for artifact in artifacts:
        try:
            result = publisher.publish(artifact)
        except (
            ArtifactMismatchError,
            CanonicalTextError,
            RevenuePublicationError,
            ValueError,
        ) as error:
            needs_review += 1
            repository.record_failure(
                artifact,
                error_code=type(error).__name__,
                error_detail=str(error),
            )
            logging.getLogger(__name__).error(
                "revenue_report_needs_review artifact=%s error=%s",
                artifact.id,
                str(error)[:500],
            )
            continue
        if result.status == "published":
            published += result.published_rows
        else:
            already_published += 1

    completion_event = build_completion_event(
        artifact_sha256=artifact_sha256,
        artifacts=len(artifacts),
        published_rows=published,
        already_published=already_published,
        needs_review=needs_review,
    )
    logging.getLogger(__name__).info(
        json.dumps(completion_event, ensure_ascii=False, sort_keys=True)
    )
    return completion_exit_code(
        needs_review=needs_review,
        artifacts=len(artifacts),
        require_artifact=args.require_artifact,
    )


if __name__ == "__main__":
    raise SystemExit(main())
