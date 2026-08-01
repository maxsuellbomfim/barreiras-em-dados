"""Registro transacional de página canônica, job e candidatos."""

from __future__ import annotations

from collections.abc import Callable

from barreiras_collectors.persistence.postgres import DatabaseConnection

from .processing import (
    ExtractionBatch,
    ExtractionPersistResult,
    ProcessingError,
    TextArtifact,
    candidate_payload,
    canonical_json,
)


class PostgresExtractionRepository:
    """Persiste a extração de um artefato em uma única transação idempotente."""

    def __init__(self, connection_factory: Callable[[], DatabaseConnection]) -> None:
        self.connection_factory = connection_factory

    @classmethod
    def from_dsn(cls, database_url: str) -> PostgresExtractionRepository:
        from barreiras_collectors.persistence.postgres import (
            PostgresCollectionRepository,
        )

        collection = PostgresCollectionRepository.from_dsn(database_url)
        return cls(collection.connection_factory)

    def pending_text_artifacts(self, limit: int) -> tuple[TextArtifact, ...]:
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                select
                  artifact.id::text as id,
                  artifact.sha256,
                  artifact.object_key
                from raw.raw_artifacts as artifact
                where artifact.artifact_kind = 'document'
                  and (
                    artifact.metadata ->> 'document_role' = 'txt'
                    or artifact.metadata ->> 'schema_name'
                        = 'gazette-direct-edition'
                  )
                  and not exists (
                    select 1
                    from raw.extraction_jobs as job
                    where job.raw_artifact_id = artifact.id
                      and job.job_type = 'gazette_act_candidates'
                      and job.idempotency_key = encode(
                        sha256(
                          ('gazette-acts:' || artifact.sha256 || ':' || %s)::bytea
                        ),
                        'hex'
                      )
                  )
                order by artifact.created_at
                limit %s
                """,
                (self._ruleset_version(), limit),
            )
            artifacts = []
            while True:
                row = rows.fetchone()
                if row is None:
                    break
                artifacts.append(
                    TextArtifact(
                        raw_artifact_id=str(row["id"]),
                        sha256=str(row["sha256"]),
                        object_key=str(row["object_key"]),
                    )
                )
            return tuple(artifacts)
        finally:
            connection.close()

    def persist_extraction(
        self,
        batch: ExtractionBatch,
    ) -> ExtractionPersistResult:
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '15s'")
                connection.execute("set local lock_timeout = '5s'")
                self._document_page(connection, batch)
                job_id = self._extraction_job(connection, batch)
                if job_id is None:
                    return ExtractionPersistResult(
                        job_created=False,
                        results_inserted=0,
                    )
                inserted = self._results(connection, batch, job_id)
            return ExtractionPersistResult(
                job_created=True,
                results_inserted=inserted,
            )
        finally:
            connection.close()

    @staticmethod
    def _ruleset_version() -> str:
        from .candidates import RULESET_VERSION

        return RULESET_VERSION

    def persist_extraction_failure(
        self,
        artifact,
        *,
        job_type: str,
        job_idempotency_key: str,
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
                      raw_artifact_id,
                      job_type,
                      idempotency_key,
                      status,
                      attempt_count,
                      last_error_code,
                      last_error_detail
                    )
                    values (%s::uuid, %s, %s, 'failed', 1, %s, %s)
                    on conflict (idempotency_key) do nothing
                    """,
                    (
                        artifact.raw_artifact_id,
                        job_type,
                        job_idempotency_key,
                        error_code[:64],
                        error_detail[:500],
                    ),
                )
        finally:
            connection.close()

    @staticmethod
    def _document_page(
        connection: DatabaseConnection,
        batch: ExtractionBatch,
    ) -> None:
        for page in batch.pages:
            row = connection.execute(
                """
                insert into raw.document_pages (
                  raw_artifact_id,
                  page_number,
                  parser_version,
                  extraction_method,
                  text_content,
                  text_sha256
                )
                values (%s::uuid, %s, %s, 'embedded_text', %s, %s)
                on conflict (raw_artifact_id, page_number, parser_version)
                  do nothing
                returning id::text as id
                """,
                (
                    batch.artifact.raw_artifact_id,
                    page.page_number,
                    page.parser_version,
                    page.text,
                    page.sha256,
                ),
            ).fetchone()
            if row is not None:
                continue

            existing = connection.execute(
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
            existing_sha = (
                str(existing["text_sha256"])
                if existing and existing["text_sha256"] is not None
                else None
            )
            if existing is None or existing_sha != page.sha256:
                raise ProcessingError(
                    "A página canônica existente diverge do texto derivado."
                )

    @staticmethod
    def _extraction_job(
        connection: DatabaseConnection,
        batch: ExtractionBatch,
    ) -> str | None:
        row = connection.execute(
            """
            insert into raw.extraction_jobs (
              raw_artifact_id,
              job_type,
              idempotency_key,
              status,
              attempt_count
            )
            values (%s::uuid, %s, %s, 'succeeded', 1)
            on conflict (idempotency_key) do nothing
            returning id::text as id
            """,
            (
                batch.artifact.raw_artifact_id,
                batch.job_type,
                batch.job_idempotency_key,
            ),
        ).fetchone()
        if row is None:
            return None
        return str(row["id"])

    @staticmethod
    def _results(
        connection: DatabaseConnection,
        batch: ExtractionBatch,
        job_id: str,
    ) -> int:
        inserted = 0
        for candidate in batch.candidates:
            connection.execute(
                """
                insert into raw.extraction_results (
                  extraction_job_id,
                  candidate_type,
                  extractor_version,
                  validator_version,
                  result_payload,
                  confidence,
                  validation_status
                )
                values (
                  %s::uuid, %s, %s, 'human-review-pending/1.0.0',
                  %s::jsonb, null, 'needs_review'
                )
                """,
                (
                    job_id,
                    candidate.act_type,
                    candidate.ruleset_version,
                    canonical_json(
                        candidate_payload(
                            candidate,
                            batch.canonical,
                            batch.artifact,
                        )
                    ),
                ),
            )
            inserted += 1
        return inserted
