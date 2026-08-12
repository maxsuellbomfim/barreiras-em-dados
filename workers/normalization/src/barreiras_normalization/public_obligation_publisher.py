"""Publicador idempotente de pagamentos de restos a pagar em balancetes."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Protocol

from .public_obligation_pdf import (
    PublicObligationProgressionError,
    PublicObligationStructuralError,
    RestosAPagarSummary,
    parse_restos_a_pagar_summary,
    validate_restos_a_pagar_progression,
)
from .revenue_publisher import ArtifactMismatchError, default_pdf_text_extractor

PUBLIC_OBLIGATION_JOB_TYPE = "public_obligation_balancete_publication/1.5.5"
PUBLIC_OBLIGATION_METHODOLOGY = "public-obligations-balancete/1.5.5"


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


@dataclass(frozen=True)
class PublicObligationExtractionProvenance:
    extraction_method: str
    extraction_parser_version: str
    page_numbers: tuple[int, ...] = ()
    rotation_degrees: int | None = None


@dataclass(frozen=True)
class PublicObligationExtraction:
    summary: RestosAPagarSummary
    provenance: PublicObligationExtractionProvenance


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
        provenance: PublicObligationExtractionProvenance,
    ) -> int: ...

    def previous_month_to_date(
        self,
        artifact: PublicObligationArtifact,
    ) -> Decimal | None: ...

    def record_progression_conflict(
        self,
        artifact: PublicObligationArtifact,
        summary: RestosAPagarSummary,
        provenance: PublicObligationExtractionProvenance,
        *,
        previous_month_to_date: Decimal,
    ) -> int: ...

    def record_failure(
        self,
        artifact: PublicObligationArtifact,
        *,
        error_code: str,
        error_detail: str,
    ) -> None: ...

    def record_section_absent(
        self,
        artifact: PublicObligationArtifact,
        *,
        detail: str,
    ) -> None: ...

    def record_section_incomplete(
        self,
        artifact: PublicObligationArtifact,
        *,
        detail: str,
    ) -> None: ...


class PublicObligationPublisher:
    """Confere o artefato e publica somente a linha cujo total fecha."""

    def __init__(
        self,
        *,
        object_reader: ObjectReader,
        repository: PublicObligationPublicationRepository,
        text_extractor: Callable[[bytes], str] = default_pdf_text_extractor,
        ocr_extractor: Callable[..., PublicObligationExtraction] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.object_reader = object_reader
        self.repository = repository
        self.text_extractor = text_extractor
        self.ocr_extractor = ocr_extractor
        self.logger = logger or logging.getLogger(__name__)

    def publish(
        self,
        artifact: PublicObligationArtifact,
    ) -> PublicObligationPublishResult:
        extraction = self.validate(artifact)
        summary = extraction.summary
        previous_month_to_date = self.repository.previous_month_to_date(artifact)
        try:
            validate_restos_a_pagar_progression(
                summary,
                previous_month_to_date=previous_month_to_date,
            )
        except PublicObligationProgressionError:
            if previous_month_to_date is None:
                raise
            inserted = self.repository.record_progression_conflict(
                artifact,
                summary,
                extraction.provenance,
                previous_month_to_date=previous_month_to_date,
            )
            self.logger.info(
                "public_obligation_progression_conflict",
                extra={
                    "artifact_id": artifact.id,
                    "period_end": summary.period_end.isoformat(),
                    "previous_month_to_date": str(previous_month_to_date),
                    "reported_prior_amount": str(summary.payments_prior_amount),
                    "difference_amount": str(
                        abs(previous_month_to_date - summary.payments_prior_amount)
                    ),
                    "inserted": inserted,
                    "methodology_version": PUBLIC_OBLIGATION_METHODOLOGY,
                },
            )
            return PublicObligationPublishResult(
                artifact_id=artifact.id,
                status="source_conflict" if inserted else "already_source_conflict",
            )
        inserted = self.repository.persist_validated_summary(
            artifact,
            summary,
            extraction.provenance,
        )
        self.logger.info(
            "public_obligation_summary_published",
            extra={
                "artifact_id": artifact.id,
                "period_end": summary.period_end.isoformat(),
                "inserted": inserted,
                "methodology_version": PUBLIC_OBLIGATION_METHODOLOGY,
                "extraction_method": extraction.provenance.extraction_method,
            },
        )
        return PublicObligationPublishResult(
            artifact_id=artifact.id,
            status="published" if inserted else "already_published",
        )

    def validate(
        self,
        artifact: PublicObligationArtifact,
    ) -> PublicObligationExtraction:
        """Valida bytes e valores sem persistir, para ensaios auditáveis."""
        raw_body = self.object_reader.read(artifact.object_key)
        actual_hash = hashlib.sha256(raw_body).hexdigest()
        if actual_hash != artifact.sha256 or len(raw_body) != artifact.byte_size:
            raise ArtifactMismatchError(
                f"Artefato {artifact.id} diverge do hash ou tamanho catalogado."
            )
        return self._extract(raw_body, artifact)

    def _extract(
        self,
        raw_body: bytes,
        artifact: PublicObligationArtifact,
    ) -> PublicObligationExtraction:
        try:
            embedded_text = self.text_extractor(raw_body)
        except ValueError:
            return self._extract_with_ocr(raw_body, artifact)
        try:
            summary = parse_restos_a_pagar_summary(
                embedded_text,
                fiscal_year=artifact.fiscal_year,
                reference_month=artifact.reference_month,
            )
        except PublicObligationStructuralError:
            return self._extract_with_ocr(raw_body, artifact)

        from barreiras_docproc.pdf_text import PDF_PARSER_VERSION

        return PublicObligationExtraction(
            summary=summary,
            provenance=PublicObligationExtractionProvenance(
                extraction_method="embedded_text",
                extraction_parser_version=PDF_PARSER_VERSION,
            ),
        )

    def _extract_with_ocr(
        self,
        raw_body: bytes,
        artifact: PublicObligationArtifact,
    ) -> PublicObligationExtraction:
        if self.ocr_extractor is None:
            raise PublicObligationStructuralError(
                "Texto embutido incompleto e fallback OCR indisponível."
            )
        return self.ocr_extractor(
            raw_body,
            fiscal_year=artifact.fiscal_year,
            reference_month=artifact.reference_month,
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
                    and btrim(coalesce(record.payload ->> 'titulo', ''))
                      ~* '^balancete[[:space:]]'
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
                        and obligation.validation_state in (
                          'validated', 'reconciled', 'conflict'
                        )
                    )
                    and not exists (
                      select 1
                      from raw.extraction_jobs as terminal_job
                      join raw.extraction_results as result
                        on result.extraction_job_id = terminal_job.id
                      where terminal_job.raw_artifact_id = document.id
                        and terminal_job.status = 'succeeded'
                        and result.validation_status = 'valid'
                        and result.extractor_version = %s
                        and result.candidate_type in (
                          'public_obligation_section_absent',
                          'public_obligation_section_incomplete'
                        )
                    )
                    and not exists (
                      select 1
                      from raw.extraction_jobs as job
                      where job.raw_artifact_id = document.id
                        and job.job_type = %s
                        and job.status in ('failed', 'succeeded', 'dead_lettered')
                    )
                  order by document.id, record.created_at desc, record.id desc
                )
                select id, sha256, object_key, byte_size, parent_record_id,
                  source_url, fiscal_year, reference_month
                from candidates
                order by fiscal_year asc, reference_month asc, created_at asc, id
                limit %s
                """,
                (
                    fiscal_year_from,
                    fiscal_year_to,
                    PUBLIC_OBLIGATION_METHODOLOGY,
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

    def record_section_incomplete(
        self,
        artifact: PublicObligationArtifact,
        *,
        detail: str,
    ) -> None:
        """Registra fonte incompleta como resultado terminal, nunca como zero."""
        connection = self.connection_factory()
        candidate_type = "public_obligation_section_incomplete"
        try:
            connection.execute(
                """
                with terminal_job as (
                  insert into raw.extraction_jobs (
                    raw_artifact_id, job_type, idempotency_key, status,
                    attempt_count
                  ) values (
                    %s::uuid, %s, %s, 'succeeded', 1
                  )
                  on conflict (idempotency_key) do update set
                    status = 'succeeded',
                    attempt_count = raw.extraction_jobs.attempt_count + 1,
                    last_error_code = null,
                    last_error_detail = null,
                    updated_at = statement_timestamp()
                  returning id
                )
                insert into raw.extraction_results (
                  extraction_job_id, candidate_type, extractor_version,
                  validator_version, result_payload, confidence,
                  validation_status, validation_errors
                )
                select
                  terminal_job.id, %s, %s, %s,
                  %s::jsonb, 1.0, 'valid', '[]'::jsonb
                from terminal_job
                where not exists (
                  select 1
                  from raw.extraction_results as existing
                  where existing.extraction_job_id = terminal_job.id
                    and existing.candidate_type = %s
                    and existing.extractor_version = %s
                )
                """,
                (
                    artifact.id,
                    PUBLIC_OBLIGATION_JOB_TYPE,
                    _failure_key(artifact.sha256),
                    candidate_type,
                    PUBLIC_OBLIGATION_METHODOLOGY,
                    PUBLIC_OBLIGATION_METHODOLOGY,
                    json.dumps(
                        {
                            "classification": "incomplete_in_source_document",
                            "detail": detail[:500],
                            "fiscal_year": artifact.fiscal_year,
                            "reference_month": artifact.reference_month,
                            "source_url": artifact.source_url,
                            "content_sha256": artifact.sha256,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    candidate_type,
                    PUBLIC_OBLIGATION_METHODOLOGY,
                ),
            )
        finally:
            connection.close()

    def persist_validated_summary(
        self,
        artifact: PublicObligationArtifact,
        summary: RestosAPagarSummary,
        provenance: PublicObligationExtractionProvenance,
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
                                "extraction_method": provenance.extraction_method,
                                "extraction_parser_version": (
                                    provenance.extraction_parser_version
                                ),
                                "page_numbers": list(provenance.page_numbers),
                                "rotation_degrees": provenance.rotation_degrees,
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

    def record_progression_conflict(
        self,
        artifact: PublicObligationArtifact,
        summary: RestosAPagarSummary,
        provenance: PublicObligationExtractionProvenance,
        *,
        previous_month_to_date: Decimal,
    ) -> int:
        """Preserva os dois valores oficiais e bloqueia a publicação numérica."""
        previous_period_end = summary.period_start - timedelta(days=1)
        difference_amount = abs(
            previous_month_to_date - summary.payments_prior_amount
        )
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '20s'")
                connection.execute("set local lock_timeout = '5s'")
                previous = connection.execute(
                    """
                    select
                      obligation.id::text,
                      obligation.payments_to_date_amount,
                      evidence_item.id::text as evidence_item_id
                    from finance.public_obligations as obligation
                    join evidence.evidence_items as evidence_item
                      on evidence_item.target_type = 'finance.public_obligations'
                     and evidence_item.target_id = obligation.id
                     and evidence_item.is_primary
                    where obligation.fiscal_year = %s
                      and obligation.period_end = %s::date
                      and obligation.obligation_type = 'restos_a_pagar_total'
                      and obligation.validation_state in ('validated', 'reconciled')
                    order by obligation.version desc,
                      obligation.validated_at desc,
                      evidence_item.created_at desc,
                      obligation.id desc,
                      evidence_item.id desc
                    limit 1
                    """,
                    (summary.fiscal_year, previous_period_end.isoformat()),
                ).fetchone()
                if previous is None:
                    raise RuntimeError(
                        "evidência do mês anterior não encontrada para o conflito"
                    )
                persisted_previous = Decimal(
                    str(previous["payments_to_date_amount"])
                )
                if persisted_previous != previous_month_to_date:
                    raise RuntimeError(
                        "valor anterior mudou durante a reconciliação"
                    )
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
                      %s::date, %s::date, %s, %s, %s, 'reported', 'conflict',
                      %s, null
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
                current_evidence = connection.execute(
                    """
                    insert into evidence.evidence_items (
                      target_type, target_id, raw_artifact_id, raw_record_id,
                      evidence_kind, source_url, excerpt, locator,
                      content_sha256, parser_version, is_primary
                    ) values (
                      'finance.public_obligations', %s::uuid, %s::uuid, %s::uuid,
                      'document', %s, %s, %s::jsonb, %s, %s, true
                    )
                    returning id::text
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
                                "extraction_method": provenance.extraction_method,
                                "extraction_parser_version": (
                                    provenance.extraction_parser_version
                                ),
                                "page_numbers": list(provenance.page_numbers),
                                "rotation_degrees": provenance.rotation_degrees,
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                        artifact.sha256,
                        PUBLIC_OBLIGATION_METHODOLOGY,
                    ),
                ).fetchone()
                connection.execute(
                    """
                    insert into evidence.source_conflicts (
                      target_type, target_id, field_name,
                      first_evidence_item_id, second_evidence_item_id,
                      first_value, second_value, status
                    ) values (
                      'finance.public_obligations', %s::uuid,
                      'payments_prior_amount', %s::uuid, %s::uuid,
                      %s::jsonb, %s::jsonb, 'open'
                    )
                    on conflict (
                      target_type, target_id, field_name,
                      first_evidence_item_id, second_evidence_item_id
                    ) do nothing
                    """,
                    (
                        inserted["id"],
                        previous["evidence_item_id"],
                        current_evidence["id"],
                        json.dumps(
                            {
                                "period_end": previous_period_end.isoformat(),
                                "payments_to_date_amount": str(
                                    previous_month_to_date
                                ),
                            },
                            separators=(",", ":"),
                        ),
                        json.dumps(
                            {
                                "period_start": summary.period_start.isoformat(),
                                "payments_prior_amount": str(
                                    summary.payments_prior_amount
                                ),
                                "difference_amount": str(difference_amount),
                            },
                            separators=(",", ":"),
                        ),
                    ),
                )
                candidate_type = "public_obligation_progression_conflict"
                connection.execute(
                    """
                    with terminal_job as (
                      insert into raw.extraction_jobs (
                        raw_artifact_id, job_type, idempotency_key, status,
                        attempt_count
                      ) values (
                        %s::uuid, %s, %s, 'succeeded', 1
                      )
                      on conflict (idempotency_key) do update set
                        status = 'succeeded',
                        attempt_count = raw.extraction_jobs.attempt_count + 1,
                        last_error_code = null,
                        last_error_detail = null,
                        updated_at = statement_timestamp()
                      returning id
                    )
                    insert into raw.extraction_results (
                      extraction_job_id, candidate_type, extractor_version,
                      validator_version, result_payload, confidence,
                      validation_status, validation_errors
                    )
                    select
                      terminal_job.id, %s, %s, %s, %s::jsonb,
                      1.0, 'valid', '[]'::jsonb
                    from terminal_job
                    where not exists (
                      select 1
                      from raw.extraction_results as existing
                      where existing.extraction_job_id = terminal_job.id
                        and existing.candidate_type = %s
                        and existing.extractor_version = %s
                    )
                    """,
                    (
                        artifact.id,
                        PUBLIC_OBLIGATION_JOB_TYPE,
                        _failure_key(artifact.sha256),
                        candidate_type,
                        PUBLIC_OBLIGATION_METHODOLOGY,
                        PUBLIC_OBLIGATION_METHODOLOGY,
                        json.dumps(
                            {
                                "classification": (
                                    "official_month_progression_conflict"
                                ),
                                "fiscal_year": artifact.fiscal_year,
                                "reference_month": artifact.reference_month,
                                "previous_period_amount": str(
                                    previous_month_to_date
                                ),
                                "reported_prior_amount": str(
                                    summary.payments_prior_amount
                                ),
                                "difference_amount": str(difference_amount),
                                "source_url": artifact.source_url,
                                "content_sha256": artifact.sha256,
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                        candidate_type,
                        PUBLIC_OBLIGATION_METHODOLOGY,
                    ),
                )
                return 1
        finally:
            connection.close()

    def previous_month_to_date(
        self,
        artifact: PublicObligationArtifact,
    ) -> Decimal | None:
        if artifact.reference_month == 1:
            return None
        previous_period_end = date(
            artifact.fiscal_year,
            artifact.reference_month,
            1,
        ) - timedelta(days=1)
        connection = self.connection_factory()
        try:
            row = connection.execute(
                """
                select payments_to_date_amount
                from finance.public_obligations
                where fiscal_year = %s
                  and period_end = %s::date
                  and obligation_type = 'restos_a_pagar_total'
                  and validation_state in ('validated', 'reconciled')
                order by version desc, validated_at desc, id desc
                limit 1
                """,
                (artifact.fiscal_year, previous_period_end.isoformat()),
            ).fetchone()
            if row is None:
                return None
            return Decimal(str(row["payments_to_date_amount"]))
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

    def record_section_absent(
        self,
        artifact: PublicObligationArtifact,
        *,
        detail: str,
    ) -> None:
        """Registra ausência comprovada como resultado terminal, não como zero."""
        connection = self.connection_factory()
        try:
            connection.execute(
                """
                with terminal_job as (
                  insert into raw.extraction_jobs (
                    raw_artifact_id, job_type, idempotency_key, status,
                    attempt_count
                  ) values (
                    %s::uuid, %s, %s, 'succeeded', 1
                  )
                  on conflict (idempotency_key) do update set
                    status = 'succeeded',
                    attempt_count = raw.extraction_jobs.attempt_count + 1,
                    last_error_code = null,
                    last_error_detail = null,
                    updated_at = statement_timestamp()
                  returning id
                )
                insert into raw.extraction_results (
                  extraction_job_id, candidate_type, extractor_version,
                  validator_version, result_payload, confidence,
                  validation_status, validation_errors
                )
                select
                  terminal_job.id, 'public_obligation_section_absent', %s, %s,
                  %s::jsonb, 1.0, 'valid', '[]'::jsonb
                from terminal_job
                where not exists (
                  select 1
                  from raw.extraction_results as existing
                  where existing.extraction_job_id = terminal_job.id
                    and existing.candidate_type
                      = 'public_obligation_section_absent'
                    and existing.extractor_version = %s
                )
                """,
                (
                    artifact.id,
                    PUBLIC_OBLIGATION_JOB_TYPE,
                    _failure_key(artifact.sha256),
                    PUBLIC_OBLIGATION_METHODOLOGY,
                    PUBLIC_OBLIGATION_METHODOLOGY,
                    json.dumps(
                        {
                            "classification": "absent_in_source_document",
                            "detail": detail[:500],
                            "fiscal_year": artifact.fiscal_year,
                            "reference_month": artifact.reference_month,
                            "source_url": artifact.source_url,
                            "content_sha256": artifact.sha256,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    PUBLIC_OBLIGATION_METHODOLOGY,
                ),
            )
        finally:
            connection.close()


def _failure_key(artifact_sha256: str) -> str:
    return hashlib.sha256(
        f"{PUBLIC_OBLIGATION_JOB_TYPE}:{artifact_sha256}".encode()
    ).hexdigest()
