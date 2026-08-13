"""Persistencia transacional da extracao estadual da LOA."""

from __future__ import annotations

from collections.abc import Callable

from barreiras_collectors.persistence.postgres import DatabaseConnection

from .bahia_state_loa import LOA_BARREIRAS_PARSER_VERSION
from .bahia_state_loa_processing import (
    LOA_EXTRACTION_JOB_TYPE,
    BahiaStateLoaArtifact,
    BahiaStateLoaExtractionBatch,
    BahiaStateLoaPersistResult,
    LoaProcessingError,
    amendment_payload,
    canonical_json,
)


class BahiaStateLoaExtractionRepository:
    """Mantem paginas, job e resultados sob a mesma transacao idempotente."""

    def __init__(self, connection_factory: Callable[[], DatabaseConnection]) -> None:
        self.connection_factory = connection_factory

    @classmethod
    def from_dsn(cls, database_url: str) -> BahiaStateLoaExtractionRepository:
        from barreiras_collectors.persistence.postgres import (
            PostgresCollectionRepository,
        )

        collection = PostgresCollectionRepository.from_dsn(database_url)
        return cls(collection.connection_factory)

    def pending_artifacts(self, limit: int) -> tuple[BahiaStateLoaArtifact, ...]:
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                select candidate.*
                from (
                  select distinct on (artifact.id)
                    artifact.id::text as artifact_id,
                    record.id::text as record_id,
                    artifact.sha256,
                    artifact.object_key,
                    (record.payload ->> 'fiscal_year')::integer as fiscal_year,
                    record.payload ->> 'annex_code' as annex_code,
                    record.payload ->> 'source_url' as source_url
                  from raw.raw_artifacts as artifact
                  join raw.raw_records as record
                    on record.raw_artifact_id = artifact.id
                   and record.record_type = 'bahia_state_loa_amendment_annex'
                   and record.payload ->> 'content_sha256' = artifact.sha256
                  where artifact.artifact_kind = 'document'
                    and artifact.content_type = 'application/pdf'
                    and artifact.object_key like
                      'bahia/loa-emendas-estaduais/%%'
                  and not exists (
                      select 1
                      from raw.extraction_jobs as job
                      join raw.extraction_results as result
                        on result.extraction_job_id = job.id
                      where job.raw_artifact_id = artifact.id
                        and job.job_type = %s
                        and job.status = 'succeeded'
                        and result.extractor_version = %s
                    )
                    and not exists (
                      select 1
                      from raw.extraction_jobs as job
                      where job.raw_artifact_id = artifact.id
                        and job.job_type = %s
                        and job.status = 'dead_lettered'
                    )
                  order by artifact.id, record.created_at desc
                ) as candidate
                order by candidate.fiscal_year desc
                limit %s
                """,
                (
                    LOA_EXTRACTION_JOB_TYPE,
                    LOA_BARREIRAS_PARSER_VERSION,
                    LOA_EXTRACTION_JOB_TYPE,
                    limit,
                ),
            ).fetchall()
            return tuple(
                BahiaStateLoaArtifact(
                    raw_artifact_id=str(row["artifact_id"]),
                    raw_record_id=str(row["record_id"]),
                    sha256=str(row["sha256"]),
                    object_key=str(row["object_key"]),
                    fiscal_year=int(row["fiscal_year"]),
                    annex_code=str(row["annex_code"]),
                    source_url=str(row["source_url"]),
                )
                for row in rows
            )
        finally:
            connection.close()

    def persist_extraction(
        self,
        batch: BahiaStateLoaExtractionBatch,
    ) -> BahiaStateLoaPersistResult:
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '30s'")
                connection.execute("set local lock_timeout = '5s'")
                for page in batch.pages:
                    inserted_page = connection.execute(
                        """
                        insert into raw.document_pages (
                          raw_artifact_id, page_number, parser_version,
                          extraction_method, text_content, text_sha256
                        )
                        values (%s::uuid, %s, %s, %s, %s, %s)
                        on conflict (
                          raw_artifact_id, page_number, parser_version
                        ) do nothing
                        returning id::text as id
                        """,
                        (
                            batch.artifact.raw_artifact_id,
                            page.page_number,
                            page.parser_version,
                            page.extraction_method,
                            page.text,
                            page.sha256,
                        ),
                    ).fetchone()
                    if inserted_page is not None:
                        continue
                    existing_page = connection.execute(
                        """
                        select text_sha256
                        from raw.document_pages
                        where raw_artifact_id = %s::uuid
                          and page_number = %s
                          and parser_version = %s
                        """,
                        (
                            batch.artifact.raw_artifact_id,
                            page.page_number,
                            page.parser_version,
                        ),
                    ).fetchone()
                    existing_hash = (
                        str(existing_page["text_sha256"])
                        if existing_page
                        and existing_page["text_sha256"] is not None
                        else None
                    )
                    if existing_page is None or existing_hash != page.sha256:
                        raise LoaProcessingError(
                            "A pagina existente diverge do texto derivado."
                        )

                job = connection.execute(
                    """
                    insert into raw.extraction_jobs (
                      raw_artifact_id, job_type, idempotency_key, status,
                      attempt_count, last_error_code, last_error_detail
                    )
                    values (%s::uuid, %s, %s, 'succeeded', 1, null, null)
                    on conflict (idempotency_key) do update set
                      status = 'succeeded',
                      attempt_count = raw.extraction_jobs.attempt_count + 1,
                      last_error_code = null,
                      last_error_detail = null,
                      updated_at = statement_timestamp()
                    where raw.extraction_jobs.status <> 'succeeded'
                    returning id::text as id
                    """,
                    (
                        batch.artifact.raw_artifact_id,
                        batch.job_type,
                        batch.idempotency_key,
                    ),
                ).fetchone()
                if job is None:
                    return BahiaStateLoaPersistResult(False, 0)

                inserted = 0
                for amendment in batch.amendments:
                    connection.execute(
                        """
                        insert into raw.extraction_results (
                          extraction_job_id, candidate_type,
                          extractor_version, validator_version,
                          result_payload, confidence,
                          validation_status, validation_errors
                        )
                        values (
                          %s::uuid, %s, %s, %s, %s::jsonb,
                          null, 'valid', '[]'::jsonb
                        )
                        """,
                        (
                            str(job["id"]),
                            "bahia_state_loa_authorized_amendment",
                            batch.extractor_version,
                            batch.validator_version,
                            canonical_json(
                                amendment_payload(amendment, batch.artifact)
                            ),
                        ),
                    )
                    inserted += 1
            return BahiaStateLoaPersistResult(True, inserted)
        finally:
            connection.close()

    def persist_failure(
        self,
        artifact: BahiaStateLoaArtifact,
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
                      raw_artifact_id, job_type, idempotency_key, status,
                      attempt_count, last_error_code, last_error_detail
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
                        LOA_EXTRACTION_JOB_TYPE,
                        idempotency_key,
                        error_code[:64],
                        error_detail[:500],
                    ),
                )
        finally:
            connection.close()
