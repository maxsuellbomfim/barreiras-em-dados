"""Publicador idempotente de demonstrativos de despesas preservados."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from .expense_publication import (
    EXPENSE_PUBLICATION_METHODOLOGY_VERSION,
    ExpensePublicationBatch,
    ExpensePublicationError,
    build_expense_publication_batch,
)
from .financial_expense_pdf import parse_expense_pdf_text
from .revenue_publisher import ArtifactMismatchError, default_pdf_text_extractor

EXPENSE_PUBLICATION_JOB_TYPE = "financial_expense_publication"


class ExpensePublicationIntegrityError(ExpensePublicationError):
    """O replay diverge das linhas financeiras já publicadas."""


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


@dataclass(frozen=True)
class ExpenseReportVersionPlan:
    action: str
    version: int
    origin_raw_record_id: str
    supersedes_id: str | None
    report_id: str | None = None


def _methodology_revision(value: object) -> tuple[int, int, int] | None:
    prefix = "public-expense-pdf/"
    if not isinstance(value, str) or not value.startswith(prefix):
        return None
    parts = value.removeprefix(prefix).split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)  # type: ignore[return-value]


def plan_expense_report_version(
    current: Mapping[str, object] | None,
    *,
    artifact: ExpenseArtifact,
    batch: ExpensePublicationBatch,
) -> ExpenseReportVersionPlan:
    """Decide entre replay idêntico e nova versão auditável do relatório."""

    expected_external_id = f"{artifact.sha256}:{batch.batch_sha256}"
    if current is None:
        return ExpenseReportVersionPlan(
            action="insert",
            version=1,
            origin_raw_record_id=artifact.parent_record_id,
            supersedes_id=None,
        )

    report_id = str(current["id"])
    origin_raw_record_id = str(current["origin_raw_record_id"])
    version = int(current["version"])
    current_methodology = current["methodology_version"]
    current_revision = _methodology_revision(current_methodology)
    next_revision = _methodology_revision(batch.methodology_version)
    if current_revision is None or next_revision is None:
        raise ExpensePublicationIntegrityError(
            "versão metodológica do relatório é inválida"
        )
    if current_revision == next_revision:
        if current.get("external_id") != expected_external_id:
            raise ExpensePublicationIntegrityError(
                "artefato imutável diverge na mesma versão metodológica"
            )
        return ExpenseReportVersionPlan(
            action="reuse",
            version=version,
            origin_raw_record_id=origin_raw_record_id,
            supersedes_id=None,
            report_id=report_id,
        )
    if current_revision > next_revision:
        raise ExpensePublicationIntegrityError(
            "metodologia atual do relatório é mais nova que o publicador"
        )
    return ExpenseReportVersionPlan(
        action="insert",
        version=version + 1,
        origin_raw_record_id=origin_raw_record_id,
        supersedes_id=report_id,
    )


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
                with ranked_reports as materialized (
                  select
                    report.*,
                    row_number() over (
                      partition by report.source_document_artifact_id
                      order by report.version desc, report.created_at desc,
                        report.id desc
                    ) as current_row
                  from finance.expense_reports as report
                  where report.validation_status = 'validated'
                    and report.published_at is not null
                    and report.fiscal_year between %s and %s
                ), current_reports as materialized (
                  select * from ranked_reports where current_row = 1
                ), replay_candidates as (
                  select distinct on (document.id)
                    document.id::text,
                    document.sha256,
                    document.object_key,
                    document.byte_size,
                    report.origin_raw_record_id::text as parent_record_id,
                    document.source_url,
                    document.created_at
                  from current_reports as report
                  join raw.raw_artifacts as document
                    on document.id = report.source_document_artifact_id
                  where report.methodology_version <> %s
                    or exists (
                        select 1
                        from finance.expense_lines as line
                        left join finance.expense_line_budget_units as allocation
                          on allocation.expense_line_id = line.id
                        where line.report_id = report.id
                          and line.origin_raw_record_id =
                            report.origin_raw_record_id
                          and allocation.expense_line_id is null
                        limit 1
                    )
                  order by document.id, report.version desc,
                    report.created_at desc, report.id desc
                ), new_candidates as (
                  select distinct on (document.id)
                    document.id::text,
                    document.sha256,
                    document.object_key,
                    document.byte_size,
                    record.id::text as parent_record_id,
                    document.source_url,
                    document.created_at
                  from raw.raw_artifacts as document
                  join raw.raw_artifacts as parent_artifact
                    on parent_artifact.id = document.parent_artifact_id
                  join raw.raw_records as record
                    on record.raw_artifact_id = parent_artifact.id
                  where document.artifact_kind = 'document'
                  and document.metadata ->> 'schema_name'
                    = 'municipal-transparency-document'
                  and document.metadata ->> 'source_record_key'
                    = record.source_record_key
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
                  order by document.id, record.created_at desc, record.id desc
                ), candidates as (
                  select * from replay_candidates
                  union all
                  select * from new_candidates
                )
                select id, sha256, object_key, byte_size, parent_record_id,
                  source_url
                from candidates
                where not exists (
                  select 1
                  from raw.extraction_jobs as job
                  where job.raw_artifact_id = candidates.id::uuid
                    and job.job_type = %s
                    and job.status = 'dead_lettered'
                )
                order by created_at, id
                limit %s
                """,
                (
                    fiscal_year_from,
                    fiscal_year_to,
                    EXPENSE_PUBLICATION_METHODOLOGY_VERSION,
                    fiscal_year_from,
                    fiscal_year_to,
                    EXPENSE_PUBLICATION_JOB_TYPE,
                    limit,
                ),
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
                connection.execute(
                    "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (artifact.id,),
                )
                current_report = connection.execute(
                    """
                    select
                      report.id::text as id,
                      report.origin_raw_record_id::text as origin_raw_record_id,
                      report.version,
                      report.external_id,
                      report.methodology_version
                    from finance.expense_reports as report
                    where report.source_document_artifact_id = %s::uuid
                      and report.validation_status = 'validated'
                      and report.published_at is not null
                    order by report.version desc, report.created_at desc,
                      report.id desc
                    limit 1
                    """,
                    (artifact.id,),
                ).fetchone()
                plan = plan_expense_report_version(
                    current_report,
                    artifact=artifact,
                    batch=batch,
                )
                if plan.action == "reuse":
                    if plan.report_id is None:
                        raise ExpensePublicationIntegrityError(
                            "plano de replay não identificou o relatório"
                        )
                    self._persist_existing_report_allocations(
                        connection,
                        artifact=artifact,
                        batch=batch,
                        report_id=plan.report_id,
                        origin_raw_record_id=plan.origin_raw_record_id,
                    )
                    self._persist_total_source_conflicts(
                        connection,
                        artifact=artifact,
                        batch=batch,
                        report_id=plan.report_id,
                        origin_raw_record_id=plan.origin_raw_record_id,
                    )
                    self._record_success(connection, artifact)
                    return 0

                report_row = connection.execute(
                    """
                    insert into finance.expense_reports (
                      origin_raw_record_id, source_document_artifact_id,
                      public_body_id, supersedes_id, version, external_id,
                      fiscal_year,
                      period_start, period_end, total_fixed_amount,
                      total_additions_amount, total_reductions_amount,
                      total_updated_amount, total_committed_period_amount,
                      total_committed_to_date_amount, total_liquidated_period_amount,
                      total_liquidated_to_date_amount, total_paid_period_amount,
                      total_paid_to_date_amount, total_unpaid_committed_amount,
                      total_balance_amount, methodology_version,
                      validation_status, published_at
                    ) values (
                      %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s,
                      %s::date, %s::date, %s, %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s, %s, %s, 'validated', statement_timestamp()
                    )
                    on conflict (source_document_artifact_id, version)
                    do nothing
                    returning id::text
                    """,
                    (
                        plan.origin_raw_record_id,
                        artifact.id,
                        public_body_id,
                        plan.supersedes_id,
                        plan.version,
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
                    raise ExpensePublicationIntegrityError(
                        "nova versão do relatório não foi persistida"
                    )
                report_id = str(report_row["id"])
                published_lines = self._persist_new_report_lines(
                    connection,
                    artifact=artifact,
                    batch=batch,
                    report_id=report_id,
                    origin_raw_record_id=plan.origin_raw_record_id,
                )
                self._persist_existing_report_allocations(
                    connection,
                    artifact=artifact,
                    batch=batch,
                    report_id=report_id,
                    origin_raw_record_id=plan.origin_raw_record_id,
                )
                self._persist_total_source_conflicts(
                    connection,
                    artifact=artifact,
                    batch=batch,
                    report_id=report_id,
                    origin_raw_record_id=plan.origin_raw_record_id,
                )
                self._record_success(connection, artifact)
                return published_lines
        finally:
            connection.close()

    @staticmethod
    def _persist_new_report_lines(
        connection,
        *,
        artifact: ExpenseArtifact,
        batch: ExpensePublicationBatch,
        report_id: str,
        origin_raw_record_id: str,
    ) -> int:
        """Grava linhas e evidências de uma nova versão em dois lotes."""

        line_input = [
            {
                "report_id": report_id,
                "origin_raw_record_id": origin_raw_record_id,
                "line_number": row.line_number,
                "expense_code": row.expense_code,
                "description": row.description,
                "source_code": row.source_code,
                "fixed_amount": str(row.fixed_amount),
                "additions_amount": str(row.additions_amount),
                "reductions_amount": str(row.reductions_amount),
                "updated_amount": str(row.updated_amount),
                "committed_period_amount": str(row.committed_period_amount),
                "committed_to_date_amount": str(row.committed_to_date_amount),
                "liquidated_period_amount": str(row.liquidated_period_amount),
                "liquidated_to_date_amount": str(row.liquidated_to_date_amount),
                "paid_period_amount": str(row.paid_period_amount),
                "paid_to_date_amount": str(row.paid_to_date_amount),
                "unpaid_committed_amount": str(row.unpaid_committed_amount),
                "balance_amount": str(row.balance_amount),
                "methodology_version": batch.methodology_version,
            }
            for row in batch.rows
        ]
        inserted = connection.execute(
            """
            with input_rows as (
              select *
              from jsonb_to_recordset(%s::jsonb) as input_row (
                report_id uuid,
                origin_raw_record_id uuid,
                line_number integer,
                expense_code text,
                description text,
                source_code text,
                fixed_amount numeric,
                additions_amount numeric,
                reductions_amount numeric,
                updated_amount numeric,
                committed_period_amount numeric,
                committed_to_date_amount numeric,
                liquidated_period_amount numeric,
                liquidated_to_date_amount numeric,
                paid_period_amount numeric,
                paid_to_date_amount numeric,
                unpaid_committed_amount numeric,
                balance_amount numeric,
                methodology_version text
              )
            )
            insert into finance.expense_lines (
              report_id, origin_raw_record_id, line_number,
              expense_code, description, source_code, fixed_amount,
              additions_amount, reductions_amount, updated_amount,
              committed_period_amount, committed_to_date_amount,
              liquidated_period_amount, liquidated_to_date_amount,
              paid_period_amount, paid_to_date_amount,
              unpaid_committed_amount, balance_amount, methodology_version
            )
            select
              report_id, origin_raw_record_id, line_number,
              expense_code, description, source_code, fixed_amount,
              additions_amount, reductions_amount, updated_amount,
              committed_period_amount, committed_to_date_amount,
              liquidated_period_amount, liquidated_to_date_amount,
              paid_period_amount, paid_to_date_amount,
              unpaid_committed_amount, balance_amount, methodology_version
            from input_rows
            on conflict (report_id, line_number) do nothing
            returning id::text as id, line_number
            """,
            (json.dumps(line_input),),
        ).fetchall()
        line_id_by_number = {
            int(row["line_number"]): str(row["id"]) for row in inserted
        }
        expected_numbers = {row.line_number for row in batch.rows}
        if (
            len(inserted) != len(batch.rows)
            or set(line_id_by_number) != expected_numbers
        ):
            raise ExpensePublicationIntegrityError(
                "relatório novo não persistiu todas as linhas"
            )

        evidence_input = [
            {
                "target_id": line_id_by_number[row.line_number],
                "raw_artifact_id": artifact.id,
                "raw_record_id": origin_raw_record_id,
                "source_url": artifact.source_url,
                "excerpt": (
                    f"{row.description} — {batch.period_start} a {batch.period_end}"
                ),
                "locator": {
                    "line_number": row.line_number,
                    "expense_code": row.expense_code,
                },
                "content_sha256": artifact.sha256,
                "parser_version": batch.methodology_version,
            }
            for row in batch.rows
        ]
        connection.execute(
            """
            insert into evidence.evidence_items (
              target_type, target_id, raw_artifact_id, raw_record_id,
              evidence_kind, source_url, excerpt, locator,
              content_sha256, parser_version, is_primary
            )
            select
              'finance.expense_lines',
              input_row.target_id,
              input_row.raw_artifact_id,
              input_row.raw_record_id,
              'document',
              input_row.source_url,
              input_row.excerpt,
              input_row.locator,
              input_row.content_sha256,
              input_row.parser_version,
              true
            from jsonb_to_recordset(%s::jsonb) as input_row (
              target_id uuid,
              raw_artifact_id uuid,
              raw_record_id uuid,
              source_url text,
              excerpt text,
              locator jsonb,
              content_sha256 text,
              parser_version text
            )
            """,
            (json.dumps(evidence_input),),
        )
        return len(inserted)

    @staticmethod
    def _persist_total_source_conflicts(
        connection,
        *,
        artifact: ExpenseArtifact,
        batch: ExpensePublicationBatch,
        report_id: str,
        origin_raw_record_id: str,
    ) -> None:
        """Registra a divergência literal entre total geral e subtotais."""

        for conflict in batch.total_source_conflicts:
            existing = connection.execute(
                """
                select 1
                from evidence.source_conflicts
                where target_type = 'finance.expense_reports'
                  and target_id = %s::uuid
                  and field_name = %s
                  and status in ('open', 'accepted_difference')
                limit 1
                """,
                (report_id, conflict.field_name),
            ).fetchone()
            if existing is not None:
                continue
            declared_evidence = connection.execute(
                """
                insert into evidence.evidence_items (
                  target_type, target_id, raw_artifact_id, raw_record_id,
                  evidence_kind, source_url, excerpt, locator,
                  content_sha256, parser_version, is_primary
                ) values (
                  'finance.expense_reports', %s::uuid, %s::uuid, %s::uuid,
                  'document', %s, %s, %s::jsonb, %s, %s, true
                )
                returning id::text
                """,
                (
                    report_id,
                    artifact.id,
                    origin_raw_record_id,
                    artifact.source_url,
                    (
                        f"Total geral declarado em {conflict.field_name}: "
                        f"{conflict.declared_amount}"
                    ),
                    json.dumps(
                        {
                            "section": "Total",
                            "field_name": conflict.field_name,
                            "value": str(conflict.declared_amount),
                        },
                        separators=(",", ":"),
                    ),
                    artifact.sha256,
                    batch.methodology_version,
                ),
            ).fetchone()
            calculated_evidence = connection.execute(
                """
                insert into evidence.evidence_items (
                  target_type, target_id, raw_artifact_id, raw_record_id,
                  evidence_kind, source_url, excerpt, locator,
                  content_sha256, parser_version, is_primary
                ) values (
                  'finance.expense_reports', %s::uuid, %s::uuid, %s::uuid,
                  'document', %s, %s, %s::jsonb, %s, %s, true
                )
                returning id::text
                """,
                (
                    report_id,
                    artifact.id,
                    origin_raw_record_id,
                    artifact.source_url,
                    (
                        "Soma das linhas conferida contra os subtotais "
                        f"oficiais em {conflict.field_name}: "
                        f"{conflict.calculated_amount}"
                    ),
                    json.dumps(
                        {
                            "section": "Total da Unidade",
                            "field_name": conflict.field_name,
                            "value": str(conflict.calculated_amount),
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    artifact.sha256,
                    batch.methodology_version,
                ),
            ).fetchone()
            if declared_evidence is None or calculated_evidence is None:
                raise ExpensePublicationIntegrityError(
                    "evidência do conflito interno não foi persistida"
                )
            connection.execute(
                """
                insert into evidence.source_conflicts (
                  target_type, target_id, field_name,
                  first_evidence_item_id, second_evidence_item_id,
                  first_value, second_value, status
                ) values (
                  'finance.expense_reports', %s::uuid, %s,
                  %s::uuid, %s::uuid, %s::jsonb, %s::jsonb, 'open'
                )
                on conflict (
                  target_type, target_id, field_name,
                  first_evidence_item_id, second_evidence_item_id
                ) do nothing
                """,
                (
                    report_id,
                    conflict.field_name,
                    declared_evidence["id"],
                    calculated_evidence["id"],
                    json.dumps(
                        {"declared_amount": str(conflict.declared_amount)},
                        separators=(",", ":"),
                    ),
                    json.dumps(
                        {
                            "calculated_amount": str(
                                conflict.calculated_amount
                            ),
                            "difference_amount": str(conflict.difference_amount),
                        },
                        separators=(",", ":"),
                    ),
                ),
            )

    @staticmethod
    def _persist_existing_report_allocations(
        connection,
        *,
        artifact: ExpenseArtifact,
        batch: ExpensePublicationBatch,
        report_id: str,
        origin_raw_record_id: str,
    ) -> None:
        """Valida linhas existentes e grava todas as unidades em poucas consultas."""

        existing_lines = connection.execute(
            """
            select
              line.id::text as id,
              line.line_number,
              line.expense_code,
              line.description,
              line.source_code,
              line.fixed_amount,
              line.additions_amount,
              line.reductions_amount,
              line.updated_amount,
              line.committed_period_amount,
              line.committed_to_date_amount,
              line.liquidated_period_amount,
              line.liquidated_to_date_amount,
              line.paid_period_amount,
              line.paid_to_date_amount,
              line.unpaid_committed_amount,
              line.balance_amount
            from finance.expense_lines as line
            where line.report_id = %s::uuid
              and line.origin_raw_record_id = %s::uuid
            order by line.line_number
            """,
            (report_id, origin_raw_record_id),
        ).fetchall()
        expected_by_line_number = {row.line_number: row for row in batch.rows}
        if len(existing_lines) != len(expected_by_line_number):
            raise ExpensePublicationIntegrityError(
                "relatório existente possui quantidade divergente de linhas"
            )

        line_ids_by_number: dict[int, str] = {}
        for existing in existing_lines:
            line_number = int(existing["line_number"])
            expected = expected_by_line_number.get(line_number)
            if expected is None or line_number in line_ids_by_number:
                raise ExpensePublicationIntegrityError(
                    "relatório existente possui numeração divergente de linhas"
                )
            _assert_existing_line_matches(existing, expected)
            line_ids_by_number[line_number] = str(existing["id"])

        allocation_input = [
            {
                "expense_line_id": line_ids_by_number[row.line_number],
                "origin_raw_record_id": origin_raw_record_id,
                "source_document_artifact_id": artifact.id,
                "version": 1,
                "budget_unit_code": row.budget_unit_code,
                "budget_unit_name": row.budget_unit_name,
                "methodology_version": batch.methodology_version,
            }
            for row in batch.rows
        ]
        line_number_by_id = {
            line_id: line_number for line_number, line_id in line_ids_by_number.items()
        }
        allocations = connection.execute(
            """
            with input_rows as (
              select *
              from jsonb_to_recordset(%s::jsonb) as input_row (
                expense_line_id uuid,
                origin_raw_record_id uuid,
                source_document_artifact_id uuid,
                version integer,
                budget_unit_code text,
                budget_unit_name text,
                methodology_version text
              )
            ), inserted as (
              insert into finance.expense_line_budget_units (
                expense_line_id, origin_raw_record_id,
                source_document_artifact_id, version,
                budget_unit_code, budget_unit_name, methodology_version
              )
              select
                expense_line_id, origin_raw_record_id,
                source_document_artifact_id, version,
                budget_unit_code, budget_unit_name, methodology_version
              from input_rows
              on conflict (expense_line_id, version) do nothing
              returning
                id, expense_line_id, origin_raw_record_id,
                source_document_artifact_id, version,
                budget_unit_code, budget_unit_name, methodology_version
            )
            select
              inserted.id::text as id,
              inserted.expense_line_id::text as expense_line_id,
              inserted.origin_raw_record_id::text as origin_raw_record_id,
              inserted.source_document_artifact_id::text
                as source_document_artifact_id,
              inserted.version,
              inserted.budget_unit_code,
              inserted.budget_unit_name,
              inserted.methodology_version,
              true as inserted
            from inserted
            union all
            select
              existing.id::text as id,
              existing.expense_line_id::text as expense_line_id,
              existing.origin_raw_record_id::text as origin_raw_record_id,
              existing.source_document_artifact_id::text
                as source_document_artifact_id,
              existing.version,
              existing.budget_unit_code,
              existing.budget_unit_name,
              existing.methodology_version,
              false as inserted
            from input_rows
            join finance.expense_line_budget_units as existing
              on existing.expense_line_id = input_rows.expense_line_id
             and existing.version = input_rows.version
            where not exists (
              select 1 from inserted
              where inserted.expense_line_id = input_rows.expense_line_id
                and inserted.version = input_rows.version
            )
            order by expense_line_id
            """,
            (json.dumps(allocation_input),),
        ).fetchall()
        expected_by_line_id = {
            item["expense_line_id"]: item for item in allocation_input
        }
        if len(allocations) != len(expected_by_line_id):
            raise ExpensePublicationIntegrityError(
                "replay não reconciliou todas as unidades orçamentárias"
            )

        inserted_evidence: list[dict[str, object]] = []
        observed_line_ids: set[str] = set()
        for allocation in allocations:
            expense_line_id = str(allocation["expense_line_id"])
            expected = expected_by_line_id.get(expense_line_id)
            if expected is None or expense_line_id in observed_line_ids:
                raise ExpensePublicationIntegrityError(
                    "replay retornou unidade orçamentária inesperada"
                )
            observed_line_ids.add(expense_line_id)
            fields = (
                "origin_raw_record_id",
                "source_document_artifact_id",
                "version",
                "budget_unit_code",
                "budget_unit_name",
                "methodology_version",
            )
            if any(str(allocation[field]) != str(expected[field]) for field in fields):
                raise ExpensePublicationIntegrityError(
                    "unidade orçamentária publicada diverge do replay"
                )
            if allocation["inserted"]:
                inserted_evidence.append(
                    {
                        "target_id": str(allocation["id"]),
                        "raw_artifact_id": artifact.id,
                        "raw_record_id": origin_raw_record_id,
                        "source_url": artifact.source_url,
                        "excerpt": (
                            f"{expected['budget_unit_code']} - "
                            f"{expected['budget_unit_name']}"
                        ),
                        "locator": {
                            "line_number": line_number_by_id[expense_line_id],
                            "budget_unit_code": expected["budget_unit_code"],
                        },
                        "content_sha256": artifact.sha256,
                        "parser_version": batch.methodology_version,
                    }
                )

        if inserted_evidence:
            connection.execute(
                """
                insert into evidence.evidence_items (
                  target_type, target_id, raw_artifact_id, raw_record_id,
                  evidence_kind, source_url, excerpt, locator,
                  content_sha256, parser_version, is_primary
                )
                select
                  'finance.expense_line_budget_units',
                  input_row.target_id,
                  input_row.raw_artifact_id,
                  input_row.raw_record_id,
                  'document',
                  input_row.source_url,
                  input_row.excerpt,
                  input_row.locator,
                  input_row.content_sha256,
                  input_row.parser_version,
                  true
                from jsonb_to_recordset(%s::jsonb) as input_row (
                  target_id uuid,
                  raw_artifact_id uuid,
                  raw_record_id uuid,
                  source_url text,
                  excerpt text,
                  locator jsonb,
                  content_sha256 text,
                  parser_version text
                )
                """,
                (json.dumps(inserted_evidence),),
            )

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
                  status = case
                    when raw.extraction_jobs.attempt_count + 1 >=
                      raw.extraction_jobs.max_attempts
                    then 'dead_lettered'
                    else 'failed'
                  end,
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

    @staticmethod
    def _record_success(connection, artifact: ExpenseArtifact) -> None:
        connection.execute(
            """
            insert into raw.extraction_jobs (
              raw_artifact_id, job_type, idempotency_key, status,
              attempt_count, last_error_code, last_error_detail
            ) values (
              %s::uuid, %s, %s, 'succeeded', 1, null, null
            )
            on conflict (idempotency_key) do update set
              status = 'succeeded',
              attempt_count = raw.extraction_jobs.attempt_count + 1,
              last_error_code = null,
              last_error_detail = null,
              updated_at = statement_timestamp()
            """,
            (
                artifact.id,
                EXPENSE_PUBLICATION_JOB_TYPE,
                _failure_key(artifact.sha256),
            ),
        )


def _failure_key(artifact_sha256: str) -> str:
    return hashlib.sha256(
        f"{EXPENSE_PUBLICATION_JOB_TYPE}:{artifact_sha256}".encode()
    ).hexdigest()


def _assert_existing_line_matches(existing, expected) -> None:
    fields = (
        "expense_code",
        "description",
        "source_code",
        "fixed_amount",
        "additions_amount",
        "reductions_amount",
        "updated_amount",
        "committed_period_amount",
        "committed_to_date_amount",
        "liquidated_period_amount",
        "liquidated_to_date_amount",
        "paid_period_amount",
        "paid_to_date_amount",
        "unpaid_committed_amount",
        "balance_amount",
    )
    divergent = [
        field for field in fields if existing[field] != getattr(expected, field)
    ]
    if divergent:
        raise ExpensePublicationIntegrityError(
            "replay diverge da linha publicada: " + ", ".join(divergent)
        )
