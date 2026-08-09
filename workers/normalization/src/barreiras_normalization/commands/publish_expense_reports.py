"""Publica automaticamente demonstrativos de despesas preservados."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from datetime import date

from barreiras_docproc.canonical import CanonicalTextError

from ..expense_publication import ExpensePublicationError
from ..expense_publisher import (
    ExpenseReportPublisher,
    PostgresExpensePublicationRepository,
)
from ..revenue_publisher import ArtifactMismatchError


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
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 20:
        parser.error("--limit deve estar entre 1 e 20")
    if not 1900 <= args.fiscal_year_from <= args.fiscal_year_to <= 2200:
        parser.error("intervalo fiscal inválido")

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

    published = 0
    already_published = 0
    needs_review = 0
    artifacts = repository.pending_documents(
        limit=args.limit,
        fiscal_year_from=args.fiscal_year_from,
        fiscal_year_to=args.fiscal_year_to,
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
            published += result.published_lines
        else:
            already_published += 1

    logger.info(
        "expense_publication_completed artifacts=%s published_lines=%s "
        "already_published=%s needs_review=%s",
        len(artifacts),
        published,
        already_published,
        needs_review,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
