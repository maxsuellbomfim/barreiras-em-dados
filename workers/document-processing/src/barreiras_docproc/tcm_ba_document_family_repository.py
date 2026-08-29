"""Persistência privada do inventário de famílias documentais TCM-BA."""

from __future__ import annotations

from collections.abc import Callable

from barreiras_collectors.persistence.postgres import DatabaseConnection

from .processing import ProcessingError, TextArtifact, canonical_json
from .tcm_ba_document_families import (
    EXTRACTOR_VERSION,
    JOB_TYPE,
    VALIDATOR_VERSION,
    TcmBaCatalogDocument,
    TcmBaDocumentFamilyBatch,
    TcmBaDocumentFamilyPersistResult,
    document_family_payload,
)


class TcmBaDocumentFamilyExtractionRepository:
    """Lê a linhagem oficial e grava uma classificação sem exposição pública."""

    def __init__(self, connection_factory: Callable[[], DatabaseConnection]) -> None:
        self.connection_factory = connection_factory

    @classmethod
    def from_dsn(
        cls,
        database_url: str,
    ) -> TcmBaDocumentFamilyExtractionRepository:
        from barreiras_collectors.persistence.postgres import (
            PostgresCollectionRepository,
        )

        collection = PostgresCollectionRepository.from_dsn(database_url)
        return cls(collection.connection_factory)

    def pending_documents(self, limit: int) -> tuple[TcmBaCatalogDocument, ...]:
        if not 1 <= limit <= 50:
            raise ValueError("limit deve estar entre 1 e 50.")
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                with preserved_documents as (
                  select
                    pdf.id::text as artifact_id,
                    pdf.sha256,
                    pdf.object_key,
                    record.source_record_key,
                    record.payload ->> 'category' as official_category,
                    pdf.created_at
                  from raw.raw_artifacts as pdf
                  join raw.raw_artifacts as prepare
                    on prepare.id = pdf.parent_artifact_id
                  join raw.raw_artifacts as catalog
                    on catalog.id = prepare.parent_artifact_id
                  join raw.raw_records as record
                    on record.raw_artifact_id = catalog.id
                   and record.source_record_key =
                     pdf.metadata ->> 'source_record_key'
                  where pdf.artifact_kind = 'document'
                    and pdf.metadata ->> 'schema_name' =
                      'tcm-ba-monthly-document'
                    and pdf.content_type = 'application/pdf'
                    and pdf.http_status between 200 and 299
                    and prepare.metadata ->> 'schema_name' =
                      'tcm-ba-document-download-prepare'
                    and record.record_type = 'tcm_ba_monthly_document'
                    and not exists (
                      select 1
                      from raw.extraction_jobs as job
                      where job.raw_artifact_id = pdf.id
                        and job.job_type = %s
                        and job.idempotency_key = encode(
                          sha256(
                            ('tcm-ba-document-family:' || pdf.sha256 || ':' ||
                              %s)::bytea
                          ),
                          'hex'
                        )
                        and job.status in ('succeeded', 'dead_lettered')
                    )
                  order by pdf.created_at, pdf.id
                  limit %s
                )
                select artifact_id, sha256, object_key, source_record_key,
                  official_category
                from preserved_documents
                order by created_at, artifact_id
                """,
                (JOB_TYPE, EXTRACTOR_VERSION, limit),
            ).fetchall()
            documents: list[TcmBaCatalogDocument] = []
            for row in rows:
                artifact_id = str(row["artifact_id"]).strip()
                sha256 = str(row["sha256"]).strip()
                object_key = str(row["object_key"]).strip()
                source_record_key = str(row["source_record_key"]).strip()
                category_value = row["official_category"]
                official_category = (
                    str(category_value).strip() if category_value is not None else ""
                )
                if (
                    not artifact_id
                    or len(sha256) != 64
                    or not object_key
                    or not source_record_key.startswith("tcm-ba:document:")
                ):
                    raise ProcessingError(
                        "A linhagem oficial do documento TCM-BA está incompleta."
                    )
                documents.append(
                    TcmBaCatalogDocument(
                        artifact=TextArtifact(
                            raw_artifact_id=artifact_id,
                            sha256=sha256,
                            object_key=object_key,
                        ),
                        source_record_key=source_record_key,
                        official_category=official_category,
                    )
                )
            return tuple(documents)
        finally:
            connection.close()

    def persist_document_family(
        self,
        batch: TcmBaDocumentFamilyBatch,
    ) -> TcmBaDocumentFamilyPersistResult:
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
                        batch.document.artifact.raw_artifact_id,
                        batch.job_type,
                        batch.job_idempotency_key,
                    ),
                ).fetchone()
                if job is None:
                    return TcmBaDocumentFamilyPersistResult(
                        False,
                        0,
                        batch.classification.family,
                    )

                validation_errors = (
                    ["unrecognized_official_category"]
                    if batch.classification.status == "unknown"
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
                      %s::uuid, 'tcm_ba_document_family', %s, %s,
                      %s::jsonb,
                      case when %s = 'unknown' then null else 1 end,
                      case when %s = 'unknown' then 'needs_review' else 'valid' end,
                      %s::jsonb
                    )
                    """,
                    (
                        str(job["id"]),
                        batch.extractor_version,
                        VALIDATOR_VERSION,
                        canonical_json(
                            document_family_payload(
                                batch.document,
                                batch.classification,
                            )
                        ),
                        batch.classification.status,
                        batch.classification.status,
                        canonical_json(validation_errors),
                    ),
                )
            return TcmBaDocumentFamilyPersistResult(
                True,
                1,
                batch.classification.family,
            )
        finally:
            connection.close()

    def persist_failure(
        self,
        document: TcmBaCatalogDocument,
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
                        document.artifact.raw_artifact_id,
                        JOB_TYPE,
                        idempotency_key,
                        error_code[:64],
                        error_detail[:500],
                    ),
                )
        finally:
            connection.close()
