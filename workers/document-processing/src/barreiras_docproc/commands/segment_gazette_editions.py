"""Segmenta edições completas em documentos literais, sem uso de IA."""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from barreiras_collectors.logging import log_event
from barreiras_collectors.settings import CollectorSettings, PersistenceSettings

from ..gazette_documents import DocumentBlock
from ..gazette_integrity import VALIDATOR_VERSION, validate_or_fallback
from ..gazette_repository import GazetteDocumentBatch, GazetteDocumentRepository
from ..gazette_segmentation import (
    SEGMENTER_VERSION,
    build_document_drafts,
    propose_boundaries,
)
from ..processing import PageInput, integral_gazette_idempotency_key


@dataclass(frozen=True)
class SegmentRunResult:
    processed: int
    failed: int


def version_idempotency_key(artifact_sha256: str, pages: Sequence[PageInput]) -> str:
    return integral_gazette_idempotency_key(
        artifact_sha256,
        tuple((page.page_number, page.parser_version) for page in pages),
        SEGMENTER_VERSION,
        VALIDATOR_VERSION,
    )


def page_blocks(pages: Sequence[PageInput]) -> tuple[DocumentBlock, ...]:
    """Produz um bloco por página nesta primeira versão conservadora.

    Limites internos de página ainda não possuem evidência de layout suficiente;
    propostas inconclusivas seguem para o fallback integral, nunca para cortes.
    """
    blocks: list[DocumentBlock] = []
    seen_pages: set[int] = set()
    for page in sorted(pages, key=lambda item: item.page_number):
        if page.page_number in seen_pages or not page.text:
            raise ValueError("Páginas da edição estão incompletas ou ambíguas.")
        seen_pages.add(page.page_number)
        blocks.append(
            DocumentBlock.create(
                page_number=page.page_number,
                block_order=0,
                text=page.text,
            )
        )
    if not blocks:
        raise ValueError("Edição sem páginas completas.")
    return tuple(blocks)


def process_pending(
    repository,
    *,
    limit: int,
    boundary_proposer: Callable = propose_boundaries,
) -> SegmentRunResult:
    """Isola uma falha por edição e persiste somente dados já validados."""
    artifacts = sorted(
        repository.pending_artifacts(limit),
        key=lambda item: (item.edition_year, item.edition, item.created_at),
        reverse=True,
    )
    processed = 0
    failed = 0
    for artifact in artifacts:
        if processed >= limit:
            break
        try:
            pages = tuple(repository.page_inputs(artifact.raw_artifact_id))
            idempotency_key = version_idempotency_key(artifact.sha256, pages)
            if repository.batch_exists(artifact.raw_artifact_id, idempotency_key):
                continue
            blocks = page_blocks(pages)
            proposals = boundary_proposer(blocks)
            try:
                drafts = build_document_drafts(blocks, proposals)
            except ValueError:
                # Uma fronteira inconsistente jamais bloqueia a publicação do
                # texto literal: ela é rebaixada ao fallback integral.
                drafts = ()
            # Um bloco por página não prova fronteiras internas. A primeira
            # versão conserva a edição inteira, mesmo diante de propostas.
            proposed_documents = len(drafts)
            documents, report = validate_or_fallback(blocks, ())
            batch = GazetteDocumentBatch(
                artifact=artifact,
                pages=pages,
                blocks=blocks,
                documents=documents,
                idempotency_key=idempotency_key,
                segmenter_version=SEGMENTER_VERSION,
                validator_version=VALIDATOR_VERSION,
            )
            persisted = repository.persist_version(batch)
            if persisted.created:
                processed += 1
            logging.getLogger(__name__).info(
                json.dumps(
                    {
                        "event": "integral_gazette_edition_processed",
                        "edition": artifact.edition,
                        "artifact_sha256": artifact.sha256,
                        "documents": len(documents),
                        "proposed_documents": proposed_documents,
                        "blocks": len(blocks),
                        "pages": len(pages),
                        "status": documents[0].status
                        if len(documents) == 1
                        else "validated",
                        "source_sha256": report.source_sha256,
                        "segmenter_version": SEGMENTER_VERSION,
                        "validator_version": VALIDATOR_VERSION,
                        "persisted": persisted.created,
                    },
                    ensure_ascii=False,
                )
            )
        except Exception as error:
            failed += 1
            repository.record_failure(
                artifact.raw_artifact_id,
                "segment_processing_error",
                f"Falha documental classificada como {type(error).__name__}.",
            )
    return SegmentRunResult(processed=processed, failed=failed)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Organiza edições integrais sem IA.")
    parser.add_argument("--limit", type=int, default=6)
    arguments = parser.parse_args(argv)
    if not 1 <= arguments.limit <= 20:
        parser.error("--limit deve estar entre 1 e 20.")
    collector_settings = CollectorSettings.from_env()
    persistence = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    if persistence.mode != "postgres-supabase" or persistence.database_url is None:
        raise RuntimeError("A segmentação requer PERSISTENCE_MODE=postgres-supabase.")
    result = process_pending(
        GazetteDocumentRepository.from_dsn(persistence.database_url),
        limit=arguments.limit,
    )
    log_event(
        logging.getLogger(__name__),
        logging.INFO,
        "integral_gazette_batch_completed",
        processed=result.processed,
        failed=result.failed,
        segmenter_version=SEGMENTER_VERSION,
        validator_version=VALIDATOR_VERSION,
    )
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
