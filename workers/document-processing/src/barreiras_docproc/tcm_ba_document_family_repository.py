"""Persistência privada do inventário de famílias documentais TCM-BA."""

from __future__ import annotations

import re
from collections.abc import Callable

from barreiras_collectors.persistence.postgres import DatabaseConnection

from .processing import ProcessingError, TextArtifact, canonical_json
from .tcm_ba_document_families import (
    EXTRACTOR_VERSION,
    JOB_TYPE,
    VALIDATOR_VERSION,
    TcmBaCatalogDocument,
    TcmBaDocumentFamilyBatch,
    TcmBaDocumentFamilyCoverage,
    TcmBaDocumentFamilyPersistResult,
    TcmBaDocumentLineage,
    classify_document_family,
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

    def document_lineage_by_sha256(
        self,
        artifact_sha256: str,
    ) -> tuple[TcmBaDocumentLineage, ...]:
        """Localiza cada observação oficial de um PDF preservado pelo hash."""
        if not re.fullmatch(r"[0-9a-f]{64}", artifact_sha256):
            raise ValueError("artifact_sha256 deve ser um sha256 hexadecimal.")
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                select
                  pdf.id::text as artifact_id,
                  pdf.sha256,
                  pdf.object_key,
                  record.source_record_key,
                  record.payload ->> 'competence' as competence,
                  record.payload ->> 'category' as official_category,
                  record.payload ->> 'name' as document_name
                from raw.raw_artifacts as pdf
                join raw.raw_artifacts as prepare
                  on prepare.id = pdf.parent_artifact_id
                join raw.raw_artifacts as catalog
                  on catalog.id = prepare.parent_artifact_id
                join raw.raw_records as record
                  on record.raw_artifact_id = catalog.id
                 and record.source_record_key =
                   pdf.metadata ->> 'source_record_key'
                where pdf.sha256 = %s
                  and pdf.artifact_kind = 'document'
                  and pdf.metadata ->> 'schema_name' =
                    'tcm-ba-monthly-document'
                  and pdf.content_type = 'application/pdf'
                  and pdf.http_status between 200 and 299
                  and prepare.metadata ->> 'schema_name' =
                    'tcm-ba-document-download-prepare'
                  and record.record_type = 'tcm_ba_monthly_document'
                order by competence, record.source_record_key, pdf.id
                """,
                (artifact_sha256,),
            ).fetchall()
            lineages: list[TcmBaDocumentLineage] = []
            for row in rows:
                category = str(row.get("official_category") or "").strip()
                classification = classify_document_family(category)
                lineages.append(
                    TcmBaDocumentLineage(
                        artifact_id=str(row["artifact_id"]).strip(),
                        artifact_sha256=str(row["sha256"]).strip(),
                        object_key=str(row["object_key"]).strip(),
                        source_record_key=str(row["source_record_key"]).strip(),
                        competence=str(row.get("competence") or "").strip(),
                        official_category=category,
                        official_category_code=(
                            classification.official_category_code
                        ),
                        family=classification.family,
                        document_name=str(row.get("document_name") or "").strip(),
                    )
                )
            return tuple(lineages)
        finally:
            connection.close()

    def document_family_coverage(self) -> TcmBaDocumentFamilyCoverage:
        connection = self.connection_factory()
        try:
            row = connection.execute(
                """
                with preserved as (
                  select pdf.id, pdf.sha256
                  from raw.raw_artifacts as pdf
                  where pdf.artifact_kind = 'document'
                    and pdf.metadata ->> 'schema_name' =
                      'tcm-ba-monthly-document'
                    and pdf.content_type = 'application/pdf'
                    and pdf.http_status between 200 and 299
                ),
                current_jobs as (
                  select job.id, job.raw_artifact_id, job.status
                  from raw.extraction_jobs as job
                  join preserved as pdf on pdf.id = job.raw_artifact_id
                  where job.job_type = %s
                    and job.idempotency_key = encode(
                      sha256(
                        ('tcm-ba-document-family:' || pdf.sha256 || ':' ||
                          %s)::bytea
                      ),
                      'hex'
                    )
                ),
                current_results as (
                  select job.raw_artifact_id, job.status as job_status,
                    result.validation_status,
                    result.result_payload
                  from current_jobs as job
                  join raw.extraction_results as result
                    on result.extraction_job_id = job.id
                  where result.candidate_type = 'tcm_ba_document_family'
                    and result.extractor_version = %s
                ),
                result_counts as (
                  select raw_artifact_id, count(*) as result_count,
                    count(*) filter (
                      where validation_status = 'valid'
                        and result_payload ->> 'family' <> 'unknown'
                    ) as classified_count,
                    count(*) filter (
                      where validation_status = 'needs_review'
                        and result_payload ->> 'family' = 'unknown'
                    ) as unknown_count,
                    count(*) filter (
                      where result_payload ->> 'schema_name'
                          <> 'tcm-ba-document-family'
                         or result_payload ->> 'family' is null
                         or validation_status = 'invalid'
                         or (
                           result_payload ->> 'family' = 'unknown'
                           and validation_status <> 'needs_review'
                         )
                         or (
                           result_payload ->> 'family' <> 'unknown'
                           and validation_status <> 'valid'
                         )
                    ) as invalid_count
                  from current_results
                  group by raw_artifact_id
                )
                select
                  count(distinct pdf.id)::integer as preserved_documents,
                  coalesce(sum(counts.classified_count), 0)::integer
                    as classified_documents,
                  coalesce(sum(counts.unknown_count), 0)::integer
                    as unknown_documents,
                  count(*) filter (where counts.raw_artifact_id is null)::integer
                    as missing_documents,
                  coalesce(sum(greatest(counts.result_count - 1, 0)), 0)::integer
                    as duplicate_results,
                  coalesce(sum(counts.invalid_count), 0)::integer
                    as invalid_results,
                  (
                    select count(*)::integer
                    from current_jobs as job
                    where job.status in (
                      'failed', 'retry_scheduled', 'dead_lettered'
                    )
                  ) as open_failures
                from preserved as pdf
                left join result_counts as counts
                  on counts.raw_artifact_id = pdf.id
                """,
                (JOB_TYPE, EXTRACTOR_VERSION, EXTRACTOR_VERSION),
            ).fetchone()
            if row is None:
                raise ProcessingError(
                    "A cobertura das famílias TCM-BA não foi retornada."
                )
            try:
                coverage = TcmBaDocumentFamilyCoverage(
                    preserved_documents=int(row["preserved_documents"]),
                    classified_documents=int(row["classified_documents"]),
                    unknown_documents=int(row["unknown_documents"]),
                    missing_documents=int(row["missing_documents"]),
                    duplicate_results=int(row["duplicate_results"]),
                    invalid_results=int(row["invalid_results"]),
                    open_failures=int(row["open_failures"]),
                )
            except (KeyError, TypeError, ValueError) as error:
                raise ProcessingError(
                    "A cobertura das famílias TCM-BA está incompleta."
                ) from error
            if any(value < 0 for value in coverage.__dict__.values()):
                raise ProcessingError(
                    "A cobertura das famílias TCM-BA possui contador inválido."
                )
            return coverage
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
