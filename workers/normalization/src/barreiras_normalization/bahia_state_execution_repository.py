"""Persistencia transacional dos agregados estaduais do FIPLAN."""

from __future__ import annotations

from collections.abc import Callable

from barreiras_collectors.persistence.postgres import DatabaseConnection

from .bahia_state_execution_processing import (
    STATE_EXECUTION_JOB_TYPE,
    STATE_EXECUTION_PARSER_VERSION,
    STATE_EXECUTION_VALIDATOR_VERSION,
    StateExecutionArtifact,
    StateExecutionExtractionBatch,
    StateExecutionPersistResult,
    canonical_json,
    execution_payload,
)


class BahiaStateExecutionRepository:
    def __init__(self, connection_factory: Callable[[], DatabaseConnection]) -> None:
        self.connection_factory = connection_factory

    @classmethod
    def from_dsn(cls, database_url: str) -> BahiaStateExecutionRepository:
        from barreiras_collectors.persistence.postgres import (
            PostgresCollectionRepository,
        )

        collection = PostgresCollectionRepository.from_dsn(database_url)
        return cls(collection.connection_factory)

    def pending_artifacts(self, limit: int) -> tuple[StateExecutionArtifact, ...]:
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                select
                  artifact.id::text as artifact_id,
                  artifact.sha256,
                  artifact.object_key,
                  artifact.source_url,
                  artifact.retrieved_at::text as collected_at
                from raw.raw_artifacts as artifact
                where artifact.artifact_kind = 'archive'
                  and artifact.content_type in (
                    'application/zip', 'application/octet-stream'
                  )
                  and artifact.object_key like
                    'bahia/emendas-estaduais/archive/%%'
                  and exists (
                    select 1
                    from raw.raw_records as manifest
                    where manifest.raw_artifact_id = artifact.id
                      and manifest.record_type =
                        'bahia_state_amendment_archive_member'
                    group by manifest.raw_artifact_id
                    having count(*) = 5
                  )
                  and not exists (
                    select 1
                    from raw.extraction_jobs as job
                    join raw.extraction_results as result
                      on result.extraction_job_id = job.id
                    where job.raw_artifact_id = artifact.id
                      and job.job_type = %s
                      and job.status = 'succeeded'
                      and result.extractor_version = %s
                      and result.validator_version = %s
                  )
                  and not exists (
                    select 1
                    from raw.extraction_jobs as job
                    where job.raw_artifact_id = artifact.id
                      and job.job_type = %s
                      and job.status = 'dead_lettered'
                  )
                order by artifact.retrieved_at desc, artifact.id desc
                limit %s
                """,
                (
                    STATE_EXECUTION_JOB_TYPE,
                    STATE_EXECUTION_PARSER_VERSION,
                    STATE_EXECUTION_VALIDATOR_VERSION,
                    STATE_EXECUTION_JOB_TYPE,
                    limit,
                ),
            ).fetchall()
            return tuple(
                StateExecutionArtifact(
                    raw_artifact_id=str(row["artifact_id"]),
                    sha256=str(row["sha256"]),
                    object_key=str(row["object_key"]),
                    source_url=str(row["source_url"]),
                    collected_at=str(row["collected_at"]),
                )
                for row in rows
            )
        finally:
            connection.close()

    def persist_extraction(
        self,
        batch: StateExecutionExtractionBatch,
    ) -> StateExecutionPersistResult:
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '30s'")
                connection.execute("set local lock_timeout = '5s'")
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
                    return StateExecutionPersistResult(False, 0)

                inserted = 0
                for aggregate in batch.aggregates:
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
                            "bahia_state_execution_aggregate",
                            batch.extractor_version,
                            batch.validator_version,
                            canonical_json(
                                execution_payload(aggregate, batch.artifact)
                            ),
                        ),
                    )
                    inserted += 1
            return StateExecutionPersistResult(True, inserted)
        finally:
            connection.close()

    def persist_failure(
        self,
        artifact: StateExecutionArtifact,
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
                        STATE_EXECUTION_JOB_TYPE,
                        idempotency_key,
                        error_code[:64],
                        error_detail[:500],
                    ),
                )
        finally:
            connection.close()
