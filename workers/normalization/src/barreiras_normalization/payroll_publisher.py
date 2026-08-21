"""Publicador idempotente dos totais mensais da folha municipal."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from .payroll_report_pdf import (
    PAYROLL_REPORT_PARSER_VERSION,
    PayrollReportAggregate,
    parse_payroll_report_aggregate,
)
from .revenue_publisher import ArtifactMismatchError

PAYROLL_PUBLICATION_JOB_TYPE = "payroll_report_publication/1.2.0"
PAYROLL_SOURCE_CODE = "prefeitura-barreiras-transparencia"
PAYROLL_ENDPOINT_CODE = "dados-abertos-api"


@dataclass(frozen=True)
class PayrollArtifact:
    id: str
    sha256: str
    object_key: str
    byte_size: int
    parent_record_id: str
    source_url: str
    reference_month: date


@dataclass(frozen=True)
class PayrollPublishResult:
    artifact_id: str
    status: str


class ObjectReader(Protocol):
    def read(self, object_key: str) -> bytes: ...


class PayrollPublicationRepository(Protocol):
    def pending_documents(
        self,
        *,
        limit: int,
        fiscal_year_from: int,
        fiscal_year_to: int,
        reference_month: date | None = None,
    ) -> tuple[PayrollArtifact, ...]: ...

    def persist_validated_report(
        self,
        artifact: PayrollArtifact,
        report: PayrollReportAggregate,
    ) -> int: ...

    def record_failure(
        self,
        artifact: PayrollArtifact,
        *,
        error_code: str,
        error_detail: str,
    ) -> None: ...

    def has_public_month(self, reference_month: date) -> bool: ...

    def unresolved_document_count(self, reference_month: date) -> int: ...


def default_payroll_pdf_text_extractor(raw_body: bytes) -> str:
    """Extrai o texto visual somente quando todas as páginas são legíveis."""

    from barreiras_docproc.pdf_text import derive_pdf_layout_text

    pdf = derive_pdf_layout_text(raw_body)
    if pdf.pages_with_text != len(pdf.pages):
        raise ValueError("PDF da folha possui páginas sem texto; publicação bloqueada")
    if not pdf.text.strip():
        raise ValueError("PDF da folha sem texto em layout")
    return pdf.text


class PayrollReportPublisher:
    """Confere o artefato e envia somente o agregado reconciliado ao banco."""

    def __init__(
        self,
        *,
        object_reader: ObjectReader,
        repository: PayrollPublicationRepository,
        text_extractor: Callable[[bytes], str] = default_payroll_pdf_text_extractor,
        logger: logging.Logger | None = None,
    ) -> None:
        self.object_reader = object_reader
        self.repository = repository
        self.text_extractor = text_extractor
        self.logger = logger or logging.getLogger(__name__)

    def publish(self, artifact: PayrollArtifact) -> PayrollPublishResult:
        raw_body = self.object_reader.read(artifact.object_key)
        actual_hash = hashlib.sha256(raw_body).hexdigest()
        if actual_hash != artifact.sha256 or len(raw_body) != artifact.byte_size:
            raise ArtifactMismatchError(
                f"Artefato {artifact.id} diverge do hash ou tamanho catalogado."
            )
        text = self.text_extractor(raw_body)
        report = parse_payroll_report_aggregate(text)
        inserted = self.repository.persist_validated_report(artifact, report)
        self.logger.info(
            "payroll_report_published",
            extra={
                "artifact_id": artifact.id,
                "reference_month": artifact.reference_month.isoformat(),
                "status": "published" if inserted else "already_published",
                "parser_version": report.parser_version,
            },
        )
        return PayrollPublishResult(
            artifact_id=artifact.id,
            status="published" if inserted else "already_published",
        )


class PostgresPayrollPublicationRepository:
    """Seleciona PDFs tipo 1 e persiste uma versão mensal transacional."""

    def __init__(self, connection_factory) -> None:
        self.connection_factory = connection_factory

    @classmethod
    def from_dsn(cls, database_url: str) -> PostgresPayrollPublicationRepository:
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
        reference_month: date | None = None,
    ) -> tuple[PayrollArtifact, ...]:
        connection = self.connection_factory()
        try:
            result = connection.execute(
                """
                with candidates as (
                  select distinct on (document.id)
                    document.id::text,
                    document.sha256,
                    document.object_key,
                    document.byte_size,
                    record.id::text as parent_record_id,
                    document.source_url,
                    case
                      when record.payload ->> 'ano_ref'
                        ~ '^(20[2-9][0-9]|2100)$'
                        and record.payload ->> 'mes_ref'
                          ~ '^(?:[1-9]|1[0-2])$'
                      then make_date(
                        (record.payload ->> 'ano_ref')::integer,
                        (record.payload ->> 'mes_ref')::integer,
                        1
                      )
                    end as reference_month,
                    document.created_at
                  from raw.raw_artifacts as document
                  join raw.raw_artifacts as parent_artifact
                    on parent_artifact.id = document.parent_artifact_id
                  join raw.raw_records as record
                    on record.raw_artifact_id = parent_artifact.id
                  join source.source_endpoints as endpoint
                    on endpoint.id = parent_artifact.source_endpoint_id
                  join source.data_sources as data_source
                    on data_source.id = endpoint.data_source_id
                  where document.artifact_kind = 'document'
                    and data_source.slug = %s
                    and endpoint.slug = %s
                    and document.metadata ->> 'schema_name'
                      = 'municipal-transparency-document'
                    and document.metadata ->> 'source_record_key'
                      = record.source_record_key
                    and document.source_url = record.payload ->> 'url'
                    and record.record_type
                      = 'municipal_transparency_servidores'
                    and regexp_replace(
                      btrim(translate(
                        normalize(
                          lower(coalesce(record.payload ->> 'titulo', '')),
                          NFKD
                        ),
                        U&'\0300\0301\0302\0303\0308\0327',
                        ''
                      )),
                      '[[:space:]]+', ' ', 'g'
                    ) in (
                      'relacao de servidores',
                      'relacao servidores',
                      'relacao de servidores 13o salario'
                    )
                    and (
                      record.payload ->> 'tipo' = '1'
                      or (
                        coalesce(trim(record.payload ->> 'tipo'), '') = ''
                        and regexp_replace(
                          btrim(translate(
                            normalize(
                              lower(coalesce(record.payload ->> 'titulo', '')),
                              NFKD
                            ),
                            U&'\0300\0301\0302\0303\0308\0327',
                            ''
                          )),
                          '[[:space:]]+',
                          ' ',
                          'g'
                        ) = 'relacao de servidores'
                      )
                    )
                    and case
                      when record.payload ->> 'ano_ref'
                        ~ '^(20[2-9][0-9]|2100)$'
                        and record.payload ->> 'mes_ref'
                          ~ '^(?:[1-9]|1[0-2])$'
                      then
                        (record.payload ->> 'ano_ref')::integer
                          between %s and %s
                        and make_date(
                          (record.payload ->> 'ano_ref')::integer,
                          (record.payload ->> 'mes_ref')::integer,
                          1
                        ) = coalesce(
                          %s::date,
                          make_date(
                            (record.payload ->> 'ano_ref')::integer,
                            (record.payload ->> 'mes_ref')::integer,
                            1
                          )
                        )
                      else false
                    end
                    and not exists (
                      select 1
                      from hr.payroll_report_aggregates as aggregate
                      where aggregate.source_document_artifact_id = document.id
                        and aggregate.parser_version = %s
                    )
                    and not exists (
                      select 1
                      from raw.extraction_jobs as job
                      where job.raw_artifact_id = document.id
                        and job.job_type = %s
                        and job.status in ('failed', 'dead_lettered')
                    )
                  order by document.id, record.created_at desc, record.id desc
                )
                select id, sha256, object_key, byte_size, parent_record_id,
                  source_url, reference_month
                from candidates
                order by reference_month asc, created_at asc, id
                limit %s
                """,
                (
                    PAYROLL_SOURCE_CODE,
                    PAYROLL_ENDPOINT_CODE,
                    fiscal_year_from,
                    fiscal_year_to,
                    reference_month,
                    PAYROLL_REPORT_PARSER_VERSION,
                    PAYROLL_PUBLICATION_JOB_TYPE,
                    limit,
                ),
            )
            return tuple(
                PayrollArtifact(
                    id=str(row["id"]),
                    sha256=str(row["sha256"]),
                    object_key=str(row["object_key"]),
                    byte_size=int(row["byte_size"]),
                    parent_record_id=str(row["parent_record_id"]),
                    source_url=str(row["source_url"]),
                    reference_month=row["reference_month"],
                )
                for row in result.fetchall()
            )
        finally:
            connection.close()

    def unresolved_document_count(self, reference_month: date) -> int:
        """Conta PDFs oficiais do mês ainda sem agregado na versão vigente."""

        connection = self.connection_factory()
        try:
            row = connection.execute(
                """
                select count(distinct document.id)::integer as unresolved_count
                from raw.raw_artifacts as document
                join raw.raw_artifacts as parent_artifact
                  on parent_artifact.id = document.parent_artifact_id
                join raw.raw_records as record
                  on record.raw_artifact_id = parent_artifact.id
                join source.source_endpoints as endpoint
                  on endpoint.id = parent_artifact.source_endpoint_id
                join source.data_sources as data_source
                  on data_source.id = endpoint.data_source_id
                where document.artifact_kind = 'document'
                  and document.metadata ->> 'schema_name'
                    = 'municipal-transparency-document'
                  and document.metadata ->> 'source_record_key'
                    = record.source_record_key
                  and document.source_url = record.payload ->> 'url'
                  and record.record_type
                    = 'municipal_transparency_servidores'
                  and data_source.slug = %s
                  and endpoint.slug = %s
                  and regexp_replace(
                    btrim(translate(
                      normalize(
                        lower(coalesce(record.payload ->> 'titulo', '')),
                        NFKD
                      ),
                      U&'\0300\0301\0302\0303\0308\0327',
                      ''
                    )),
                    '[[:space:]]+', ' ', 'g'
                  ) in (
                    'relacao de servidores',
                    'relacao servidores',
                    'relacao de servidores 13o salario'
                  )
                  and (
                    record.payload ->> 'tipo' = '1'
                    or (
                      coalesce(trim(record.payload ->> 'tipo'), '') = ''
                      and regexp_replace(
                        btrim(translate(
                          normalize(
                            lower(coalesce(record.payload ->> 'titulo', '')),
                            NFKD
                          ),
                          U&'\0300\0301\0302\0303\0308\0327',
                          ''
                        )),
                        '[[:space:]]+', ' ', 'g'
                      ) = 'relacao de servidores'
                    )
                  )
                  and record.payload ->> 'ano_ref'
                    ~ '^(20[2-9][0-9]|2100)$'
                  and record.payload ->> 'mes_ref' ~ '^(?:[1-9]|1[0-2])$'
                  and make_date(
                    (record.payload ->> 'ano_ref')::integer,
                    (record.payload ->> 'mes_ref')::integer,
                    1
                  ) = %s::date
                  and not exists (
                    select 1
                    from hr.payroll_report_aggregates as aggregate
                    where aggregate.source_document_artifact_id = document.id
                      and aggregate.parser_version = %s
                  )
                """,
                (
                    PAYROLL_SOURCE_CODE,
                    PAYROLL_ENDPOINT_CODE,
                    reference_month,
                    PAYROLL_REPORT_PARSER_VERSION,
                ),
            ).fetchone()
            return 0 if row is None else int(row["unresolved_count"])
        finally:
            connection.close()

    def has_public_month(self, reference_month: date) -> bool:
        """Confirma a competência na mesma projeção determinística do portal."""

        connection = self.connection_factory()
        try:
            row = connection.execute(
                "select hr.payroll_month_is_public(%s::date) as is_public",
                (reference_month,),
            ).fetchone()
            return row is not None and bool(row["is_public"])
        finally:
            connection.close()

    def persist_validated_report(
        self,
        artifact: PayrollArtifact,
        report: PayrollReportAggregate,
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
                lock_key = (
                    f"payroll:{public_body_id}:"
                    f"{artifact.reference_month.isoformat()}:"
                    f"{report.payroll_cycle}"
                )
                connection.execute(
                    "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (lock_key,),
                )
                previous = connection.execute(
                    """
                    select id::text, version
                    from hr.payroll_report_aggregates
                    where public_body_id = %s::uuid
                      and report_kind = 'municipal_staff'
                      and reference_month = %s::date
                      and payroll_cycle = %s
                    order by version desc, created_at desc, id desc
                    limit 1
                    """,
                    (
                        public_body_id,
                        artifact.reference_month,
                        report.payroll_cycle,
                    ),
                ).fetchone()
                supersedes_id = None if previous is None else str(previous["id"])
                version = 1 if previous is None else int(previous["version"]) + 1
                aggregate = connection.execute(
                    """
                    insert into hr.payroll_report_aggregates (
                      origin_raw_record_id, source_document_artifact_id,
                      public_body_id, supersedes_id, version, reference_month,
                      payroll_cycle, employee_count, gross_amount,
                      deduction_amount, net_amount, subtotal_count,
                      parser_version, validated_at
                    ) values (
                      %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s, %s::date,
                      %s, %s, %s, %s, %s, %s, %s, statement_timestamp()
                    )
                    on conflict (source_document_artifact_id, parser_version)
                    do nothing
                    returning id::text
                    """,
                    (
                        artifact.parent_record_id,
                        artifact.id,
                        public_body_id,
                        supersedes_id,
                        version,
                        artifact.reference_month,
                        report.payroll_cycle,
                        report.employee_count,
                        report.gross_amount,
                        report.deduction_amount,
                        report.net_amount,
                        report.subtotal_count,
                        report.parser_version,
                    ),
                ).fetchone()
                if aggregate is None:
                    return 0
                connection.execute(
                    """
                    insert into evidence.evidence_items (
                      target_type, target_id, raw_artifact_id, raw_record_id,
                      evidence_kind, source_url, excerpt, locator,
                      content_sha256, parser_version, is_primary
                    ) values (
                      'hr.payroll_report_aggregates', %s::uuid, %s::uuid,
                      %s::uuid, 'document', %s,
                      'Componente mensal reconciliado com os subtotais do PDF oficial.',
                      jsonb_build_object(
                        'reference_month', %s::text,
                        'payroll_cycle', %s::text
                      ),
                      %s, %s, true
                    )
                    """,
                    (
                        aggregate["id"],
                        artifact.id,
                        artifact.parent_record_id,
                        artifact.source_url,
                        artifact.reference_month.isoformat(),
                        report.payroll_cycle,
                        artifact.sha256,
                        report.parser_version,
                    ),
                )
                return 1
        finally:
            connection.close()

    def record_failure(
        self,
        artifact: PayrollArtifact,
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
                    PAYROLL_PUBLICATION_JOB_TYPE,
                    _failure_key(artifact.sha256),
                    error_code,
                    error_detail[:1000],
                ),
            )
        finally:
            connection.close()


def _failure_key(artifact_sha256: str) -> str:
    return hashlib.sha256(
        f"{PAYROLL_PUBLICATION_JOB_TYPE}:{artifact_sha256}".encode()
    ).hexdigest()
