"""Baixa PDFs mensais do e-TCM em lotes pequenos e auditáveis."""

from __future__ import annotations

import argparse
import calendar
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from ..collection_control import (
    CollectionControl,
    CollectionOutcome,
    build_execution_idempotency_key,
)
from ..connectors.tcm_ba import (
    ENDPOINT_CODE,
    SOURCE_CODE,
    TcmBaDocument,
    TcmBaPublicAccountsClient,
)
from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.tcm_ba import (
    TCM_BA_DOCUMENT_COLLECTOR_VERSION,
    TcmBaDocumentPersistenceService,
)
from ..settings import CollectorSettings, PersistenceSettings
from ..tcm_ba_limits import MAX_TCM_BA_DOCUMENTS_PER_BATCH
from .pncp_runtime import build_authenticated_object_store


@dataclass(frozen=True)
class TcmBaDocumentBatchSummary:
    competence: str
    expected_documents: int
    preserved_before: int
    downloaded_documents: int
    preserved_after: int
    remaining_documents: int
    pdf_hashes: tuple[str, ...]


def execute_tcm_ba_document_batch(
    *,
    competence: str,
    max_documents: int,
    repository,
    service: TcmBaDocumentPersistenceService,
    client: TcmBaPublicAccountsClient,
    control: CollectionControl,
    category_code: str | None = None,
) -> TcmBaDocumentBatchSummary:
    """Executa um lote e só fecha o mês quando todos os PDFs foram preservados."""
    month, year = _parse_competence(competence)
    if not 1 <= max_documents <= MAX_TCM_BA_DOCUMENTS_PER_BATCH:
        raise ValueError(
            "max_documents deve estar entre 1 e "
            f"{MAX_TCM_BA_DOCUMENTS_PER_BATCH}."
        )

    with control:
        selection = repository.tcm_ba_document_references(
            competence=competence,
            limit=max_documents,
            category_code=category_code,
        )
        hashes: list[str] = []
        for reference in selection.references:
            expected_document = TcmBaDocument(
                category=reference.category,
                name=reference.name,
                inserted_at=reference.inserted_at,
                page_number=reference.page_number,
                download_form_id=reference.download_form_id,
            )
            download = client.fetch_monthly_document(
                year=year,
                month=month,
                document_position=reference.document_position,
                expected_total_documents=reference.expected_total_documents,
                expected_document=expected_document,
            )
            persisted = service.persist(
                download,
                reference=reference,
                collection_run_id=control.run_id,
            )
            hashes.append(persisted.pdf_sha256)

        downloaded = len(hashes)
        preserved_after = selection.preserved_documents + downloaded
        remaining = selection.pending_documents - downloaded
        if (
            remaining < 0
            or preserved_after > selection.expected_total_documents
            or preserved_after + remaining != selection.expected_total_documents
        ):
            raise RuntimeError("Contadores do lote documental TCM-BA divergiram.")
        outcome = (
            CollectionOutcome.COMPLETE if remaining == 0 else CollectionOutcome.PARTIAL
        )
        control.complete(
            outcome=outcome,
            observed_records=preserved_after,
            checkpoint={
                "competence": competence,
                "expected_documents": selection.expected_total_documents,
                "preserved_documents": preserved_after,
                "remaining_documents": remaining,
                "latest_pdf_hashes": hashes,
                "requested_category_code": category_code,
            },
            metrics={
                "documents_downloaded": downloaded,
                "documents_preserved_before": selection.preserved_documents,
                "documents_preserved_after": preserved_after,
                "documents_remaining": remaining,
                "requested_category_code": category_code,
            },
        )

    return TcmBaDocumentBatchSummary(
        competence=competence,
        expected_documents=selection.expected_total_documents,
        preserved_before=selection.preserved_documents,
        downloaded_documents=downloaded,
        preserved_after=preserved_after,
        remaining_documents=remaining,
        pdf_hashes=tuple(hashes),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preserva PDFs exatos de um catálogo mensal TCM-BA já completo. "
            "O lote é limitado a dez documentos."
        )
    )
    parser.add_argument("--competence", required=True, help="Competência MM/AAAA")
    parser.add_argument("--max-documents", type=int, default=1)
    parser.add_argument("--requests-per-minute", type=int, default=30)
    parser.add_argument("--category-code", default="")
    parser.add_argument(
        "--execution-origin",
        choices=("manual", "github_actions", "windows_scheduler"),
        default="manual",
    )
    args = parser.parse_args(argv)
    try:
        month, year = _parse_competence(args.competence)
    except ValueError as error:
        parser.error(str(error))
    if not 1 <= args.max_documents <= MAX_TCM_BA_DOCUMENTS_PER_BATCH:
        parser.error(
            "--max-documents deve estar entre 1 e "
            f"{MAX_TCM_BA_DOCUMENTS_PER_BATCH}."
        )
    if not 1 <= args.requests_per_minute <= 30:
        parser.error("--requests-per-minute deve estar entre 1 e 30.")
    category_code = args.category_code.strip().upper() or None
    if category_code is not None and not re.fullmatch(r"PCMGE\d{3}", category_code):
        parser.error("--category-code deve usar PCMGE seguido de três dígitos.")

    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    if persistence_settings.mode != "postgres-supabase":
        raise RuntimeError("Documentos TCM-BA exigem persistência PostgreSQL.")
    if persistence_settings.database_url is None:
        raise RuntimeError("Configuração de banco incompleta.")

    repository = PostgresCollectionRepository.from_dsn(
        persistence_settings.database_url
    )
    service = TcmBaDocumentPersistenceService(
        object_store=build_authenticated_object_store(persistence_settings),
        repository=repository,
    )
    client = TcmBaPublicAccountsClient(
        requests_per_minute=args.requests_per_minute,
    )
    period_start = date(year, month, 1)
    period_end = date(year, month, calendar.monthrange(year, month)[1])
    control = CollectionControl(
        repository=repository,
        source_code=SOURCE_CODE,
        endpoint_code=ENDPOINT_CODE,
        idempotency_key=build_execution_idempotency_key(
            f"tcm-documents-{year:04d}-{month:02d}"
        ),
        collector_version=TCM_BA_DOCUMENT_COLLECTOR_VERSION,
        parser_version="not-applicable",
        partition_key=f"documents:{year:04d}-{month:02d}",
        period_start=period_start,
        period_end=period_end,
        execution_origin=args.execution_origin,
    )
    summary = execute_tcm_ba_document_batch(
        competence=args.competence,
        max_documents=args.max_documents,
        repository=repository,
        service=service,
        client=client,
        control=control,
        category_code=category_code,
    )
    log_event(
        logging.getLogger(__name__),
        logging.INFO,
        "collector_tcm_ba_documents_completed",
        source=SOURCE_CODE,
        competence=summary.competence,
        expected_documents=summary.expected_documents,
        downloaded_documents=summary.downloaded_documents,
        preserved_documents=summary.preserved_after,
        remaining_documents=summary.remaining_documents,
        coverage_status=("complete" if summary.remaining_documents == 0 else "partial"),
        requested_category_code=category_code,
        pdf_hashes=list(summary.pdf_hashes),
    )
    return 0


def _parse_competence(value: str) -> tuple[int, int]:
    if re.fullmatch(r"(?:0[1-9]|1[0-2])/\d{4}", value) is None:
        raise ValueError("Competência inválida; use MM/AAAA.")
    month, year = value.split("/", 1)
    return int(month), int(year)


if __name__ == "__main__":
    raise SystemExit(main())
