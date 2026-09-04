"""Audita um lote documental TCM-BA sem alterar banco ou Storage."""

from __future__ import annotations

import argparse
import hashlib
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from ..logging import log_event
from ..persistence.models import TcmBaDocumentAuditSnapshot
from ..persistence.postgres import PostgresCollectionRepository
from ..settings import CollectorSettings, PersistenceSettings
from ..tcm_ba_limits import MAX_TCM_BA_DOCUMENTS_PER_BATCH
from .pncp_runtime import build_authenticated_object_store

_SHA256 = re.compile(r"[0-9a-f]{64}")
_PREPARE_SCHEMA = "tcm-ba-document-download-prepare"
_PDF_SCHEMA = "tcm-ba-monthly-document"


class TcmBaDocumentAuditError(RuntimeError):
    """O lote persistido divergiu do contrato verificável."""


class AuditRepository(Protocol):
    def tcm_ba_document_audit_snapshot(
        self, *, competence: str
    ) -> TcmBaDocumentAuditSnapshot: ...


class ReadableObjectStore(Protocol):
    def read(self, object_key: str) -> bytes: ...


@dataclass(frozen=True)
class TcmBaDocumentAuditSummary:
    competence: str
    expected_documents: int
    downloaded_documents: int
    preserved_documents: int
    remaining_documents: int
    coverage_status: str
    run_artifacts: int
    prepare_xml: int
    pdfs: int
    catalog_links: int
    physical_objects_verified: int
    physical_bytes_verified: int
    distinct_physical_sha256: int
    current_open_failures: int
    historical_open_failures: int


