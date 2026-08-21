"""Persistência transacional do recorte de Transferências Especiais da Bahia."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from barreiras_collectors.persistence.postgres import DatabaseConnection

from .bahia_special_transfer_processing import (
    SPECIAL_TRANSFER_JOB_TYPE,
    SPECIAL_TRANSFER_VALIDATOR_VERSION,
    SpecialTransferArtifact,
    SpecialTransferExtractionBatch,
    SpecialTransferPersistResult,
    canonical_json,
)
from .bahia_special_transfers import (
    SPECIAL_TRANSFER_PARSER_VERSION,
    special_transfer_payload,
)


class BahiaSpecialTransferRepository:
    def __init__(self, connection_factory: Callable[[], DatabaseConnection]) -> None:
        self.connection_factory = connection_factory

    @classmethod
    def from_dsn(cls, database_url: str) -> BahiaSpecialTransferRepository:
        from barreiras_collectors.persistence.postgres import (
            PostgresCollectionRepository,
        )

        collection = PostgresCollectionRepository.from_dsn(database_url)
        return cls(collection.connection_factory)

    def pending_artifacts(self, limit: int) -> tuple[SpecialTransferArtifact, ...]:
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
                    'bahia/transferencias-especiais/archive/%%'
                  and exists (
                    select 1
                    from raw.raw_records as manifest
                    where manifest.raw_artifact_id = artifact.id
                      and manifest.record_type =
                        'bahia_special_transfer_archive_member'
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
                    SPECIAL_TRANSFER_JOB_TYPE,
                    SPECIAL_TRANSFER_PARSER_VERSION,
                    SPECIAL_TRANSFER_VALIDATOR_VERSION,
                    SPECIAL_TRANSFER_JOB_TYPE,
                    limit,
                ),
            ).fetchall()
            return tuple(
                SpecialTransferArtifact(
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
        batch: SpecialTransferExtractionBatch,
    ) -> SpecialTransferPersistResult:
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
                    return SpecialTransferPersistResult(False, 0)

                summary_payload = canonical_json(
                    {
                        "schema_name": "bahia-special-transfer-scope-summary",
                        "schema_version": "1.0.0",
                        "candidate_count": len(batch.candidates),
                        "territorial_scope": "payment_object_literal_barreiras",
                        "public_projection": ("blocked_pending_author_reconciliation"),
                        "source_url": batch.artifact.source_url,
                        "source_artifact_sha256": batch.artifact.sha256,
                        "source_collected_at": batch.artifact.collected_at,
                        "parser_version": batch.extractor_version,
                    }
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
                      %s::uuid, %s, %s, %s, %s::jsonb,
                      null, 'valid', '[]'::jsonb
                    )
                    """,
                    (
                        str(job["id"]),
                        "bahia_special_transfer_scope_summary",
                        batch.extractor_version,
                        batch.validator_version,
                        summary_payload,
                    ),
                )

                coverage_start_year = 2021
                coverage_end_year = datetime.fromisoformat(
                    batch.artifact.collected_at.replace("Z", "+00:00")
                ).year
                public_annual_coverage = tuple(
                    row
                    for row in batch.annual_coverage
                    if coverage_start_year
                    <= row.fiscal_year
                    <= coverage_end_year
                )
                coverage_payload = canonical_json(
                    {
                        "schema_name": (
                            "bahia-special-transfer-annual-coverage"
                        ),
                        "schema_version": "1.0.0",
                        "coverage_start_year": coverage_start_year,
                        "coverage_end_year": coverage_end_year,
                        "years": [
                            {
                                "fiscal_year": row.fiscal_year,
                                "source_payment_count": row.source_payment_count,
                                "territorial_payment_count": (
                                    row.territorial_payment_count
                                ),
                            }
                            for row in public_annual_coverage
                        ],
                        "territorial_scope": (
                            "payment_object_literal_barreiras"
                        ),
                        "source_url": batch.artifact.source_url,
                        "source_artifact_sha256": batch.artifact.sha256,
                        "source_collected_at": batch.artifact.collected_at,
                        "parser_version": batch.extractor_version,
                    }
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
                      %s::uuid, %s, %s, %s, %s::jsonb,
                      null, 'valid', '[]'::jsonb
                    )
                    """,
                    (
                        str(job["id"]),
                        "bahia_special_transfer_annual_coverage",
                        batch.extractor_version,
                        batch.validator_version,
                        coverage_payload,
                    ),
                )

                if batch.candidates:
                    payloads = canonical_json(
                        [
                            special_transfer_payload(
                                candidate,
                                source_url=batch.artifact.source_url,
                                source_artifact_sha256=batch.artifact.sha256,
                                source_collected_at=batch.artifact.collected_at,
                            )
                            for candidate in batch.candidates
                        ]
                    )
                    connection.execute(
                        """
                        insert into raw.extraction_results (
                          extraction_job_id, candidate_type,
                          extractor_version, validator_version,
                          result_payload, confidence,
                          validation_status, validation_errors
                        )
                        select
                          %s::uuid, %s, %s, %s, payload.value,
                          null, 'valid', '[]'::jsonb
                        from jsonb_array_elements(%s::jsonb) as payload(value)
                        """,
                        (
                            str(job["id"]),
                            "bahia_special_transfer_payment_candidate",
                            batch.extractor_version,
                            batch.validator_version,
                            payloads,
                        ),
                    )
            return SpecialTransferPersistResult(True, len(batch.candidates))
        finally:
            connection.close()

    def persist_failure(
        self,
        artifact: SpecialTransferArtifact,
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
                        SPECIAL_TRANSFER_JOB_TYPE,
                        idempotency_key,
                        error_code[:64],
                        error_detail[:500],
                    ),
                )
        finally:
            connection.close()
