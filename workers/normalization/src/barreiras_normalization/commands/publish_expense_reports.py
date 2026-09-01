"""Publica automaticamente demonstrativos de despesas preservados."""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections.abc import Sequence
from datetime import date

from barreiras_docproc.canonical import CanonicalTextError

from ..expense_publication import ExpensePublicationError
from ..expense_publisher import (
    ExpenseReportPublisher,
    PostgresExpensePublicationRepository,
)
from ..revenue_publisher import ArtifactMismatchError


def completion_exit_code(
    *,
    needs_review: int,
    artifacts: int = 0,
    require_artifact: bool = False,
) -> int:
    """Não mascara falha de publicação nem backfill dirigido vazio."""

    return 1 if needs_review or (require_artifact and artifacts == 0) else 0


def build_completion_event(
    *,
    artifact_sha256: str | None,
    artifacts: int,
    reports_published: int,
    published_lines: int,
    already_published: int,
    needs_review: int,
) -> dict[str, str | int | None]:
    """Emite um contrato sanitizado que wrappers podem validar sem ler texto."""

    return {
        "event": "expense_publication_completed",
        "artifact_sha256": artifact_sha256,
        "artifacts": artifacts,
        "reports_published": reports_published,
        "published_lines": published_lines,
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
        description="Publica linhas determinísticas de despesas municipais."
    )
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--fiscal-year-from", type=int, default=2021)
    parser.add_argument("--fiscal-year-to", type=int, default=date.today().year)
    parser.add_argument("--artifact-sha256", default="")
    parser.add_argument("--require-artifact", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 20:
        parser.error("--limit deve estar entre 1 e 20")
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
    repository = PostgresExpensePublicationRepository.from_dsn(settings.database_url)
    reader = SupabaseStorageObjectStore(
        client.storage.from_(settings.raw_artifacts_bucket)
    )
    publisher = ExpenseReportPublisher(object_reader=reader, repository=repository)

    reports_published = 0
    published_lines = 0
    already_published = 0
    needs_review = 0
    artifacts = repository.pending_documents(
        limit=args.limit,
        fiscal_year_from=args.fiscal_year_from,
        fiscal_year_to=args.fiscal_year_to,
        artifact_sha256=artifact_sha256,
    )
    logger = logging.getLogger(__name__)
    for index, artifact in enumerate(artifacts, start=1):
        logger.info(
            "expense_report_start artifact=%s progress=%s/%s source=%s",
            artifact.id,
            index,
            len(artifacts),
            artifact.source_url,
        )
        try:
            result = publisher.publish(artifact)
        except (
            ArtifactMismatchError,
            CanonicalTextError,
            ExpensePublicationError,
            ValueError,
        ) as error:
            needs_review += 1
            repository.record_failure(
                artifact,
                error_code=type(error).__name__,
                error_detail=str(error),
            )
            logger.error(
                "expense_report_needs_review artifact=%s error=%s",
                artifact.id,
                str(error)[:500],
            )
            continue
        if result.status == "published":
            reports_published += 1
            published_lines += result.published_lines
        else:
            already_published += 1

    completion_event = build_completion_event(
        artifact_sha256=artifact_sha256,
        artifacts=len(artifacts),
        reports_published=reports_published,
        published_lines=published_lines,
        already_published=already_published,
        needs_review=needs_review,
    )
    logger.info(json.dumps(completion_event, ensure_ascii=False, sort_keys=True))
    return completion_exit_code(
        needs_review=needs_review,
        artifacts=len(artifacts),
        require_artifact=args.require_artifact,
    )


if __name__ == "__main__":
    raise SystemExit(main())
