"""Publicador idempotente de pagamentos de restos a pagar em balancetes."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from .public_obligation_pdf import (
    RestosAPagarSummary,
    parse_restos_a_pagar_summary,
)
from .revenue_publisher import ArtifactMismatchError, default_pdf_text_extractor

PUBLIC_OBLIGATION_JOB_TYPE = "public_obligation_balancete_publication/1.1.0"
PUBLIC_OBLIGATION_METHODOLOGY = "public-obligations-balancete/1.1.0"


@dataclass(frozen=True)
class PublicObligationArtifact:
    id: str
    sha256: str
    object_key: str
    byte_size: int
    parent_record_id: str
    source_url: str
    fiscal_year: int
    reference_month: int


@dataclass(frozen=True)
class PublicObligationPublishResult:
    artifact_id: str
    status: str


class ObjectReader(Protocol):
    def read(self, object_key: str) -> bytes: ...


class PublicObligationPublicationRepository(Protocol):
    def pending_documents(
        self,
        *,
        limit: int,
        fiscal_year_from: int,
        fiscal_year_to: int,
    ) -> tuple[PublicObligationArtifact, ...]: ...

    def persist_validated_summary(
        self,
        artifact: PublicObligationArtifact,
        summary: RestosAPagarSummary,
    ) -> int: ...

    def record_failure(
        self,
        artifact: PublicObligationArtifact,
        *,
        error_code: str,
        error_detail: str,
    ) -> None: ...


class PublicObligationPublisher:
    """Confere o artefato e publica somente a linha cujo total fecha."""

    def __init__(
        self,
        *,
        object_reader: ObjectReader,
        repository: PublicObligationPublicationRepository,
        text_extractor: Callable[[bytes], str] = default_pdf_text_extractor,
        logger: logging.Logger | None = None,
    ) -> None:
        self.object_reader = object_reader
        self.repository = repository
        self.text_extractor = text_extractor
        self.logger = logger or logging.getLogger(__name__)

    def publish(
        self,
        artifact: PublicObligationArtifact,
    ) -> PublicObligationPublishResult:
        raw_body = self.object_reader.read(artifact.object_key)
        actual_hash = hashlib.sha256(raw_body).hexdigest()
        if actual_hash != artifact.sha256 or len(raw_body) != artifact.byte_size:
            raise ArtifactMismatchError(
                f"Artefato {artifact.id} diverge do hash ou tamanho catalogado."
            )
        summary = parse_restos_a_pagar_summary(
            self.text_extractor(raw_body),
            fiscal_year=artifact.fiscal_year,
            reference_month=artifact.reference_month,
        )
        inserted = self.repository.persist_validated_summary(artifact, summary)
        self.logger.info(
            "public_obligation_summary_published",
            extra={
                "artifact_id": artifact.id,
                "period_end": summary.period_end.isoformat(),
                "inserted": inserted,
                "methodology_version": PUBLIC_OBLIGATION_METHODOLOGY,
            },
        )
        return PublicObligationPublishResult(
            artifact_id=artifact.id,
            status="published" if inserted else "already_published",
        )


class PostgresPublicObligationPublicationRepository:
    """Seleciona balancetes e grava a obrigação com sua evidência exata."""

    def __init__(self, connection_factory) -> None:
        self.connection_factory = connection_factory

    @classmethod
    def from_dsn(
        cls,
        database_url: str,
    ) -> PostgresPublicObligationPublicationRepository:
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
    ) -> tuple[PublicObligationArtifact, ...]:
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
                    coalesce(
                      record.payload ->> 'ano',
                      record.payload ->> 'ano_ref'
                    )::integer as fiscal_year,
                    coalesce(
                      record.payload ->> 'mes',
                      record.payload ->> 'mes_ref'
                    )::integer as reference_month,
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
                    and document.source_url = record.payload ->> 'url'
                    and record.record_type
                      = 'municipal_transparency_balancetes'
                    and coalesce(
                      record.payload ->> 'ano', record.payload ->> 'ano_ref'
                    )
                      ~ '^[0-9]{4}$'
                    and coalesce(
                      record.payload ->> 'mes', record.payload ->> 'mes_ref'
                    )
                      ~ '^(?:[1-9]|1[0-2])$'
                    and coalesce(
                      record.payload ->> 'ano', record.payload ->> 'ano_ref'
                    )::integer between %s and %s
                    and not exists (
                      select 1
                      from finance.public_obligations as obligation
                      where obligation.source_document_artifact_id = document.id
                        and obligation.obligation_type = 'restos_a_pagar_total'
                        and obligation.validation_state in ('validated', 'reconciled')
                    )
                    and not exists (
                      select 1
                      from raw.extraction_jobs as job
                      where job.raw_artifact_id = document.id
                        and job.job_type = %s
                        and job.status = 'failed'
                    )
                  order by document.id, record.created_at desc, record.id desc
                )
                select id, sha256, object_key, byte_size, parent_record_id,
                  source_url, fiscal_year, reference_month
                from candidates
                order by created_at, id
                limit %s
                """,
                (
                    fiscal_year_from,
                    fiscal_year_to,
                    PUBLIC_OBLIGATION_JOB_TYPE,
                    limit,
                ),
            )
            return tuple(
                PublicObligationArtifact(
                    id=str(row["id"]),
                    sha256=str(row["sha256"]),
                    object_key=str(row["object_key"]),
                    byte_size=int(row["byte_size"]),
                    parent_record_id=str(row["parent_record_id"]),
                    source_url=str(row["source_url"]),
                    fiscal_year=int(row["fiscal_year"]),
                    reference_month=int(row["reference_month"]),
                )
                for row in result.fetchall()
            )
        finally:
            connection.close()

    def persist_validated_summary(
        self,
        artifact: PublicObligationArtifact,
        summary: RestosAPagarSummary,
    ) -> int:
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '20s'")
                connection.execute("set local lock_timeout = '5s'")
                body = connection.execute(
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
                if body is None:
                    raise RuntimeError("órgão executivo municipal não encontrado")
                inserted = connection.execute(
                    """
                    insert into finance.public_obligations (
                      origin_raw_record_id, source_document_artifact_id,
                      public_body_id, obligation_key, obligation_type,
                      description, fiscal_year, period_start, period_end,
                      payments_prior_amount, payments_amount,
                      payments_to_date_amount, status, validation_state,
                      methodology_version, validated_at
                    ) values (
                      %s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s,
                      %s::date, %s::date, %s, %s, %s, 'reported', 'validated',
                      %s, statement_timestamp()
                    )
                    on conflict (public_body_id, obligation_key, version)
                    do nothing
                    returning id::text
                    """,
                    (
                        artifact.parent_record_id,
                        artifact.id,
                        str(body["id"]),
                        (
                            "restos-a-pagar-total:"
                            f"{summary.fiscal_year}-{summary.period_end.month:02d}"
                        ),
                        summary.obligation_type,
                        summary.description,
                        summary.fiscal_year,
                        summary.period_start.isoformat(),
                        summary.period_end.isoformat(),
                        summary.payments_prior_amount,
                        summary.payments_period_amount,
                        summary.payments_to_date_amount,
                        PUBLIC_OBLIGATION_METHODOLOGY,
                    ),
                ).fetchone()
                if inserted is None:
                    return 0
                connection.execute(
                    """
                    insert into evidence.evidence_items (
                      target_type, target_id, raw_artifact_id, raw_record_id,
                      evidence_kind, source_url, excerpt, locator,
                      content_sha256, parser_version, is_primary
                    ) values (
                      'finance.public_obligations', %s::uuid, %s::uuid, %s::uuid,
                      'document', %s, %s, %s::jsonb, %s, %s, true
                    )
                    """,
                    (
                        inserted["id"],
                        artifact.id,
                        artifact.parent_record_id,
                        artifact.source_url,
                        (
                            "RESTOS A PAGAR — anterior "
                            f"{summary.payments_prior_amount}; mês "
                            f"{summary.payments_period_amount}; acumulado "
                            f"{summary.payments_to_date_amount}"
                        ),
                        json.dumps(
                            {
                                "section": "RESTOS A PAGAR",
                                "period_end": summary.period_end.isoformat(),
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                        artifact.sha256,
                        PUBLIC_OBLIGATION_METHODOLOGY,
                    ),
                )
                return 1
        finally:
            connection.close()

    def record_failure(
        self,
        artifact: PublicObligationArtifact,
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
                    PUBLIC_OBLIGATION_JOB_TYPE,
                    _failure_key(artifact.sha256),
                    error_code,
                    error_detail[:1000],
                ),
            )
        finally:
            connection.close()


def _failure_key(artifact_sha256: str) -> str:
    return hashlib.sha256(
        f"{PUBLIC_OBLIGATION_JOB_TYPE}:{artifact_sha256}".encode()
    ).hexdigest()
