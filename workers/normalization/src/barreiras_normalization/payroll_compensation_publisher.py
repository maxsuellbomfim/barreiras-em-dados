"""Publica faixas agregadas de provento bruto da folha regular."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Protocol, TypedDict

from .payroll_publisher import ObjectReader, default_payroll_pdf_text_extractor
from .payroll_report_pdf import (
    PayrollCompensationDistribution,
    parse_payroll_report_compensation_distribution,
)
from .revenue_publisher import ArtifactMismatchError

PAYROLL_COMPENSATION_PUBLICATION_JOB_TYPE = "payroll_compensation_publication/1.0.0"


class CompensationBandPayload(TypedDict):
    band_code: str
    band_label: str
    employee_count: int
    gross_amount: str


@dataclass(frozen=True)
class PayrollCompensationArtifact:
    aggregate_id: str
    artifact_id: str
    sha256: str
    object_key: str
    byte_size: int
    parent_record_id: str
    source_url: str
    reference_month: date


@dataclass(frozen=True)
class PayrollCompensationPublishResult:
    aggregate_id: str
    status: str


class PayrollCompensationRepository(Protocol):
    def pending_documents(
        self,
        *,
        limit: int,
        reference_month: date | None = None,
    ) -> tuple[PayrollCompensationArtifact, ...]: ...

    def persist_distribution(
        self,
        artifact: PayrollCompensationArtifact,
        distribution: PayrollCompensationDistribution,
    ) -> int: ...

    def record_failure(
        self,
        artifact: PayrollCompensationArtifact,
        *,
        error_code: str,
        error_detail: str,
    ) -> None: ...

    def has_public_distribution(self, reference_month: date) -> bool: ...


def compensation_bands_payload(
    distribution: PayrollCompensationDistribution,
) -> list[CompensationBandPayload]:
    return [
        {
            "band_code": band.band_code,
            "band_label": band.band_label,
            "employee_count": band.employee_count,
            "gross_amount": str(band.gross_amount),
        }
        for band in distribution.bands
    ]


class PayrollCompensationPublisher:
    def __init__(
        self,
        *,
        object_reader: ObjectReader,
        repository: PayrollCompensationRepository,
        text_extractor: Callable[[bytes], str] = default_payroll_pdf_text_extractor,
        logger: logging.Logger | None = None,
    ) -> None:
        self.object_reader = object_reader
        self.repository = repository
        self.text_extractor = text_extractor
        self.logger = logger or logging.getLogger(__name__)

    def publish(
        self,
        artifact: PayrollCompensationArtifact,
    ) -> PayrollCompensationPublishResult:
        raw_body = self.object_reader.read(artifact.object_key)
        actual_hash = hashlib.sha256(raw_body).hexdigest()
        if actual_hash != artifact.sha256 or len(raw_body) != artifact.byte_size:
            raise ArtifactMismatchError(
                f"Artefato {artifact.artifact_id} diverge do hash "
                "ou tamanho catalogado."
            )
        distribution = parse_payroll_report_compensation_distribution(
            self.text_extractor(raw_body)
        )
        inserted = self.repository.persist_distribution(artifact, distribution)
        status = "published" if inserted else "already_published"
        self.logger.info(
            "payroll_compensation_distribution_published",
            extra={
                "aggregate_id": artifact.aggregate_id,
                "reference_month": artifact.reference_month.isoformat(),
                "band_count": len(distribution.bands),
                "status": status,
                "parser_version": distribution.parser_version,
            },
        )
        return PayrollCompensationPublishResult(
            aggregate_id=artifact.aggregate_id,
            status=status,
        )


class PostgresPayrollCompensationRepository:
    def __init__(self, connection_factory) -> None:
        self.connection_factory = connection_factory

    @classmethod
    def from_dsn(cls, database_url: str) -> PostgresPayrollCompensationRepository:
        from barreiras_collectors.persistence.postgres import (
            PostgresCollectionRepository,
        )

        collection = PostgresCollectionRepository.from_dsn(database_url)
        return cls(collection.connection_factory)

    def pending_documents(
        self,
        *,
        limit: int,
        reference_month: date | None = None,
    ) -> tuple[PayrollCompensationArtifact, ...]:
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                select aggregate_id, artifact_id, sha256, object_key,
                  byte_size, parent_record_id, source_url, reference_month
                from hr.get_pending_payroll_compensation_documents(%s, %s)
                """,
                (limit, reference_month),
            ).fetchall()
            return tuple(
                PayrollCompensationArtifact(
                    aggregate_id=str(row["aggregate_id"]),
                    artifact_id=str(row["artifact_id"]),
                    sha256=str(row["sha256"]),
                    object_key=str(row["object_key"]),
                    byte_size=int(row["byte_size"]),
                    parent_record_id=str(row["parent_record_id"]),
                    source_url=str(row["source_url"]),
                    reference_month=row["reference_month"],
                )
                for row in rows
            )
        finally:
            connection.close()

    def persist_distribution(
        self,
        artifact: PayrollCompensationArtifact,
        distribution: PayrollCompensationDistribution,
    ) -> int:
        bands_json = json.dumps(
            compensation_bands_payload(distribution),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '30s'")
                connection.execute("set local lock_timeout = '5s'")
                row = connection.execute(
                    """
                    insert into hr.payroll_report_compensation_distributions (
                      payroll_report_aggregate_id, bands,
                      maximum_gross_amount, parser_version, validated_at
                    ) values (
                      %s::uuid, %s::jsonb, %s, %s, statement_timestamp()
                    )
                    on conflict (payroll_report_aggregate_id) do nothing
                    returning id::text
                    """,
                    (
                        artifact.aggregate_id,
                        bands_json,
                        distribution.maximum_gross_amount,
                        distribution.parser_version,
                    ),
                ).fetchone()
                if row is None:
                    return 0
                connection.execute(
                    """
                    insert into evidence.evidence_items (
                      target_type, target_id, raw_artifact_id, raw_record_id,
                      evidence_kind, source_url, excerpt, locator,
                      content_sha256, parser_version, is_primary
                    ) values (
                      'hr.payroll_report_compensation_distributions', %s::uuid,
                      %s::uuid, %s::uuid, 'document', %s,
                      'Faixas de provento bruto reconciliadas com a folha regular.',
                      jsonb_build_object(
                        'reference_month', %s::text,
                        'aggregate_id', %s::text
                      ),
                      %s, %s, true
                    )
                    """,
                    (
                        row["id"],
                        artifact.artifact_id,
                        artifact.parent_record_id,
                        artifact.source_url,
                        artifact.reference_month.isoformat(),
                        artifact.aggregate_id,
                        artifact.sha256,
                        distribution.parser_version,
                    ),
                )
                return 1
        finally:
            connection.close()

    def has_public_distribution(self, reference_month: date) -> bool:
        connection = self.connection_factory()
        try:
            row = connection.execute(
                """
                select exists(
                  select 1
                  from api.get_public_payroll_compensation_distribution(%s::date)
                ) as is_public
                """,
                (reference_month,),
            ).fetchone()
            return row is not None and bool(row["is_public"])
        finally:
            connection.close()

    def record_failure(
        self,
        artifact: PayrollCompensationArtifact,
        *,
        error_code: str,
        error_detail: str,
    ) -> None:
        connection = self.connection_factory()
        try:
            connection.execute(
                """
                insert into raw.extraction_jobs (
                  raw_artifact_id, job_type, idempotency_key, status,
                  attempt_count, last_error_code, last_error_detail
                ) values (
                  %s::uuid, %s, %s, 'failed', 1, %s, %s
                )
                on conflict (idempotency_key) do update set
                  status = 'failed',
                  attempt_count = raw.extraction_jobs.attempt_count + 1,
                  last_error_code = excluded.last_error_code,
                  last_error_detail = excluded.last_error_detail,
                  updated_at = statement_timestamp()
                """,
                (
                    artifact.artifact_id,
                    PAYROLL_COMPENSATION_PUBLICATION_JOB_TYPE,
                    _failure_key(artifact.aggregate_id, artifact.sha256),
                    error_code,
                    error_detail[:1000],
                ),
            )
        finally:
            connection.close()


def _failure_key(aggregate_id: str, artifact_sha256: str) -> str:
    material = (
        f"{PAYROLL_COMPENSATION_PUBLICATION_JOB_TYPE}:{aggregate_id}:{artifact_sha256}"
    )
    return hashlib.sha256(material.encode()).hexdigest()