def audit_tcm_ba_document_batch(
    *,
    competence: str,
    repository: AuditRepository,
    object_store: ReadableObjectStore,
) -> TcmBaDocumentAuditSummary:
    """Reconcilia cobertura, linhagem, metadados e bytes do último lote."""
    month, year = _parse_competence(competence)
    snapshot = repository.tcm_ba_document_audit_snapshot(competence=competence)
    if snapshot.competence != competence:
        raise TcmBaDocumentAuditError(
            "A competência do snapshot diverge da solicitada."
        )
    if snapshot.partition_completed_at is None:
        raise TcmBaDocumentAuditError("A partição documental não possui terminalidade.")

    expected = _exact_non_negative_integer(
        snapshot.checkpoint.get("expected_documents"), "expected_documents"
    )
    preserved = _exact_non_negative_integer(
        snapshot.checkpoint.get("preserved_documents"), "preserved_documents"
    )
    remaining = _exact_non_negative_integer(
        snapshot.checkpoint.get("remaining_documents"), "remaining_documents"
    )
    downloaded = _exact_non_negative_integer(
        snapshot.metrics.get("documents_downloaded"), "documents_downloaded"
    )
    preserved_before = _exact_non_negative_integer(
        snapshot.metrics.get("documents_preserved_before"),
        "documents_preserved_before",
    )
    preserved_after = _exact_non_negative_integer(
        snapshot.metrics.get("documents_preserved_after"),
        "documents_preserved_after",
    )
    metrics_remaining = _exact_non_negative_integer(
        snapshot.metrics.get("documents_remaining"), "documents_remaining"
    )
    if expected <= 0:
        raise TcmBaDocumentAuditError("expected_documents deve ser maior que zero.")
    if not 1 <= downloaded <= MAX_TCM_BA_DOCUMENTS_PER_BATCH:
        raise TcmBaDocumentAuditError(
            "O lote auditado deve conter entre 1 e "
            f"{MAX_TCM_BA_DOCUMENTS_PER_BATCH} PDFs."
        )
    if preserved != snapshot.observed_records or preserved != preserved_after:
        raise TcmBaDocumentAuditError("A cobertura observada diverge dos preservados.")
    if preserved_before + downloaded != preserved:
        raise TcmBaDocumentAuditError("O avanço cumulativo do lote é inconsistente.")
    if preserved + remaining != expected or remaining != metrics_remaining:
        raise TcmBaDocumentAuditError(
            "Preservados e restantes não recompõem o catálogo."
        )

    expected_coverage = "complete" if remaining == 0 else "partial"
    expected_run_status = "succeeded" if remaining == 0 else "partial"
    if snapshot.partition_status != expected_coverage:
        raise TcmBaDocumentAuditError("O status da partição diverge dos contadores.")
    if snapshot.run_status != expected_run_status:
        raise TcmBaDocumentAuditError("O status da execução diverge da cobertura.")
    if snapshot.metrics.get("collection_outcome") != expected_coverage:
        raise TcmBaDocumentAuditError("collection_outcome diverge da cobertura.")
    if snapshot.current_open_failures != 0:
        raise TcmBaDocumentAuditError("A execução atual possui falha não resolvida.")

    artifacts = snapshot.artifacts
    if len(artifacts) != downloaded * 2:
        raise TcmBaDocumentAuditError(
            "O lote não possui exatamente XML e PDF por item."
        )
    prepare = tuple(item for item in artifacts if item.schema_name == _PREPARE_SCHEMA)
    pdfs = tuple(item for item in artifacts if item.schema_name == _PDF_SCHEMA)
    if len(prepare) != downloaded or len(pdfs) != downloaded:
        raise TcmBaDocumentAuditError("A composição XML/PDF do lote é inválida.")
    if snapshot.catalog_links != downloaded:
        raise TcmBaDocumentAuditError(
            "A linhagem entre catálogo e lote está incompleta."
        )

    prepare_by_id = {item.artifact_id: item for item in prepare}
    if len(prepare_by_id) != downloaded:
        raise TcmBaDocumentAuditError("Há identificadores de artefato duplicados.")
    prepare_keys = {item.source_record_key for item in prepare}
    pdf_keys = {item.source_record_key for item in pdfs}
    if len(prepare_keys) != downloaded or prepare_keys != pdf_keys:
        raise TcmBaDocumentAuditError("As chaves oficiais de XML e PDF divergem.")
    for pdf in pdfs:
        parent = prepare_by_id.get(pdf.parent_artifact_id)
        if parent is None or parent.source_record_key != pdf.source_record_key:
            raise TcmBaDocumentAuditError(
                "A linhagem PDF para XML preparatório é inválida."
            )

    physical_bytes = 0
    physical_hashes: set[str] = set()
    for artifact in artifacts:
        expected_role, expected_media, expected_suffix = (
            ("prepare", "application/xml", "xml")
            if artifact.schema_name == _PREPARE_SCHEMA
            else ("pdf", "application/pdf", "pdf")
        )
        if artifact.http_status < 200 or artifact.http_status > 299:
            raise TcmBaDocumentAuditError("Um artefato possui HTTP fora de 2xx.")
        if artifact.content_type != expected_media:
            raise TcmBaDocumentAuditError(
                "O tipo de mídia diverge do papel documental."
            )
        if artifact.byte_size <= 0 or _SHA256.fullmatch(artifact.sha256) is None:
            raise TcmBaDocumentAuditError("Hash ou tamanho de artefato é inválido.")
        expected_key = (
            f"tcm-ba/monthly-documents/{year:04d}/{month:02d}/{expected_role}/"
            f"sha256/{artifact.sha256[:2]}/{artifact.sha256}.{expected_suffix}"
        )
        if artifact.object_key != expected_key:
            raise TcmBaDocumentAuditError(
                "A chave de objeto não é endereçada pelo hash."
            )
        body = object_store.read(artifact.object_key)
        if len(body) != artifact.byte_size:
            raise TcmBaDocumentAuditError("O tamanho físico diverge do banco.")
        actual_sha256 = hashlib.sha256(body).hexdigest()
        if actual_sha256 != artifact.sha256:
            raise TcmBaDocumentAuditError("Os bytes físicos divergem do SHA-256.")
        if expected_role == "prepare":
            if (
                not body.lstrip().startswith(b"<?xml")
                or b"downloadDocumento.seam" not in body
            ):
                raise TcmBaDocumentAuditError(
                    "O XML preparatório não tem a assinatura esperada."
                )
        elif not body.startswith(b"%PDF-") or b"%%EOF" not in body[-4096:]:
            raise TcmBaDocumentAuditError(
                "O PDF não tem a assinatura estrutural mínima."
            )
        physical_bytes += len(body)
        physical_hashes.add(actual_sha256)
    if len(physical_hashes) != len(artifacts):
        raise TcmBaDocumentAuditError(
            "O lote reutilizou conteúdo físico inesperadamente."
        )

    return TcmBaDocumentAuditSummary(
        competence=competence,
        expected_documents=expected,
        downloaded_documents=downloaded,
        preserved_documents=preserved,
        remaining_documents=remaining,
        coverage_status=expected_coverage,
        run_artifacts=len(artifacts),
        prepare_xml=len(prepare),
        pdfs=len(pdfs),
        catalog_links=snapshot.catalog_links,
        physical_objects_verified=len(artifacts),
        physical_bytes_verified=physical_bytes,
        distinct_physical_sha256=len(physical_hashes),
        current_open_failures=snapshot.current_open_failures,
        historical_open_failures=snapshot.historical_open_failures,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audita o último lote documental TCM-BA."
    )
    parser.add_argument("--competence", required=True, help="Competência MM/AAAA")
    args = parser.parse_args(argv)
    _parse_competence(args.competence)
    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    if persistence_settings.mode != "postgres-supabase":
        raise RuntimeError("A auditoria TCM-BA exige persistência PostgreSQL.")
    if persistence_settings.database_url is None:
        raise RuntimeError("Configuração de banco incompleta.")
    summary = audit_tcm_ba_document_batch(
        competence=args.competence,
        repository=PostgresCollectionRepository.from_dsn(
            persistence_settings.database_url
        ),
        object_store=build_authenticated_object_store(persistence_settings),
    )
    log_event(
        logging.getLogger(__name__),
        logging.INFO,
        "auditor_tcm_ba_document_batch_completed",
        gate="PASS",
        **summary.__dict__,
    )
    return 0


def _parse_competence(value: str) -> tuple[int, int]:
    if re.fullmatch(r"(?:0[1-9]|1[0-2])/\d{4}", value) is None:
        raise ValueError("Competência inválida; use MM/AAAA.")
    month, year = value.split("/", 1)
    return int(month), int(year)


def _exact_non_negative_integer(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TcmBaDocumentAuditError(f"{field} deve ser inteiro não negativo.")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
