"""Persistência privada dos campos contratuais preservados pelo TCM-BA."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from barreiras_collectors.persistence.postgres import DatabaseConnection

from .ocr import TCM_BA_OCR_PARSER_VERSION
from .pdf_text import PDF_PARSER_VERSION
from .processing import PageInput, ProcessingError, TextArtifact, canonical_json
from .tcm_ba_contract_documents import (
    EXTRACTOR_VERSION as SEGMENT_EXTRACTOR_VERSION,
)
from .tcm_ba_contract_fields import (
    EXTRACTOR_VERSION,
    JOB_TYPE,
    VALIDATOR_VERSION,
    TcmBaContractFieldBatch,
    TcmBaContractFieldCoverage,
    TcmBaContractFieldPersistResult,
    contract_field_candidate_payload,
)


@dataclass(frozen=True)
class TcmBaContractFieldPageSet:
    artifact: TextArtifact
    pages: tuple[PageInput, ...]


class TcmBaContractFieldExtractionRepository:
    """Lê segmentos e páginas verificados e grava candidatos privados."""

    def __init__(self, connection_factory: Callable[[], DatabaseConnection]) -> None:
        self.connection_factory = connection_factory

    @classmethod
    def from_dsn(
        cls,
        database_url: str,
    ) -> TcmBaContractFieldExtractionRepository:
        from barreiras_collectors.persistence.postgres import (
            PostgresCollectionRepository,
        )

        collection = PostgresCollectionRepository.from_dsn(database_url)
        return cls(collection.connection_factory)

    def pending_page_sets(
        self,
        limit: int,
    ) -> tuple[TcmBaContractFieldPageSet, ...]:
        if not 1 <= limit <= 50:
            raise ValueError("limit deve estar entre 1 e 50.")
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                with segmented_artifacts as (
                  select distinct job.raw_artifact_id
                  from raw.extraction_jobs as job
                  join raw.extraction_results as segment
                    on segment.extraction_job_id = job.id
                  where segment.candidate_type =
                      'tcm_ba_contract_document_segment'
                    and segment.extractor_version = %s
                    and segment.validation_status = 'needs_review'
                    and segment.result_payload ->> 'document_kind' <> 'unknown'
                    and segment.result_payload ->> 'segment_ordinal' is not null
                    and segment.result_payload ->> 'segment_text_sha256' is not null
                    and job.status = 'succeeded'
                ),
                tcm_artifacts as (
                  select artifact.id, artifact.sha256, artifact.object_key,
                    artifact.created_at
                  from raw.raw_artifacts as artifact
                  join segmented_artifacts as segmented
                    on segmented.raw_artifact_id = artifact.id
                  where artifact.artifact_kind = 'document'
                    and artifact.metadata ->> 'schema_name' =
                      'tcm-ba-monthly-document'
                    and artifact.content_type = 'application/pdf'
                    and artifact.http_status between 200 and 299
                ),
                resolved_pages as (
                  select
                    base.raw_artifact_id,
                    base.page_number,
                    case when base.text_content is not null
                      then base.parser_version else ocr.parser_version end
                      as parser_version,
                    case when base.text_content is not null
                      then base.extraction_method else ocr.extraction_method end
                      as extraction_method,
                    coalesce(base.text_content, ocr.text_content)
                      as text_content,
                    coalesce(base.text_sha256, ocr.text_sha256) as text_sha256
                  from raw.document_pages as base
                  join tcm_artifacts as artifact
                    on artifact.id = base.raw_artifact_id
                  left join lateral (
                    select supplemental.parser_version,
                      supplemental.extraction_method,
                      supplemental.text_content,
                      supplemental.text_sha256
                    from raw.document_pages as supplemental
                    where supplemental.raw_artifact_id = base.raw_artifact_id
                      and supplemental.page_number = base.page_number
                      and supplemental.parser_version = %s
                      and supplemental.text_content is not null
                    order by supplemental.created_at desc
                    limit 1
                  ) as ocr on true
                  where base.parser_version = %s
                ),
                ready_artifacts as (
                  select page.raw_artifact_id
                  from resolved_pages as page
                  group by page.raw_artifact_id
                  having count(*) > 0
                    and bool_and(page.text_content is not null)
                    and bool_and(page.text_sha256 is not null)
                ),
                candidates as (
                  select artifact.*
                  from tcm_artifacts as artifact
                  join ready_artifacts as ready
                    on ready.raw_artifact_id = artifact.id
                  where not exists (
                    select 1
                    from raw.extraction_jobs as job
                    where job.raw_artifact_id = artifact.id
                      and job.job_type = %s
                      and job.idempotency_key = encode(
                        sha256(
                          ('tcm-ba-contract-fields:' || artifact.sha256 || ':' ||
                            %s || ':' || %s)::bytea
                        ),
                        'hex'
                      )
                      and job.status in ('succeeded', 'dead_lettered')
                  )
                  order by artifact.created_at, artifact.id
                  limit %s
                )
                select candidate.id::text as artifact_id,
                  candidate.sha256, candidate.object_key,
                  page.page_number, page.parser_version,
                  page.extraction_method, page.text_content, page.text_sha256
                from candidates as candidate
                join resolved_pages as page
                  on page.raw_artifact_id = candidate.id
                order by candidate.created_at, candidate.id, page.page_number
                """,
                (
                    SEGMENT_EXTRACTOR_VERSION,
                    TCM_BA_OCR_PARSER_VERSION,
                    PDF_PARSER_VERSION,
                    JOB_TYPE,
                    SEGMENT_EXTRACTOR_VERSION,
                    EXTRACTOR_VERSION,
                    limit,
                ),
            ).fetchall()
            grouped: dict[str, tuple[TextArtifact, list[PageInput]]] = {}
            for row in rows:
                if row["text_sha256"] is None:
                    raise ProcessingError(
                        "A página contratual TCM-BA não possui hash de texto."
                    )
                artifact_id = str(row["artifact_id"])
                if artifact_id not in grouped:
                    grouped[artifact_id] = (
                        TextArtifact(
                            raw_artifact_id=artifact_id,
                            sha256=str(row["sha256"]),
                            object_key=str(row["object_key"]),
                        ),
                        [],
                    )
                grouped[artifact_id][1].append(
                    PageInput(
                        page_number=int(row["page_number"]),
                        parser_version=str(row["parser_version"]),
                        extraction_method=str(row["extraction_method"]),
                        text=str(row["text_content"]),
                        sha256=str(row["text_sha256"]),
                    )
                )
            return tuple(
                TcmBaContractFieldPageSet(artifact, tuple(pages))
                for artifact, pages in grouped.values()
            )
        finally:
            connection.close()

    def contract_field_coverage(self) -> TcmBaContractFieldCoverage:
        connection = self.connection_factory()
        try:
            row = connection.execute(
                """
                with eligible_segments as (
                  select segment_job.raw_artifact_id,
                    artifact.sha256 as artifact_sha256,
                    (segment.result_payload ->> 'segment_ordinal')::integer
                      as segment_ordinal,
                    segment.result_payload ->> 'segment_text_sha256'
                      as segment_text_sha256
                  from raw.extraction_jobs as segment_job
                  join raw.extraction_results as segment
                    on segment.extraction_job_id = segment_job.id
                  join raw.raw_artifacts as artifact
                    on artifact.id = segment_job.raw_artifact_id
                  where segment.candidate_type =
                      'tcm_ba_contract_document_segment'
                    and segment.extractor_version = %s
                    and segment.validation_status = 'needs_review'
                    and segment.result_payload ->> 'document_kind' <> 'unknown'
                    and segment.result_payload ->> 'segment_ordinal' is not null
                    and segment.result_payload ->> 'segment_text_sha256'
                      ~ '^[0-9a-f]{64}$'
                    and segment_job.status = 'succeeded'
                ),
                current_jobs as (
                  select job.id, job.raw_artifact_id, job.status
                  from raw.extraction_jobs as job
                  join raw.raw_artifacts as artifact
                    on artifact.id = job.raw_artifact_id
                  where job.job_type = %s
                    and job.idempotency_key = encode(
                      sha256(
                        ('tcm-ba-contract-fields:' || artifact.sha256 || ':' ||
                          %s || ':' || %s)::bytea
                      ),
                      'hex'
                    )
                ),
                field_results as (
                  select job.raw_artifact_id, result.id,
                    result.validation_status, result.result_payload
                  from current_jobs as job
                  join raw.extraction_results as result
                    on result.extraction_job_id = job.id
                  where result.candidate_type =
                      'tcm_ba_contract_field_candidate'
                    and result.extractor_version = %s
                ),
                valid_results as (
                  select field.raw_artifact_id, field.id,
                    (field.result_payload ->> 'source_segment_ordinal')::integer
                      as segment_ordinal,
                    field.result_payload ->> 'source_segment_text_sha256'
                      as segment_text_sha256,
                    field.result_payload
                  from field_results as field
                  join raw.raw_artifacts as artifact
                    on artifact.id = field.raw_artifact_id
                  where field.validation_status = 'needs_review'
                    and field.result_payload ->> 'schema_name' =
                      'tcm-ba-contract-field-candidate'
                    and field.result_payload ->> 'schema_version' = '1.0.0'
                    and field.result_payload ->> 'source_artifact_sha256' =
                      artifact.sha256
                    and field.result_payload ->> 'source_segment_extractor_version'
                      = %s
                    and field.result_payload ->> 'source_segment_ordinal'
                      ~ '^[1-9][0-9]*$'
                    and field.result_payload ->> 'source_segment_text_sha256'
                      ~ '^[0-9a-f]{64}$'
                    and jsonb_typeof(
                      field.result_payload -> 'source_anchors'
                    ) = 'object'
                    and field.result_payload ->> 'candidate_status' in (
                      'fields_observed', 'no_fields_observed'
                    )
                ),
                matched as (
                  select eligible.raw_artifact_id, eligible.segment_ordinal,
                    valid.id, valid.result_payload
                  from eligible_segments as eligible
                  join valid_results as valid
                    on valid.raw_artifact_id = eligible.raw_artifact_id
                    and valid.segment_ordinal = eligible.segment_ordinal
                    and valid.segment_text_sha256 =
                      eligible.segment_text_sha256
                ),
                metrics as (
                  select
                    (select count(distinct raw_artifact_id)
                      from eligible_segments)::integer as eligible_artifacts,
                    (select count(distinct raw_artifact_id)
                      from matched)::integer as processed_artifacts,
                    (select count(*) from eligible_segments)::integer
                      as eligible_segments,
                    (select count(distinct (raw_artifact_id, segment_ordinal))
                      from matched)::integer as processed_segments,
                    coalesce((
                      select count(*)
                      from matched,
                      lateral jsonb_object_keys(
                        matched.result_payload -> 'source_anchors'
                      ) as source_anchor(field_name)
                    ), 0)::integer as observed_fields,
                    (select count(*) from matched where result_payload ->>
                      'candidate_status' = 'no_fields_observed')::integer
                      as no_fields_observed,
                    ((select count(*) from eligible_segments) -
                      (select count(distinct (
                        raw_artifact_id, segment_ordinal
                      )) from matched))::integer as missing_segments,
                    ((select count(*) from valid_results) -
                      (select count(distinct (
                        raw_artifact_id, segment_ordinal
                      )) from valid_results))::integer as duplicate_results,
                    ((select count(*) from field_results) -
                      (select count(*) from valid_results))::integer
                      as invalid_results,
                    (select count(*) from current_jobs where status in (
                      'failed', 'retry_scheduled', 'dead_lettered'
                    ))::integer as open_failures
                )
                select * from metrics
                """,
                (
                    SEGMENT_EXTRACTOR_VERSION,
                    JOB_TYPE,
                    SEGMENT_EXTRACTOR_VERSION,
                    EXTRACTOR_VERSION,
                    EXTRACTOR_VERSION,
                    SEGMENT_EXTRACTOR_VERSION,
                ),
            ).fetchone()
            if row is None:
                raise ProcessingError(
                    "A cobertura dos campos contratuais não foi retornada."
                )
            try:
                coverage = TcmBaContractFieldCoverage(
                    eligible_artifacts=int(row["eligible_artifacts"]),
                    processed_artifacts=int(row["processed_artifacts"]),
                    eligible_segments=int(row["eligible_segments"]),
                    processed_segments=int(row["processed_segments"]),
                    observed_fields=int(row["observed_fields"]),
                    no_fields_observed=int(row["no_fields_observed"]),
                    missing_segments=int(row["missing_segments"]),
                    duplicate_results=int(row["duplicate_results"]),
                    invalid_results=int(row["invalid_results"]),
                    open_failures=int(row["open_failures"]),
                )
            except (KeyError, TypeError, ValueError) as error:
                raise ProcessingError(
                    "A cobertura dos campos contratuais está incompleta."
                ) from error
            if any(value < 0 for value in coverage.__dict__.values()):
                raise ProcessingError(
                    "A cobertura dos campos contratuais possui contador inválido."
                )
            return coverage
        finally:
            connection.close()

    def persist_contract_field_candidates(
        self,
        batch: TcmBaContractFieldBatch,
    ) -> TcmBaContractFieldPersistResult:
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '15s'")
                connection.execute("set local lock_timeout = '5s'")
                job = connection.execute(
                    """
                    insert into raw.extraction_jobs (
                      raw_artifact_id, job_type, idempotency_key,
                      status, attempt_count
                    )
                    values (%s::uuid, %s, %s, 'succeeded', 1)
                    on conflict (idempotency_key) do update set
                      status = 'succeeded',
                      attempt_count = raw.extraction_jobs.attempt_count + 1,
                      last_error_code = null,
                      last_error_detail = null,
                      updated_at = statement_timestamp()
                    where raw.extraction_jobs.status not in (
                      'succeeded', 'dead_lettered'
                    )
                    returning id::text as id
                    """,
                    (
                        batch.artifact.raw_artifact_id,
                        batch.job_type,
                        batch.job_idempotency_key,
                    ),
                ).fetchone()
                if job is None:
                    return TcmBaContractFieldPersistResult(False, 0, 0, 0)

                inserted = 0
                fields_observed = 0
                empty_candidates = 0
                for candidate in batch.candidates:
                    connection.execute(
                        """
                        insert into raw.extraction_results (
                          extraction_job_id, candidate_type,
                          extractor_version, validator_version,
                          result_payload, confidence,
                          validation_status, validation_errors
                        )
                        values (
                          %s::uuid, 'tcm_ba_contract_field_candidate', %s,
                          %s, %s::jsonb, null, 'needs_review', '[]'::jsonb
                        )
                        """,
                        (
                            str(job["id"]),
                            batch.extractor_version,
                            VALIDATOR_VERSION,
                            canonical_json(
                                contract_field_candidate_payload(
                                    candidate,
                                    batch.artifact,
                                )
                            ),
                        ),
                    )
                    inserted += 1
                    fields_observed += len(candidate.source_anchors)
                    empty_candidates += int(
                        candidate.candidate_status == "no_fields_observed"
                    )
            return TcmBaContractFieldPersistResult(
                True,
                inserted,
                fields_observed,
                empty_candidates,
            )
        finally:
            connection.close()

    def persist_failure(
        self,
        artifact: TextArtifact,
        *,
        idempotency_key: str,
        error_code: str,
        error_detail: str,
    ) -> None:
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '15s'")
                connection.execute("set local lock_timeout = '5s'")
                connection.execute(
                    """
                    insert into raw.extraction_jobs (
                      raw_artifact_id, job_type, idempotency_key,
                      status, attempt_count, last_error_code, last_error_detail
                    )
                    values (%s::uuid, %s, %s, 'failed', 1, %s, %s)
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
                    where raw.extraction_jobs.status <> 'succeeded'
                    """,
                    (
                        artifact.raw_artifact_id,
                        JOB_TYPE,
                        idempotency_key,
                        error_code[:64],
                        error_detail[:500],
                    ),
                )
        finally:
            connection.close()
