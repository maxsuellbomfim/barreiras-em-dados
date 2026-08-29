"""Persistência privada dos segmentos contratuais preservados pelo TCM-BA."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from barreiras_collectors.persistence.postgres import DatabaseConnection

from .ocr import TCM_BA_OCR_PARSER_VERSION
from .pdf_text import PDF_PARSER_VERSION
from .processing import PageInput, ProcessingError, TextArtifact, canonical_json
from .tcm_ba_contract_documents import (
    EXTRACTOR_VERSION,
    JOB_TYPE,
    VALIDATOR_VERSION,
    TcmBaContractDocumentBatch,
    TcmBaContractDocumentCoverage,
    TcmBaContractDocumentPersistResult,
    contract_document_payload,
)
from .tcm_ba_document_families import (
    EXTRACTOR_VERSION as FAMILY_EXTRACTOR_VERSION,
)


@dataclass(frozen=True)
class TcmBaContractDocumentPageSet:
    artifact: TextArtifact
    pages: tuple[PageInput, ...]


class TcmBaContractDocumentExtractionRepository:
    """Lê a família validada e grava somente candidatos privados."""

    def __init__(self, connection_factory: Callable[[], DatabaseConnection]) -> None:
        self.connection_factory = connection_factory

    @classmethod
    def from_dsn(
        cls,
        database_url: str,
    ) -> TcmBaContractDocumentExtractionRepository:
        from barreiras_collectors.persistence.postgres import (
            PostgresCollectionRepository,
        )

        collection = PostgresCollectionRepository.from_dsn(database_url)
        return cls(collection.connection_factory)

    def pending_page_sets(
        self,
        limit: int,
    ) -> tuple[TcmBaContractDocumentPageSet, ...]:
        if not 1 <= limit <= 50:
            raise ValueError("limit deve estar entre 1 e 50.")
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                with contract_family as (
                  select distinct job.raw_artifact_id
                  from raw.extraction_jobs as job
                  join raw.extraction_results as result
                    on result.extraction_job_id = job.id
                  where result.candidate_type = 'tcm_ba_document_family'
                    and result.extractor_version = %s
                    and result.validation_status = 'valid'
                    and result.result_payload ->> 'family' =
                      'contracts_and_amendments'
                    and job.status = 'succeeded'
                ),
                tcm_artifacts as (
                  select artifact.id, artifact.sha256, artifact.object_key,
                    artifact.created_at
                  from raw.raw_artifacts as artifact
                  join contract_family as family
                    on family.raw_artifact_id = artifact.id
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
                          ('tcm-ba-contract-segments:' || artifact.sha256 || ':' ||
                            %s)::bytea
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
                    FAMILY_EXTRACTOR_VERSION,
                    TCM_BA_OCR_PARSER_VERSION,
                    PDF_PARSER_VERSION,
                    JOB_TYPE,
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
                TcmBaContractDocumentPageSet(artifact, tuple(pages))
                for artifact, pages in grouped.values()
            )
        finally:
            connection.close()

    def contract_document_coverage(self) -> TcmBaContractDocumentCoverage:
        connection = self.connection_factory()
        try:
            row = connection.execute(
                """
                with eligible as (
                  select distinct family_job.raw_artifact_id, artifact.sha256
                  from raw.extraction_jobs as family_job
                  join raw.extraction_results as family_result
                    on family_result.extraction_job_id = family_job.id
                  join raw.raw_artifacts as artifact
                    on artifact.id = family_job.raw_artifact_id
                  where family_result.candidate_type =
                      'tcm_ba_document_family'
                    and family_result.extractor_version = %s
                    and family_result.validation_status = 'valid'
                    and family_result.result_payload ->> 'family' =
                      'contracts_and_amendments'
                    and family_job.status = 'succeeded'
                ),
                current_jobs as (
                  select job.id, job.raw_artifact_id, job.status
                  from raw.extraction_jobs as job
                  join eligible
                    on eligible.raw_artifact_id = job.raw_artifact_id
                  where job.job_type = %s
                    and job.idempotency_key = encode(
                      sha256(
                        ('tcm-ba-contract-segments:' || eligible.sha256 || ':' ||
                          %s)::bytea
                      ),
                      'hex'
                    )
                ),
                current_results as (
                  select job.raw_artifact_id,
                    eligible.sha256 as source_artifact_sha256,
                    result.validation_status, result.result_payload
                  from current_jobs as job
                  join eligible
                    on eligible.raw_artifact_id = job.raw_artifact_id
                  join raw.extraction_results as result
                    on result.extraction_job_id = job.id
                  where result.candidate_type =
                      'tcm_ba_contract_document_segment'
                    and result.extractor_version = %s
                ),
                result_counts as (
                  select raw_artifact_id,
                    count(*) as result_count,
                    count(distinct result_payload ->> 'segment_ordinal')
                      as distinct_ordinals,
                    count(*) filter (
                      where result_payload ->> 'document_kind' <> 'unknown'
                    ) as identified_count,
                    count(*) filter (
                      where result_payload ->> 'document_kind' = 'unknown'
                    ) as unknown_count,
                    count(*) filter (
                      where validation_status <> 'needs_review'
                         or result_payload ->> 'schema_name' is null
                         or result_payload ->> 'schema_name'
                            <> 'tcm-ba-contract-document-segment'
                         or result_payload ->> 'document_kind' is null
                         or result_payload ->> 'segment_ordinal' is null
                         or result_payload ->> 'segment_ordinal'
                            !~ '^[1-9][0-9]*$'
                         or result_payload ->> 'segment_text_sha256' is null
                         or result_payload ->> 'segment_text_sha256'
                            !~ '^[0-9a-f]{64}$'
                         or result_payload ->> 'source_artifact_sha256' is null
                         or result_payload ->> 'source_artifact_sha256'
                            <> source_artifact_sha256
                    ) as invalid_count
                  from current_results
                  group by raw_artifact_id
                )
                select
                  count(distinct eligible.raw_artifact_id)::integer
                    as eligible_artifacts,
                  count(*) filter (
                    where counts.result_count > 0
                  )::integer as processed_artifacts,
                  coalesce(sum(counts.identified_count), 0)::integer
                    as identified_segments,
                  coalesce(sum(counts.unknown_count), 0)::integer
                    as unknown_segments,
                  count(*) filter (
                    where counts.raw_artifact_id is null
                  )::integer as missing_artifacts,
                  count(*) filter (
                    where counts.identified_count = 0
                      and counts.unknown_count > 0
                  )::integer as unknown_only_artifacts,
                  coalesce(sum(
                    greatest(
                      counts.result_count - counts.distinct_ordinals,
                      0
                    )
                  ), 0)::integer as duplicate_results,
                  coalesce(sum(counts.invalid_count), 0)::integer
                    as invalid_results,
                  (
                    select count(*)::integer
                    from current_jobs as job
                    where job.status in (
                      'failed', 'retry_scheduled', 'dead_lettered'
                    )
                  ) as open_failures
                from eligible
                left join result_counts as counts
                  on counts.raw_artifact_id = eligible.raw_artifact_id
                """,
                (
                    FAMILY_EXTRACTOR_VERSION,
                    JOB_TYPE,
                    EXTRACTOR_VERSION,
                    EXTRACTOR_VERSION,
                ),
            ).fetchone()
            if row is None:
                raise ProcessingError(
                    "A cobertura dos segmentos contratuais não foi retornada."
                )
            try:
                coverage = TcmBaContractDocumentCoverage(
                    eligible_artifacts=int(row["eligible_artifacts"]),
                    processed_artifacts=int(row["processed_artifacts"]),
                    identified_segments=int(row["identified_segments"]),
                    unknown_segments=int(row["unknown_segments"]),
                    missing_artifacts=int(row["missing_artifacts"]),
                    unknown_only_artifacts=int(row["unknown_only_artifacts"]),
                    duplicate_results=int(row["duplicate_results"]),
                    invalid_results=int(row["invalid_results"]),
                    open_failures=int(row["open_failures"]),
                )
            except (KeyError, TypeError, ValueError) as error:
                raise ProcessingError(
                    "A cobertura dos segmentos contratuais está incompleta."
                ) from error
            if any(value < 0 for value in coverage.__dict__.values()):
                raise ProcessingError(
                    "A cobertura dos segmentos contratuais possui contador inválido."
                )
            return coverage
        finally:
            connection.close()

    def persist_contract_document_segments(
        self,
        batch: TcmBaContractDocumentBatch,
    ) -> TcmBaContractDocumentPersistResult:
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
                    return TcmBaContractDocumentPersistResult(False, 0, 0, 0)

                inserted = 0
                identified = 0
                unknown = 0
                for segment in batch.segments:
                    validation_errors = (
                        ["unrecognized_contract_heading"]
                        if segment.document_kind == "unknown"
                        else []
                    )
                    connection.execute(
                        """
                        insert into raw.extraction_results (
                          extraction_job_id, candidate_type,
                          extractor_version, validator_version,
                          result_payload, confidence,
                          validation_status, validation_errors
                        )
                        values (
                          %s::uuid, 'tcm_ba_contract_document_segment', %s,
                          %s, %s::jsonb, null, 'needs_review', %s::jsonb
                        )
                        """,
                        (
                            str(job["id"]),
                            batch.extractor_version,
                            VALIDATOR_VERSION,
                            canonical_json(
                                contract_document_payload(
                                    segment,
                                    batch.artifact,
                                )
                            ),
                            canonical_json(validation_errors),
                        ),
                    )
                    inserted += 1
                    if segment.document_kind == "unknown":
                        unknown += 1
                    else:
                        identified += 1
            return TcmBaContractDocumentPersistResult(
                True,
                inserted,
                identified,
                unknown,
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
