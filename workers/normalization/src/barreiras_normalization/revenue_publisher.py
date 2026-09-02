"""Publicador idempotente de receitas extraídas de PDFs preservados."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Protocol

from .financial_revenue_pdf import parse_revenue_pdf_text
from .revenue_publication import (
    REVENUE_PUBLICATION_JOB_TYPE,
    RevenuePublicationBatch,
    build_publication_batch,
)
from .tcm_ba_revenue_pdf import parse_tcm_ba_revenue_pdf_text

TCM_BA_REVENUE_METHODOLOGY_VERSION = "tcm-ba-analytical-revenue/1.2.0"


class ArtifactMismatchError(RuntimeError):
    """Os bytes restaurados não correspondem ao artefato catalogado."""


class RevenueDocumentArtifact(Protocol):
    id: str
    sha256: str
    object_key: str
    byte_size: int
    parent_record_id: str
    source_url: str
    source_kind: str


@dataclass(frozen=True)
class RevenueArtifact:
    id: str
    sha256: str
    object_key: str
    byte_size: int
    parent_record_id: str
    source_url: str
    source_kind: str = "municipal"


@dataclass(frozen=True)
class RevenuePublishResult:
    artifact_id: str
    status: str
    published_rows: int = 0
    error_code: str | None = None


class ObjectReader(Protocol):
    def read(self, object_key: str) -> bytes: ...


class RevenuePublicationRepository(Protocol):
    def pending_documents(
        self,
        *,
        limit: int,
        fiscal_year_from: int,
        fiscal_year_to: int,
        artifact_sha256: str | None = None,
    ) -> tuple[RevenueArtifact, ...]: ...

    def persist_validated_report(
        self,
        artifact: RevenueArtifact,
        batch: RevenuePublicationBatch,
    ) -> int: ...

    def record_failure(
        self,
        artifact: RevenueArtifact,
        *,
        error_code: str,
        error_detail: str,
    ) -> None: ...


def default_pdf_text_extractor(raw_body: bytes) -> str:
    """Extrai apenas PDFs com texto embutido completo; OCR é outro estágio."""

    from barreiras_docproc.pdf_text import derive_pdf_text

    pdf = derive_pdf_text(raw_body)
    if pdf.pages_with_text != len(pdf.pages):
        raise ValueError("PDF possui páginas sem texto embutido; aguarda OCR")
    if not pdf.text.strip():
        raise ValueError("PDF sem texto canônico")
    return pdf.text


class RevenueReportPublisher:
    """Valida bytes, extrai linhas e solicita uma gravação transacional."""

    def __init__(
        self,
        *,
        object_reader: ObjectReader,
        repository: RevenuePublicationRepository,
        text_extractor: Callable[[bytes], str] = default_pdf_text_extractor,
        logger: logging.Logger | None = None,
    ) -> None:
        self.object_reader = object_reader
        self.repository = repository
        self.text_extractor = text_extractor
        self.logger = logger or logging.getLogger(__name__)

    def publish(self, artifact: RevenueArtifact) -> RevenuePublishResult:
        raw_body = self.object_reader.read(artifact.object_key)
        actual_hash = hashlib.sha256(raw_body).hexdigest()
        if actual_hash != artifact.sha256 or len(raw_body) != artifact.byte_size:
            raise ArtifactMismatchError(
                f"Artefato {artifact.id} diverge do hash ou tamanho catalogado."
            )
        text = self.text_extractor(raw_body)
        if artifact.source_kind == "municipal":
            report = parse_revenue_pdf_text(text)
            batch = build_publication_batch(report)
        elif artifact.source_kind == "tcm_ba":
            report = parse_tcm_ba_revenue_pdf_text(text)
            batch = replace(
                build_publication_batch(report),
                methodology_version=TCM_BA_REVENUE_METHODOLOGY_VERSION,
            )
        else:
            raise ValueError(
                f"origem de receita não suportada: {artifact.source_kind}"
            )
        published_rows = self.repository.persist_validated_report(artifact, batch)
        self.logger.info(
            "revenue_report_published",
            extra={
                "artifact_id": artifact.id,
                "period_end": batch.period_end,
                "published_rows": published_rows,
                "methodology_version": batch.methodology_version,
            },
        )
        return RevenuePublishResult(
            artifact_id=artifact.id,
            status="published" if published_rows else "already_published",
            published_rows=published_rows,
        )


class PostgresRevenuePublicationRepository:
    """Implementa seleção e publicação em uma transação PostgreSQL."""

    def __init__(self, connection_factory) -> None:
        self.connection_factory = connection_factory

    @classmethod
    def from_dsn(cls, database_url: str) -> PostgresRevenuePublicationRepository:
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
        artifact_sha256: str | None = None,
    ) -> tuple[RevenueArtifact, ...]:
        connection = self.connection_factory()
        try:
            result = connection.execute(
                """
                with municipal_candidates as (
                  select distinct on (document.id)
                    document.id,
                    document.sha256,
                    document.object_key,
                    document.byte_size,
                    record.id::text as parent_record_id,
                    document.source_url,
                    'municipal'::text as source_kind,
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
                    = 'municipal_transparency_pdc-resumo-execucao-da-receita'
                  and record.payload ->> 'ano' ~ '^[0-9]{4}$'
                  and (record.payload ->> 'ano')::integer between %s and %s
                  order by document.id, record.created_at desc, record.id desc
                ), tcm_ba_candidates as (
                  select distinct on (document.id)
                    document.id,
                    document.sha256,
                    document.object_key,
                    document.byte_size,
                    record.id::text as parent_record_id,
                    document.source_url,
                    'tcm_ba'::text as source_kind,
                    document.created_at
                  from raw.raw_artifacts as document
                  join raw.raw_artifacts as prepare
                    on prepare.id = document.parent_artifact_id
                  join raw.raw_artifacts as catalog
                    on catalog.id = prepare.parent_artifact_id
                  join raw.raw_records as record
                    on record.raw_artifact_id = catalog.id
                   and record.source_record_key
                     = document.metadata ->> 'source_record_key'
                  where document.artifact_kind = 'document'
                    and document.metadata ->> 'schema_name'
                      = 'tcm-ba-monthly-document'
                    and document.metadata ->> 'document_role' = 'pdf'
                    and document.source_url
                      = 'https://e.tcm.ba.gov.br/epp/PdfReadOnly/downloadDocumento.seam'
                    and prepare.artifact_kind = 'document'
                    and prepare.metadata ->> 'schema_name'
                      = 'tcm-ba-document-download-prepare'
                    and prepare.metadata ->> 'source_record_key'
                      = record.source_record_key
                    and record.record_type = 'tcm_ba_monthly_document'
                    and left(record.payload ->> 'category', 8) = 'PCMGE016'
                    and record.payload ->> 'unit'
                      = 'Prefeitura Municipal de BARREIRAS'
                    and record.payload ->> 'competence'
                      ~ '^(0[1-9]|1[0-2])/[0-9]{4}$'
                    and right(record.payload ->> 'competence', 4)::integer
                      between %s and %s
                  order by document.id, record.created_at desc, record.id desc
                ), candidates as (
                  select * from municipal_candidates
                  union all
                  select * from tcm_ba_candidates
                ), pending as (
                  select candidates.*
                  from candidates
                  where (%s::text is null or candidates.sha256 = %s::text)
                  and (
                    %s::text is not null
                    or not exists (
                      select 1
                      from finance.revenues as revenue
                      where revenue.source_document_artifact_id = candidates.id
                        and revenue.validation_status = 'validated'
                    )
                  )
                  and not exists (
                    select 1
                    from raw.extraction_jobs as job
                    where job.raw_artifact_id = candidates.id
                      and job.job_type = %s
                      and job.status = 'dead_lettered'
                  )
                )
                select id, sha256, object_key, byte_size, parent_record_id,
                  source_url, source_kind
                from pending
                order by created_at, id
                limit %s
                """,
                (
                    fiscal_year_from,
                    fiscal_year_to,
                    fiscal_year_from,
                    fiscal_year_to,
                    artifact_sha256,
                    artifact_sha256,
                    artifact_sha256,
                    REVENUE_PUBLICATION_JOB_TYPE,
                    limit,
                ),
            )
            return tuple(
                RevenueArtifact(
                    id=str(row["id"]),
                    sha256=str(row["sha256"]),
                    object_key=str(row["object_key"]),
                    byte_size=int(row["byte_size"]),
                    parent_record_id=str(row["parent_record_id"]),
                    source_url=str(row["source_url"]),
                    source_kind=str(row["source_kind"]),
                )
                for row in result.fetchall()
            )
        finally:
            connection.close()

    def persist_validated_report(
        self,
        artifact: RevenueArtifact,
        batch: RevenuePublicationBatch,
    ) -> int:
        connection = self.connection_factory()
        inserted = 0
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '20s'")
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
                    connection.execute(
                        """
                        insert into org.public_bodies (
                          origin_raw_record_id, ibge_code, official_code, name,
                          body_type, jurisdiction, state_code, active_from
                        ) values (
                          %s::uuid, '2903201', 'PREF-BARREIRAS',
                          'Prefeitura Municipal de Barreiras', 'executive',
                          'municipal', 'BA', %s::date
                        )
                         on conflict (ibge_code, body_type)
                           where ibge_code is not null and active_until is null
                         do nothing
                        """,
                        (artifact.parent_record_id, batch.period_start),
                    )
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

                for row in batch.rows:
                    external_id = f"{artifact.sha256}:{row.revenue_code}"
                    inserted_row = connection.execute(
                        """
                        insert into finance.revenues (
                          origin_raw_record_id, public_body_id,
                          source_document_artifact_id, version, external_id,
                          fiscal_year, revenue_date, revenue_code, description,
                          forecast_amount, collected_amount, accumulated_amount,
                          forecast_amount_signed, collected_amount_signed,
                          accumulated_amount_signed,
                          report_total_period_amount,
                          difference_more, difference_less, collection_direction,
                          methodology_version, validation_status, published_at
                        ) values (
                          %s::uuid, %s::uuid, %s::uuid, 1, %s,
                          %s, %s::date, %s, %s,
                          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                          %s, 'validated', statement_timestamp()
                        )
                         on conflict (public_body_id, external_id, version)
                           where external_id is not null
                         do nothing
                        returning id::text
                        """,
                        (
                            artifact.parent_record_id,
                            public_body_id,
                            artifact.id,
                            external_id,
                            batch.fiscal_year,
                            batch.period_end,
                            row.revenue_code,
                            row.description,
                            row.forecast_amount,
                            row.collected_amount,
                            row.accumulated_amount,
                            row.forecast_amount_signed,
                            row.collected_amount_signed,
                            row.accumulated_amount_signed,
                            batch.total_period_amount,
                            row.difference_more,
                            row.difference_less,
                            row.collection_direction,
                            batch.methodology_version,
                        ),
                    ).fetchone()
                    if inserted_row is None:
                        continue
                    inserted += 1
                    connection.execute(
                        """
                        insert into evidence.evidence_items (
                          target_type, target_id, raw_artifact_id, raw_record_id,
                          evidence_kind, source_url, excerpt, locator,
                          content_sha256, parser_version, is_primary
                        ) values (
                          'finance.revenues', %s::uuid, %s::uuid, %s::uuid,
                          'document', %s, %s, %s::jsonb, %s, %s, true
                        )
                        """,
                        (
                            inserted_row["id"],
                            artifact.id,
                            artifact.parent_record_id,
                            artifact.source_url,
                            row.description,
                            f'{{"period_end": "{batch.period_end}", '
                            f'"revenue_code": "{row.revenue_code}"}}',
                            artifact.sha256,
                            batch.methodology_version,
                        ),
                    )
                self._record_success(connection, artifact)
            return inserted
        finally:
            connection.close()

    def record_failure(
        self,
        artifact: RevenueArtifact,
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
                    REVENUE_PUBLICATION_JOB_TYPE,
                    _failure_key(artifact.sha256),
                    error_code,
                    error_detail[:1000],
                ),
            )
        finally:
            connection.close()

    @staticmethod
    def _record_success(connection, artifact: RevenueArtifact) -> None:
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
                REVENUE_PUBLICATION_JOB_TYPE,
                _failure_key(artifact.sha256),
            ),
        )


def _failure_key(artifact_sha256: str) -> str:
    return hashlib.sha256(
        f"{REVENUE_PUBLICATION_JOB_TYPE}:{artifact_sha256}".encode()
    ).hexdigest()
