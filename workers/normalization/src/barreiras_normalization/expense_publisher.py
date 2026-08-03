"""Publicador idempotente de demonstrativos de despesas preservados."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from .expense_publication import (
    ExpensePublicationBatch,
    build_expense_publication_batch,
)
from .financial_expense_pdf import parse_expense_pdf_text
from .revenue_publisher import ArtifactMismatchError, default_pdf_text_extractor

EXPENSE_PUBLICATION_JOB_TYPE = "financial_expense_publication"


@dataclass(frozen=True)
class ExpenseArtifact:
    id: str
    sha256: str
    object_key: str
    byte_size: int
    parent_record_id: str
    source_url: str


@dataclass(frozen=True)
class ExpensePublishResult:
    artifact_id: str
    status: str
    published_lines: int = 0


class ObjectReader(Protocol):
    def read(self, object_key: str) -> bytes: ...


class ExpensePublicationRepository(Protocol):
    def pending_documents(
        self,
        *,
        limit: int,
        fiscal_year_from: int,
        fiscal_year_to: int,
    ) -> tuple[ExpenseArtifact, ...]: ...

    def persist_validated_report(
        self,
        artifact: ExpenseArtifact,
        batch: ExpensePublicationBatch,
    ) -> int: ...

    def record_failure(
        self,
        artifact: ExpenseArtifact,
        *,
        error_code: str,
        error_detail: str,
    ) -> None: ...


class ExpenseReportPublisher:
    """Valida bytes, extrai o demonstrativo e persiste uma versão publicada."""

    def __init__(
        self,
        *,
        object_reader: ObjectReader,
        repository: ExpensePublicationRepository,
        text_extractor: Callable[[bytes], str] = default_pdf_text_extractor,
        logger: logging.Logger | None = None,
    ) -> None:
        self.object_reader = object_reader
        self.repository = repository
        self.text_extractor = text_extractor
        self.logger = logger or logging.getLogger(__name__)

    def publish(self, artifact: ExpenseArtifact) -> ExpensePublishResult:
        raw_body = self.object_reader.read(artifact.object_key)
        actual_hash = hashlib.sha256(raw_body).hexdigest()
        if actual_hash != artifact.sha256 or len(raw_body) != artifact.byte_size:
            raise ArtifactMismatchError(
                f"Artefato {artifact.id} diverge do hash ou tamanho catalogado."
            )
        text = self.text_extractor(raw_body)
        report = parse_expense_pdf_text(text)
        batch = build_expense_publication_batch(report)
        published_lines = self.repository.persist_validated_report(artifact, batch)
        self.logger.info(
            "expense_report_published",
            extra={
                "artifact_id": artifact.id,
                "period_end": batch.period_end,
                "published_lines": published_lines,
                "methodology_version": batch.methodology_version,
            },
        )
        return ExpensePublishResult(
            artifact_id=artifact.id,
            status="published" if published_lines else "already_published",
            published_lines=published_lines,
        )


class PostgresExpensePublicationRepository:
    """Seleção e publicação transacional do relatório de despesas."""

    def __init__(self, connection_factory) -> None:
        self.connection_factory = connection_factory

    @classmethod
    def from_dsn(cls, database_url: str) -> PostgresExpensePublicationRepository:
        from barreiras_collectors.persistence.postgres import (
            PostgresCollectionRepository,
        )

        collection = PostgresCollectionRepository.from_dsn(database_url)
        return cls(collection.connection_factory)

    def pending_documents(
        self,
        *,
        limit: int,
        fiscal_year_from: int,
        fiscal_year_to: int,
    ) -> tuple[ExpenseArtifact, ...]:
        connection = self.connection_factory()
        try:
            result = connection.execute(
                """
                select
                  document.id::text,
                  document.sha256,
                  document.object_key,
                  document.byte_size,
                  record.id::text as parent_record_id,
                  document.source_url
                from raw.raw_artifacts as document
                join raw.raw_artifacts as parent_artifact
                  on parent_artifact.id = document.parent_artifact_id
                join raw.raw_records as record
                  on record.raw_artifact_id = parent_artifact.id
                where document.artifact_kind = 'document'
                  and document.metadata ->> 'schema_name'
                    = 'municipal-transparency-document'
                  and record.record_type
                    = 'municipal_transparency_pdc-resumo-execucao-da-despesa'
                  and record.payload ->> 'ano' ~ '^[0-9]{4}$'
                  and (record.payload ->> 'ano')::integer between %s and %s
                  and not exists (
                    select 1
                    from finance.expense_reports as report
                    where report.source_document_artifact_id = document.id
                      and report.validation_status = 'validated'
                  )
                  and not exists (
                    select 1
                    from raw.extraction_jobs as job
                    where job.raw_artifact_id = document.id
                      and job.job_type = %s
                      and job.status = 'failed'
                  )
                order by document.created_at, document.id
                limit %s
                """,
                (fiscal_year_from, fiscal_year_to, EXPENSE_PUBLICATION_JOB_TYPE, limit),
            )
            return tuple(
                ExpenseArtifact(
                    id=str(row["id"]),
                    sha256=str(row["sha256"]),
                    object_key=str(row["object_key"]),
                    byte_size=int(row["byte_size"]),
                    parent_record_id=str(row["parent_record_id"]),
                    source_url=str(row["source_url"]),
                )
                for row in result.fetchall()
            )
        finally:
            connection.close()

    def persist_validated_report(
        self,
        artifact: ExpenseArtifact,
        batch: ExpensePublicationBatch,
    ) -> int:
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '30s'")
                connection.execute("set local lock_timeout = '5s'")
                body_result = connection.execute(
                    """
                    select id
                    from org.public_bodies
                    where ibge_code = '2903201'
                      and body_type = 'executive'
                      and active_until is null
                    order by version desc, created_at desc, id desc
                    limit 1
                    """
                ).fetchone()
                if body_result is None:
                    raise RuntimeError("órgão executivo municipal não encontrado")
                public_body_id = str(body_result["id"])
                report_row = connection.execute(
                    """
                    insert into finance.expense_reports (
                      origin_raw_record_id, source_document_artifact_id,
                      public_body_id, version, external_id, fiscal_year,
                      period_start, period_end, total_fixed_amount,
                      total_additions_amount, total_reductions_amount,
                      total_updated_amount, total_committed_period_amount,
                      total_committed_to_date_amount, total_liquidated_period_amount,
                      total_liquidated_to_date_amount, total_paid_period_amount,
                      total_paid_to_date_amount, total_unpaid_committed_amount,
                      total_balance_amount, methodology_version,
                      validation_status, published_at
                    ) values (
                      %s::uuid, %s::uuid, %s::uuid, 1, %s, %s,
                      %s::date, %s::date, %s, %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s, %s, %s, 'validated', statement_timestamp()
                    )
                    on conflict (source_document_artifact_id, version)
                    do nothing
                    returning id::text
                    """,
                    (
                        artifact.parent_record_id,
                        artifact.id,
                        public_body_id,
                        f"{artifact.sha256}:{batch.batch_sha256}",
                        batch.fiscal_year,
                        batch.period_start,
                        batch.period_end,
                        batch.total_fixed_amount,
                        batch.total_additions_amount,
                        batch.total_reductions_amount,
                        batch.total_updated_amount,
                        batch.total_committed_period_amount,
                        batch.total_committed_to_date_amount,
                        batch.total_liquidated_period_amount,
                        batch.total_liquidated_to_date_amount,
                        batch.total_paid_period_amount,
                        batch.total_paid_to_date_amount,
                        batch.total_unpaid_committed_amount,
                        batch.total_balance_amount,
                        batch.methodology_version,
                    ),
                ).fetchone()
                if report_row is None:
                    return 0
                report_id = str(report_row["id"])
                for row in batch.rows:
                    line_row = connection.execute(
                        """
                        insert into finance.expense_lines (
                          report_id, origin_raw_record_id, line_number,
                          expense_code, description, source_code, fixed_amount,
                          additions_amount, reductions_amount, updated_amount,
                          committed_period_amount, committed_to_date_amount,
                          liquidated_period_amount, liquidated_to_date_amount,
                          paid_period_amount, paid_to_date_amount,
                          unpaid_committed_amount, balance_amount,
                          methodology_version
                        ) values (
                          %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s,
                          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        on conflict (report_id, line_number) do nothing
                        returning id::text
                        """,
                        (
                            report_id,
                            artifact.parent_record_id,
                            row.line_number,
                            row.expense_code,
                            row.description,
                            row.source_code,
                            row.fixed_amount,
                            row.additions_amount,
                            row.reductions_amount,
                            row.updated_amount,
                            row.committed_period_amount,
                            row.committed_to_date_amount,
                            row.liquidated_period_amount,
                            row.liquidated_to_date_amount,
                            row.paid_period_amount,
                            row.paid_to_date_amount,
                            row.unpaid_committed_amount,
                            row.balance_amount,
                            batch.methodology_version,
                        ),
                    ).fetchone()
                    if line_row is None:
                        continue
                    connection.execute(
                        """
                        insert into evidence.evidence_items (
                          target_type, target_id, raw_artifact_id, raw_record_id,
                          evidence_kind, source_url, excerpt, locator,
                          content_sha256, parser_version, is_primary
                        ) values (
                          'finance.expense_lines', %s::uuid, %s::uuid, %s::uuid,
                          'document', %s, %s, %s::jsonb, %s, %s, true
                        )
                        """,
                        (
                            line_row["id"],
                            artifact.id,
                            artifact.parent_record_id,
                            artifact.source_url,
                            f"{row.description} — "
                            f"{batch.period_start} a {batch.period_end}",
                            f'{{"line_number": {row.line_number}, '
                            f'"expense_code": "{row.expense_code}"}}',
                            artifact.sha256,
                            batch.methodology_version,
                        ),
                    )
                return len(batch.rows)
        finally:
            connection.close()

    def record_failure(
        self,
        artifact: ExpenseArtifact,
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
                    artifact.id,
                    EXPENSE_PUBLICATION_JOB_TYPE,
                    _failure_key(artifact.sha256),
                    error_code,
                    error_detail[:1000],
                ),
            )
        finally:
            connection.close()


def _failure_key(artifact_sha256: str) -> str:
    return hashlib.sha256(
        f"{EXPENSE_PUBLICATION_JOB_TYPE}:{artifact_sha256}".encode()
    ).hexdigest()
