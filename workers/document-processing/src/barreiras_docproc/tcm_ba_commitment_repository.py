"""Persistência dos candidatos privados de notas de empenho do TCM-BA."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from barreiras_collectors.persistence.postgres import DatabaseConnection

from .ocr import TCM_BA_OCR_PARSER_VERSION
from .pdf_layout import PDF_LAYOUT_VERSION
from .pdf_text import PDF_PARSER_VERSION
from .processing import PageInput, ProcessingError, TextArtifact, canonical_json
from .tcm_ba_commitment_amount_diagnostic import TcmBaAmountLayoutTarget
from .tcm_ba_commitment_budget_diagnostic import TcmBaBudgetLayoutTarget
from .tcm_ba_commitment_creditor_diagnostic import TcmBaCreditorLayoutTarget
from .tcm_ba_commitment_date_diagnostic import TcmBaIssueDateLayoutTarget
from .tcm_ba_commitments import (
    EXTRACTOR_VERSION,
    JOB_TYPE,
    SCHEMA_VERSION,
    TcmBaCommitmentBatch,
    TcmBaCommitmentCoverage,
    TcmBaCommitmentFieldBreakdown,
    TcmBaCommitmentMissingFieldGroup,
    TcmBaCommitmentPersistResult,
    commitment_candidate_payload,
)


@dataclass(frozen=True)
class TcmBaCommitmentPageSet:
    artifact: TextArtifact
    pages: tuple[PageInput, ...]


class TcmBaCommitmentExtractionRepository:
    """Lê páginas verificadas e grava apenas candidatos para revisão."""

    def __init__(self, connection_factory: Callable[[], DatabaseConnection]) -> None:
        self.connection_factory = connection_factory

    @classmethod
    def from_dsn(
        cls,
        database_url: str,
    ) -> TcmBaCommitmentExtractionRepository:
        from barreiras_collectors.persistence.postgres import (
            PostgresCollectionRepository,
        )

        collection = PostgresCollectionRepository.from_dsn(database_url)
        return cls(collection.connection_factory)

    def pending_page_sets(
        self,
        limit: int,
    ) -> tuple[TcmBaCommitmentPageSet, ...]:
        if not 1 <= limit <= 50:
            raise ValueError("limit deve estar entre 1 e 50.")
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                with tcm_artifacts as (
                  select artifact.id, artifact.sha256, artifact.object_key,
                    artifact.created_at
                  from raw.raw_artifacts as artifact
                  where artifact.artifact_kind = 'document'
                    and artifact.metadata ->> 'schema_name'
                        = 'tcm-ba-monthly-document'
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
                          ('tcm-ba-commitments:' || artifact.sha256 || ':' ||
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
                        "A página TCM-BA resolvida não possui hash de texto."
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
                TcmBaCommitmentPageSet(artifact, tuple(pages))
                for artifact, pages in grouped.values()
            )
        finally:
            connection.close()

    def budget_layout_targets(
        self,
        *,
        limit: int = 500,
    ) -> tuple[TcmBaBudgetLayoutTarget, ...]:
        if not 1 <= limit <= 500:
            raise ValueError("limit deve estar entre 1 e 500.")
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                with tcm_artifacts as (
                  select artifact.id, artifact.sha256, artifact.object_key
                  from raw.raw_artifacts as artifact
                  where artifact.artifact_kind = 'document'
                    and artifact.metadata ->> 'schema_name'
                        = 'tcm-ba-monthly-document'
                    and artifact.content_type = 'application/pdf'
                    and artifact.http_status between 200 and 299
                ),
                current_jobs as (
                  select job.id, job.raw_artifact_id
                  from raw.extraction_jobs as job
                  join tcm_artifacts as artifact
                    on artifact.id = job.raw_artifact_id
                  where job.job_type = %s
                    and job.status = 'succeeded'
                    and job.idempotency_key = encode(
                      sha256(
                        ('tcm-ba-commitments:' || artifact.sha256 || ':' ||
                          %s)::bytea
                      ),
                      'hex'
                    )
                ),
                current_results as (
                  select job.raw_artifact_id,
                    (result.result_payload ->> 'source_page_number')::integer
                      as page_number
                  from current_jobs as job
                  join raw.extraction_results as result
                    on result.extraction_job_id = job.id
                  where result.candidate_type = 'tcm_ba_commitment_note'
                    and result.extractor_version = %s
                    and result.validation_status = 'needs_review'
                    and result.result_payload ->> 'schema_version' = %s
                    and result.result_payload -> 'missing_fields'
                        ? 'budget_allocation'
                ),
                page_counts as (
                  select raw_artifact_id, page_number,
                    count(*)::integer as candidate_count
                  from current_results
                  group by raw_artifact_id, page_number
                )
                select artifact.id::text as artifact_id,
                  artifact.sha256, artifact.object_key,
                  jsonb_agg(
                    jsonb_build_array(page.page_number, page.candidate_count)
                    order by page.page_number
                  ) as candidate_page_counts,
                  count(*) over()::integer as total_artifacts,
                  'commitment_budget_layout_targets' as report_marker
                from page_counts as page
                join tcm_artifacts as artifact
                  on artifact.id = page.raw_artifact_id
                group by artifact.id, artifact.sha256, artifact.object_key
                order by artifact.sha256
                limit %s
                """,
                (
                    JOB_TYPE,
                    EXTRACTOR_VERSION,
                    EXTRACTOR_VERSION,
                    SCHEMA_VERSION,
                    limit,
                ),
            ).fetchall()
        finally:
            connection.close()
        return self._budget_targets_from_rows(rows, limit=limit)

    @staticmethod
    def _budget_targets_from_rows(
        rows,
        *,
        limit: int,
    ) -> tuple[TcmBaBudgetLayoutTarget, ...]:
        targets: list[TcmBaBudgetLayoutTarget] = []
        total_artifacts: int | None = None
        for row in rows:
            try:
                row_total = int(row["total_artifacts"])
                raw_counts = row["candidate_page_counts"]
                artifact_id = str(row["artifact_id"])
                sha256 = str(row["sha256"])
                object_key = str(row["object_key"])
            except (KeyError, TypeError, ValueError) as error:
                raise ProcessingError(
                    "O alvo espacial de dotação está incompleto."
                ) from error
            if total_artifacts is None:
                total_artifacts = row_total
            elif total_artifacts != row_total:
                raise ProcessingError(
                    "A contagem total dos alvos de dotação divergiu."
                )
            if isinstance(raw_counts, str):
                try:
                    raw_counts = json.loads(raw_counts)
                except json.JSONDecodeError as error:
                    raise ProcessingError(
                        "As páginas dos alvos de dotação não são JSON válido."
                    ) from error
            if not isinstance(raw_counts, list):
                raise ProcessingError(
                    "As páginas dos alvos de dotação não formam uma lista."
                )
            page_counts: list[tuple[int, int]] = []
            for raw_pair in raw_counts:
                if not isinstance(raw_pair, list) or len(raw_pair) != 2:
                    raise ProcessingError(
                        "Uma contagem de página da dotação é inválida."
                    )
                try:
                    page_number, candidate_count = map(int, raw_pair)
                except (TypeError, ValueError) as error:
                    raise ProcessingError(
                        "Uma contagem de página da dotação não é numérica."
                    ) from error
                if page_number < 1 or candidate_count < 1:
                    raise ProcessingError(
                        "Uma contagem de página da dotação está fora do limite."
                    )
                page_counts.append((page_number, candidate_count))
            if (
                len({page for page, _count in page_counts}) != len(page_counts)
                or page_counts != sorted(page_counts)
                or len(sha256) != 64
                or any(character not in "0123456789abcdef" for character in sha256)
                or not object_key
            ):
                raise ProcessingError("O alvo espacial de dotação é inválido.")
            targets.append(
                TcmBaBudgetLayoutTarget(
                    artifact=TextArtifact(artifact_id, sha256, object_key),
                    candidate_page_counts=tuple(page_counts),
                )
            )
        if total_artifacts is not None and total_artifacts > limit:
            raise ProcessingError(
                "O benchmark de dotações excedeu o limite de artefatos."
            )
        return tuple(targets)

    def creditor_layout_targets(
        self,
        *,
        limit: int = 500,
    ) -> tuple[TcmBaCreditorLayoutTarget, ...]:
        if not 1 <= limit <= 500:
            raise ValueError("limit deve estar entre 1 e 500.")
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                with tcm_artifacts as (
                  select artifact.id, artifact.sha256, artifact.object_key
                  from raw.raw_artifacts as artifact
                  where artifact.artifact_kind = 'document'
                    and artifact.metadata ->> 'schema_name'
                        = 'tcm-ba-monthly-document'
                    and artifact.content_type = 'application/pdf'
                    and artifact.http_status between 200 and 299
                ),
                current_jobs as (
                  select job.id, job.raw_artifact_id
                  from raw.extraction_jobs as job
                  join tcm_artifacts as artifact
                    on artifact.id = job.raw_artifact_id
                  where job.job_type = %s
                    and job.status = 'succeeded'
                    and job.idempotency_key = encode(
                      sha256(
                        ('tcm-ba-commitments:' || artifact.sha256 || ':' ||
                          %s)::bytea
                      ),
                      'hex'
                    )
                ),
                current_results as (
                  select job.raw_artifact_id,
                    (result.result_payload ->> 'source_page_number')::integer
                      as page_number
                  from current_jobs as job
                  join raw.extraction_results as result
                    on result.extraction_job_id = job.id
                  where result.candidate_type = 'tcm_ba_commitment_note'
                    and result.extractor_version = %s
                    and result.validation_status = 'needs_review'
                    and result.result_payload ->> 'schema_version' = %s
                    and result.result_payload -> 'missing_fields'
                        ? 'creditor_name'
                ),
                page_counts as (
                  select raw_artifact_id, page_number,
                    count(*)::integer as candidate_count
                  from current_results
                  group by raw_artifact_id, page_number
                )
                select artifact.id::text as artifact_id,
                  artifact.sha256, artifact.object_key,
                  jsonb_agg(
                    jsonb_build_array(page.page_number, page.candidate_count)
                    order by page.page_number
                  ) as candidate_page_counts,
                  count(*) over()::integer as total_artifacts,
                  'commitment_creditor_layout_targets' as report_marker
                from page_counts as page
                join tcm_artifacts as artifact
                  on artifact.id = page.raw_artifact_id
                group by artifact.id, artifact.sha256, artifact.object_key
                order by artifact.sha256
                limit %s
                """,
                (
                    JOB_TYPE,
                    EXTRACTOR_VERSION,
                    EXTRACTOR_VERSION,
                    SCHEMA_VERSION,
                    limit,
                ),
            ).fetchall()
        finally:
            connection.close()
        targets: list[TcmBaCreditorLayoutTarget] = []
        total_artifacts: int | None = None
        for row in rows:
            try:
                row_total = int(row["total_artifacts"])
                raw_counts = row["candidate_page_counts"]
                artifact_id = str(row["artifact_id"])
                sha256 = str(row["sha256"])
                object_key = str(row["object_key"])
            except (KeyError, TypeError, ValueError) as error:
                raise ProcessingError(
                    "O alvo espacial de credor está incompleto."
                ) from error
            if total_artifacts is None:
                total_artifacts = row_total
            elif total_artifacts != row_total:
                raise ProcessingError("A contagem total dos alvos de credor divergiu.")
            if isinstance(raw_counts, str):
                try:
                    raw_counts = json.loads(raw_counts)
                except json.JSONDecodeError as error:
                    raise ProcessingError(
                        "As páginas dos alvos de credor não são JSON válido."
                    ) from error
            if not isinstance(raw_counts, list):
                raise ProcessingError(
                    "As páginas dos alvos de credor não formam uma lista."
                )
            page_counts: list[tuple[int, int]] = []
            for raw_pair in raw_counts:
                if not isinstance(raw_pair, list) or len(raw_pair) != 2:
                    raise ProcessingError(
                        "Uma contagem de página do credor é inválida."
                    )
                try:
                    page_number, candidate_count = map(int, raw_pair)
                except (TypeError, ValueError) as error:
                    raise ProcessingError(
                        "Uma contagem de página do credor não é numérica."
                    ) from error
                if page_number < 1 or candidate_count < 1:
                    raise ProcessingError(
                        "Uma contagem de página do credor está fora do limite."
                    )
                page_counts.append((page_number, candidate_count))
            if (
                len({page for page, _count in page_counts}) != len(page_counts)
                or page_counts != sorted(page_counts)
                or len(sha256) != 64
                or any(character not in "0123456789abcdef" for character in sha256)
                or not object_key
            ):
                raise ProcessingError("O alvo espacial de credor é inválido.")
            targets.append(
                TcmBaCreditorLayoutTarget(
                    artifact=TextArtifact(artifact_id, sha256, object_key),
                    candidate_page_counts=tuple(page_counts),
                )
            )
        if total_artifacts is not None and total_artifacts > limit:
            raise ProcessingError(
                "O benchmark de credores excedeu o limite de artefatos."
            )
        return tuple(targets)

    def amount_layout_targets(
        self,
        *,
        limit: int = 500,
    ) -> tuple[TcmBaAmountLayoutTarget, ...]:
        if not 1 <= limit <= 500:
            raise ValueError("limit deve estar entre 1 e 500.")
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                with tcm_artifacts as (
                  select artifact.id, artifact.sha256, artifact.object_key
                  from raw.raw_artifacts as artifact
                  where artifact.artifact_kind = 'document'
                    and artifact.metadata ->> 'schema_name'
                        = 'tcm-ba-monthly-document'
                    and artifact.content_type = 'application/pdf'
                    and artifact.http_status between 200 and 299
                ),
                current_jobs as (
                  select job.id, job.raw_artifact_id
                  from raw.extraction_jobs as job
                  join tcm_artifacts as artifact
                    on artifact.id = job.raw_artifact_id
                  where job.job_type = %s
                    and job.status = 'succeeded'
                    and job.idempotency_key = encode(
                      sha256(
                        ('tcm-ba-commitments:' || artifact.sha256 || ':' ||
                          %s)::bytea
                      ),
                      'hex'
                    )
                ),
                current_results as (
                  select job.raw_artifact_id,
                    (result.result_payload ->> 'source_page_number')::integer
                      as page_number
                  from current_jobs as job
                  join raw.extraction_results as result
                    on result.extraction_job_id = job.id
                  where result.candidate_type = 'tcm_ba_commitment_note'
                    and result.extractor_version = %s
                    and result.validation_status = 'needs_review'
                    and result.result_payload ->> 'schema_version' = %s
                    and result.result_payload -> 'missing_fields' ? 'amount_text'
                ),
                page_counts as (
                  select raw_artifact_id, page_number,
                    count(*)::integer as candidate_count
                  from current_results
                  group by raw_artifact_id, page_number
                )
                select artifact.id::text as artifact_id,
                  artifact.sha256, artifact.object_key,
                  jsonb_agg(
                    jsonb_build_array(page.page_number, page.candidate_count)
                    order by page.page_number
                  ) as candidate_page_counts,
                  count(*) over()::integer as total_artifacts,
                  'commitment_amount_layout_targets' as report_marker
                from page_counts as page
                join tcm_artifacts as artifact
                  on artifact.id = page.raw_artifact_id
                group by artifact.id, artifact.sha256, artifact.object_key
                order by artifact.sha256
                limit %s
                """,
                (
                    JOB_TYPE,
                    EXTRACTOR_VERSION,
                    EXTRACTOR_VERSION,
                    SCHEMA_VERSION,
                    limit,
                ),
            ).fetchall()
        finally:
            connection.close()
        budget_targets = self._budget_targets_from_rows(rows, limit=limit)
        return tuple(
            TcmBaAmountLayoutTarget(
                artifact=target.artifact,
                candidate_page_counts=target.candidate_page_counts,
            )
            for target in budget_targets
        )

    def issue_date_layout_targets(
        self,
        *,
        limit: int = 500,
    ) -> tuple[TcmBaIssueDateLayoutTarget, ...]:
        if not 1 <= limit <= 500:
            raise ValueError("limit deve estar entre 1 e 500.")
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                with tcm_artifacts as (
                  select artifact.id, artifact.sha256, artifact.object_key
                  from raw.raw_artifacts as artifact
                  where artifact.artifact_kind = 'document'
                    and artifact.metadata ->> 'schema_name'
                        = 'tcm-ba-monthly-document'
                    and artifact.content_type = 'application/pdf'
                    and artifact.http_status between 200 and 299
                ),
                current_jobs as (
                  select job.id, job.raw_artifact_id
                  from raw.extraction_jobs as job
                  join tcm_artifacts as artifact
                    on artifact.id = job.raw_artifact_id
                  where job.job_type = %s
                    and job.status = 'succeeded'
                    and job.idempotency_key = encode(
                      sha256(
                        ('tcm-ba-commitments:' || artifact.sha256 || ':' ||
                          %s)::bytea
                      ),
                      'hex'
                    )
                ),
                current_results as (
                  select job.raw_artifact_id,
                    (result.result_payload ->> 'source_page_number')::integer
                      as page_number
                  from current_jobs as job
                  join raw.extraction_results as result
                    on result.extraction_job_id = job.id
                  where result.candidate_type = 'tcm_ba_commitment_note'
                    and result.extractor_version = %s
                    and result.validation_status = 'needs_review'
                    and result.result_payload ->> 'schema_version' = %s
                    and result.result_payload -> 'missing_fields'
                        ? 'issue_date'
                ),
                page_counts as (
                  select raw_artifact_id, page_number,
                    count(*)::integer as candidate_count
                  from current_results
                  group by raw_artifact_id, page_number
                )
                select artifact.id::text as artifact_id,
                  artifact.sha256, artifact.object_key,
                  jsonb_agg(
                    jsonb_build_array(page.page_number, page.candidate_count)
                    order by page.page_number
                  ) as candidate_page_counts,
                  count(*) over()::integer as total_artifacts,
                  'commitment_issue_date_layout_targets' as report_marker
                from page_counts as page
                join tcm_artifacts as artifact
                  on artifact.id = page.raw_artifact_id
                group by artifact.id, artifact.sha256, artifact.object_key
                order by artifact.sha256
                limit %s
                """,
                (
                    JOB_TYPE,
                    EXTRACTOR_VERSION,
                    EXTRACTOR_VERSION,
                    SCHEMA_VERSION,
                    limit,
                ),
            ).fetchall()
        finally:
            connection.close()
        targets: list[TcmBaIssueDateLayoutTarget] = []
        total_artifacts: int | None = None
        for row in rows:
            try:
                row_total = int(row["total_artifacts"])
                raw_counts = row["candidate_page_counts"]
                artifact_id = str(row["artifact_id"])
                sha256 = str(row["sha256"])
                object_key = str(row["object_key"])
            except (KeyError, TypeError, ValueError) as error:
                raise ProcessingError(
                    "O alvo espacial de data está incompleto."
                ) from error
            if total_artifacts is None:
                total_artifacts = row_total
            elif total_artifacts != row_total:
                raise ProcessingError("A contagem total dos alvos de data divergiu.")
            if isinstance(raw_counts, str):
                try:
                    raw_counts = json.loads(raw_counts)
                except json.JSONDecodeError as error:
                    raise ProcessingError(
                        "As páginas dos alvos de data não são JSON válido."
                    ) from error
            if not isinstance(raw_counts, list):
                raise ProcessingError(
                    "As páginas dos alvos de data não formam uma lista."
                )
            page_counts: list[tuple[int, int]] = []
            for raw_pair in raw_counts:
                if not isinstance(raw_pair, list) or len(raw_pair) != 2:
                    raise ProcessingError(
                        "Uma contagem de página da data é inválida."
                    )
                try:
                    page_number, candidate_count = map(int, raw_pair)
                except (TypeError, ValueError) as error:
                    raise ProcessingError(
                        "Uma contagem de página da data não é numérica."
                    ) from error
                if page_number < 1 or candidate_count < 1:
                    raise ProcessingError(
                        "Uma contagem de página da data está fora do limite."
                    )
                page_counts.append((page_number, candidate_count))
            if (
                len({page for page, _count in page_counts}) != len(page_counts)
                or page_counts != sorted(page_counts)
                or len(sha256) != 64
                or any(character not in "0123456789abcdef" for character in sha256)
                or not object_key
            ):
                raise ProcessingError("O alvo espacial de data é inválido.")
            targets.append(
                TcmBaIssueDateLayoutTarget(
                    artifact=TextArtifact(artifact_id, sha256, object_key),
                    candidate_page_counts=tuple(page_counts),
                )
            )
        if total_artifacts is not None and total_artifacts > limit:
            raise ProcessingError(
                "O benchmark de datas excedeu o limite de artefatos."
            )
        return tuple(targets)
    def commitment_coverage(self) -> TcmBaCommitmentCoverage:
        connection = self.connection_factory()
        try:
            connection.execute("set local statement_timeout = '30s'")
            row = connection.execute(
                """
                with tcm_artifacts as (
                  select artifact.id, artifact.sha256
                  from raw.raw_artifacts as artifact
                  where artifact.artifact_kind = 'document'
                    and artifact.metadata ->> 'schema_name'
                        = 'tcm-ba-monthly-document'
                    and artifact.content_type = 'application/pdf'
                    and artifact.http_status between 200 and 299
                ),
                resolved_pages as (
                  select base.raw_artifact_id,
                    coalesce(base.text_content, ocr.text_content)
                      as text_content,
                    coalesce(base.text_sha256, ocr.text_sha256) as text_sha256
                  from raw.document_pages as base
                  join tcm_artifacts as artifact
                    on artifact.id = base.raw_artifact_id
                  left join lateral (
                    select supplemental.text_content,
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
                commitment_coverage_eligible as (
                  select artifact.id as raw_artifact_id, artifact.sha256
                  from tcm_artifacts as artifact
                  join (
                    select page.raw_artifact_id
                    from resolved_pages as page
                    group by page.raw_artifact_id
                    having count(*) > 0
                      and bool_and(page.text_content is not null)
                      and bool_and(page.text_sha256 is not null)
                  ) as ready on ready.raw_artifact_id = artifact.id
                ),
                current_jobs as (
                  select job.id, job.raw_artifact_id, job.status
                  from raw.extraction_jobs as job
                  join commitment_coverage_eligible as eligible
                    on eligible.raw_artifact_id = job.raw_artifact_id
                  where job.job_type = %s
                    and job.idempotency_key = encode(
                      sha256(
                        ('tcm-ba-commitments:' || eligible.sha256 || ':' ||
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
                  join commitment_coverage_eligible as eligible
                    on eligible.raw_artifact_id = job.raw_artifact_id
                  join raw.extraction_results as result
                    on result.extraction_job_id = job.id
                  where result.candidate_type = 'tcm_ba_commitment_note'
                    and result.extractor_version = %s
                ),
                result_counts as (
                  select raw_artifact_id,
                    count(*)::integer as result_count,
                    count(distinct (
                      coalesce(result_payload ->> 'source_page_number', '') ||
                      ':' || coalesce(
                        result_payload ->> 'commitment_number', ''
                      )
                    ))::integer as distinct_candidates,
                    count(*) filter (
                      where result_payload ->> 'candidate_status' = 'complete'
                    )::integer as complete_count,
                    count(*) filter (
                      where result_payload ->> 'candidate_status' = 'incomplete'
                    )::integer as incomplete_count,
                    count(*) filter (
                      where coalesce(validation_status, '') <> 'needs_review'
                         or coalesce(
                              result_payload ->> 'schema_name', ''
                            ) <> 'tcm-ba-commitment-candidate'
                         or coalesce(
                              result_payload ->> 'schema_version', ''
                            ) <> %s
                         or coalesce(
                              result_payload ->> 'candidate_status', ''
                            ) not in ('complete', 'incomplete')
                         or coalesce(
                              result_payload ->> 'commitment_number', ''
                            ) = ''
                         or coalesce(
                              result_payload ->> 'source_page_number', ''
                            ) !~ '^[1-9][0-9]*$'
                         or coalesce(
                              result_payload ->> 'source_artifact_sha256', ''
                            ) <> source_artifact_sha256
                         or jsonb_typeof(result_payload -> 'missing_fields')
                            is distinct from 'array'
                         or case
                           when jsonb_typeof(
                             result_payload -> 'missing_fields'
                           ) = 'array'
                           then (
                             result_payload ->> 'candidate_status' = 'complete'
                             and jsonb_array_length(
                               result_payload -> 'missing_fields'
                             ) <> 0
                           ) or (
                             result_payload ->> 'candidate_status' = 'incomplete'
                             and jsonb_array_length(
                               result_payload -> 'missing_fields'
                             ) = 0
                           )
                           else false
                         end
                    )::integer as invalid_count
                  from current_results
                  group by raw_artifact_id
                )
                select
                  count(*)::integer as eligible_artifacts,
                  count(*) filter (
                    where job.status = 'succeeded'
                  )::integer as processed_artifacts,
                  coalesce(sum(counts.result_count), 0)::integer
                    as candidate_results,
                  coalesce(sum(counts.complete_count), 0)::integer
                    as complete_candidates,
                  coalesce(sum(counts.incomplete_count), 0)::integer
                    as incomplete_candidates,
                  count(*) filter (
                    where job.status = 'succeeded'
                      and coalesce(counts.result_count, 0) = 0
                  )::integer as zero_candidate_artifacts,
                  count(*) filter (
                    where job.id is null or job.status <> 'succeeded'
                  )::integer as missing_artifacts,
                  coalesce(sum(greatest(
                    counts.result_count - counts.distinct_candidates,
                    0
                  )), 0)::integer as duplicate_results,
                  coalesce(sum(counts.invalid_count), 0)::integer
                    as invalid_results,
                  (
                    select count(*)::integer
                    from current_jobs as failed_job
                    where failed_job.status in (
                      'failed', 'retry_scheduled', 'dead_lettered'
                    )
                  ) as open_failures
                from commitment_coverage_eligible as eligible
                left join current_jobs as job
                  on job.raw_artifact_id = eligible.raw_artifact_id
                left join result_counts as counts
                  on counts.raw_artifact_id = eligible.raw_artifact_id
                """,
                (
                    TCM_BA_OCR_PARSER_VERSION,
                    PDF_PARSER_VERSION,
                    JOB_TYPE,
                    EXTRACTOR_VERSION,
                    EXTRACTOR_VERSION,
                    SCHEMA_VERSION,
                ),
            ).fetchone()
            if row is None:
                raise ProcessingError(
                    "A cobertura dos candidatos de empenho não foi retornada."
                )
            try:
                coverage = TcmBaCommitmentCoverage(
                    eligible_artifacts=int(row["eligible_artifacts"]),
                    processed_artifacts=int(row["processed_artifacts"]),
                    candidate_results=int(row["candidate_results"]),
                    complete_candidates=int(row["complete_candidates"]),
                    incomplete_candidates=int(row["incomplete_candidates"]),
                    zero_candidate_artifacts=int(row["zero_candidate_artifacts"]),
                    missing_artifacts=int(row["missing_artifacts"]),
                    duplicate_results=int(row["duplicate_results"]),
                    invalid_results=int(row["invalid_results"]),
                    open_failures=int(row["open_failures"]),
                )
            except (KeyError, TypeError, ValueError) as error:
                raise ProcessingError(
                    "A cobertura dos candidatos de empenho está incompleta."
                ) from error
            if any(value < 0 for value in coverage.__dict__.values()):
                raise ProcessingError(
                    "A cobertura dos candidatos de empenho possui contador inválido."
                )
            return coverage
        finally:
            connection.close()

    def commitment_missing_field_breakdown(
        self,
    ) -> TcmBaCommitmentFieldBreakdown:
        connection = self.connection_factory()
        try:
            connection.execute("set local statement_timeout = '30s'")
            rows = connection.execute(
                """
                with tcm_artifacts as (
                  select artifact.id, artifact.sha256
                  from raw.raw_artifacts as artifact
                  where artifact.artifact_kind = 'document'
                    and artifact.metadata ->> 'schema_name'
                        = 'tcm-ba-monthly-document'
                    and artifact.content_type = 'application/pdf'
                    and artifact.http_status between 200 and 299
                ),
                current_jobs as (
                  select job.id
                  from raw.extraction_jobs as job
                  join tcm_artifacts as artifact
                    on artifact.id = job.raw_artifact_id
                  where job.job_type = %s
                    and job.status = 'succeeded'
                    and job.idempotency_key = encode(
                      sha256(
                        ('tcm-ba-commitments:' || artifact.sha256 || ':' ||
                          %s)::bytea
                      ),
                      'hex'
                    )
                ),
                current_results as (
                  select result.result_payload
                  from current_jobs as job
                  join raw.extraction_results as result
                    on result.extraction_job_id = job.id
                  where result.candidate_type = 'tcm_ba_commitment_note'
                    and result.extractor_version = %s
                )
                select
                  result_payload -> 'missing_fields' as missing_fields,
                  count(*)::integer as candidate_count,
                  count(*) filter (
                    where jsonb_typeof(
                      result_payload -> 'budget_allocation_evidence'
                    ) = 'object'
                  )::integer as spatial_budget_count,
                  count(*) filter (
                    where jsonb_typeof(
                      result_payload -> 'issue_date_evidence'
                    ) = 'object'
                  )::integer as spatial_issue_date_count,
                  count(*) filter (
                    where jsonb_typeof(
                      result_payload -> 'amount_text_evidence'
                    ) = 'object'
                  )::integer as spatial_amount_count,
                  count(*) filter (
                    where jsonb_typeof(
                      result_payload -> 'creditor_name_evidence'
                    ) = 'object'
                  )::integer as spatial_creditor_count,
                  count(*) filter (
                    where (
                      case
                        when result_payload -> 'issue_date_evidence' is null
                          or jsonb_typeof(
                            result_payload -> 'issue_date_evidence'
                          ) = 'null'
                          then false
                        when jsonb_typeof(
                          result_payload -> 'issue_date_evidence'
                        ) <> 'object'
                          then true
                        else
                          coalesce(result_payload ->> 'issue_date', '')
                            !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                          or coalesce(
                            result_payload -> 'issue_date_evidence'
                              ->> 'parser_version', ''
                          ) <> %s
                          or coalesce(
                            result_payload -> 'issue_date_evidence'
                              ->> 'page_number', ''
                          ) !~ '^[1-9][0-9]*$'
                          or (
                            result_payload -> 'issue_date_evidence'
                              ->> 'page_number'
                          ) <> result_payload ->> 'source_page_number'
                          or coalesce(
                            result_payload -> 'issue_date_evidence'
                              ->> 'label_block_order', ''
                          ) !~ '^[0-9]+$'
                          or coalesce(
                            result_payload -> 'issue_date_evidence'
                              ->> 'value_block_order', ''
                          ) !~ '^[0-9]+$'
                          or coalesce(
                            result_payload -> 'issue_date_evidence'
                              ->> 'relation', ''
                          ) not in ('below', 'right', 'inline')
                          or coalesce(
                            result_payload -> 'issue_date_evidence'
                              ->> 'occurrence_count', ''
                          ) !~ '^[1-9][0-9]*$'
                          or (
                            coalesce(
                              result_payload -> 'issue_date_evidence'
                                ->> 'relation', ''
                            ) <> 'inline'
                            and (
                              result_payload -> 'issue_date_evidence'
                                ->> 'occurrence_count'
                            ) <> '1'
                          )
                          or (
                            coalesce(
                              result_payload -> 'issue_date_evidence'
                                ->> 'relation', ''
                            ) = 'inline'
                            and (
                              result_payload -> 'issue_date_evidence'
                                ->> 'label_block_order'
                            ) <> (
                              result_payload -> 'issue_date_evidence'
                                ->> 'value_block_order'
                            )
                          )
                      end
                    ) or (
                      case
                        when result_payload -> 'amount_text_evidence' is null
                          or jsonb_typeof(
                            result_payload -> 'amount_text_evidence'
                          ) = 'null'
                          then false
                        when jsonb_typeof(
                          result_payload -> 'amount_text_evidence'
                        ) <> 'object'
                          then true
                        else
                          coalesce(result_payload ->> 'amount_text', '')
                            !~ '^-?[0-9.]+,[0-9]{2}$'
                          or coalesce(
                            result_payload -> 'amount_text_evidence'
                              ->> 'parser_version', ''
                          ) <> %s
                          or coalesce(
                            result_payload -> 'amount_text_evidence'
                              ->> 'page_number', ''
                          ) !~ '^[1-9][0-9]*$'
                          or (
                            result_payload -> 'amount_text_evidence'
                              ->> 'page_number'
                          ) <> result_payload ->> 'source_page_number'
                          or coalesce(
                            result_payload -> 'amount_text_evidence'
                              ->> 'label_block_order', ''
                          ) !~ '^[0-9]+$'
                          or coalesce(
                            result_payload -> 'amount_text_evidence'
                              ->> 'value_block_order', ''
                          ) !~ '^[0-9]+$'
                          or coalesce(
                            result_payload -> 'amount_text_evidence'
                              ->> 'relation', ''
                          ) not in ('below', 'right')
                      end
                    ) or (
                      case
                        when result_payload -> 'budget_allocation_evidence' is null
                          or jsonb_typeof(
                            result_payload -> 'budget_allocation_evidence'
                          ) = 'null'
                          then false
                        when jsonb_typeof(
                          result_payload -> 'budget_allocation_evidence'
                        ) <> 'object'
                          then true
                        else
                          coalesce(result_payload ->> 'budget_allocation', '') = ''
                          or coalesce(
                            result_payload -> 'budget_allocation_evidence'
                              ->> 'parser_version', ''
                          ) <> %s
                          or coalesce(
                            result_payload -> 'budget_allocation_evidence'
                              ->> 'page_number', ''
                          ) !~ '^[1-9][0-9]*$'
                          or (
                            result_payload -> 'budget_allocation_evidence'
                              ->> 'page_number'
                          ) <> result_payload ->> 'source_page_number'
                          or coalesce(
                            result_payload -> 'budget_allocation_evidence'
                              ->> 'label_block_order', ''
                          ) !~ '^[0-9]+$'
                          or coalesce(
                            result_payload -> 'budget_allocation_evidence'
                              ->> 'value_block_order', ''
                          ) !~ '^[0-9]+$'
                          or coalesce(
                            result_payload -> 'budget_allocation_evidence'
                              ->> 'relation', ''
                          ) not in ('below', 'right')
                      end
                    ) or (
                      case
                        when result_payload -> 'creditor_name_evidence' is null
                          or jsonb_typeof(
                            result_payload -> 'creditor_name_evidence'
                          ) = 'null'
                          then false
                        when jsonb_typeof(
                          result_payload -> 'creditor_name_evidence'
                        ) <> 'object'
                          then true
                        else
                          coalesce(result_payload ->> 'creditor_name', '') = ''
                          or coalesce(
                            result_payload -> 'creditor_name_evidence'
                              ->> 'parser_version', ''
                          ) <> %s
                          or coalesce(
                            result_payload -> 'creditor_name_evidence'
                              ->> 'page_number', ''
                          ) !~ '^[1-9][0-9]*$'
                          or (
                            result_payload -> 'creditor_name_evidence'
                              ->> 'page_number'
                          ) <> result_payload ->> 'source_page_number'
                          or coalesce(
                            result_payload -> 'creditor_name_evidence'
                              ->> 'label_block_order', ''
                          ) !~ '^[0-9]+$'
                          or coalesce(
                            result_payload -> 'creditor_name_evidence'
                              ->> 'value_block_order', ''
                          ) !~ '^[0-9]+$'
                          or coalesce(
                            result_payload -> 'creditor_name_evidence'
                              ->> 'relation', ''
                          ) not in ('below', 'right')
                      end
                    )
                  )::integer as invalid_spatial_count,
                  'commitment_missing_field_breakdown' as report_marker
                from current_results
                group by result_payload -> 'missing_fields'
                order by candidate_count desc,
                  (result_payload -> 'missing_fields')::text
                """,
                (
                    JOB_TYPE,
                    EXTRACTOR_VERSION,
                    EXTRACTOR_VERSION,
                    PDF_LAYOUT_VERSION,
                    PDF_LAYOUT_VERSION,
                    PDF_LAYOUT_VERSION,
                    PDF_LAYOUT_VERSION,
                ),
            ).fetchall()
        finally:
            connection.close()

        allowed_fields = {
            "issue_date",
            "creditor_name",
            "amount_text",
            "budget_allocation",
        }
        groups: list[TcmBaCommitmentMissingFieldGroup] = []
        spatial_budget_allocations = 0
        spatial_issue_dates = 0
        spatial_amounts = 0
        spatial_creditor_names = 0
        invalid_spatial_evidence = 0
        counts = {field: 0 for field in allowed_fields}
        complete_candidates = 0
        for row in rows:
            raw_fields = row["missing_fields"]
            if isinstance(raw_fields, str):
                try:
                    raw_fields = json.loads(raw_fields)
                except json.JSONDecodeError as error:
                    raise ProcessingError(
                        "A combinação de campos faltantes não é JSON válido."
                    ) from error
            if not isinstance(raw_fields, list) or any(
                not isinstance(field, str) for field in raw_fields
            ):
                raise ProcessingError(
                    "A combinação de campos faltantes não é uma lista textual."
                )
            missing_fields = tuple(raw_fields)
            if len(set(missing_fields)) != len(missing_fields) or not set(
                missing_fields
            ).issubset(allowed_fields):
                raise ProcessingError(
                    "A combinação de campos faltantes possui campo inválido."
                )
            try:
                candidate_count = int(row["candidate_count"])
                spatial_budget_count = int(row["spatial_budget_count"])
                spatial_issue_date_count = int(row["spatial_issue_date_count"])
                spatial_amount_count = int(row["spatial_amount_count"])
                spatial_creditor_count = int(row["spatial_creditor_count"])
                invalid_spatial_count = int(row["invalid_spatial_count"])
            except (KeyError, TypeError, ValueError) as error:
                raise ProcessingError(
                    "A distribuição de campos faltantes está incompleta."
                ) from error
            if (
                candidate_count < 0
                or spatial_budget_count < 0
                or spatial_budget_count > candidate_count
                or spatial_issue_date_count < 0
                or spatial_issue_date_count > candidate_count
                or spatial_amount_count < 0
                or spatial_amount_count > candidate_count
                or spatial_creditor_count < 0
                or spatial_creditor_count > candidate_count
                or invalid_spatial_count < 0
                or invalid_spatial_count > candidate_count
            ):
                raise ProcessingError(
                    "A distribuição de campos faltantes possui contador inválido."
                )
            if not missing_fields:
                complete_candidates += candidate_count
            for field in missing_fields:
                counts[field] += candidate_count
            spatial_budget_allocations += spatial_budget_count
            spatial_issue_dates += spatial_issue_date_count
            spatial_amounts += spatial_amount_count
            spatial_creditor_names += spatial_creditor_count
            invalid_spatial_evidence += invalid_spatial_count
            groups.append(
                TcmBaCommitmentMissingFieldGroup(
                    missing_fields=missing_fields,
                    candidates=candidate_count,
                )
            )
        groups.sort(
            key=lambda group: (-group.candidates, group.missing_fields),
        )
        total_candidates = sum(group.candidates for group in groups)
        if any(
            count > total_candidates
            for count in (
                spatial_budget_allocations,
                spatial_issue_dates,
                spatial_amounts,
                spatial_creditor_names,
            )
        ):
            raise ProcessingError(
                "A cobertura espacial excede a quantidade de candidatos."
            )
        return TcmBaCommitmentFieldBreakdown(
            total_candidates=total_candidates,
            complete_candidates=complete_candidates,
            spatial_budget_allocations=spatial_budget_allocations,
            spatial_issue_dates=spatial_issue_dates,
            spatial_amounts=spatial_amounts,
            spatial_creditor_names=spatial_creditor_names,
            invalid_spatial_evidence=invalid_spatial_evidence,
            missing_issue_date=counts["issue_date"],
            missing_creditor_name=counts["creditor_name"],
            missing_amount_text=counts["amount_text"],
            missing_budget_allocation=counts["budget_allocation"],
            groups=tuple(groups),
        )

    def persist_tcm_ba_commitment_candidates(
        self,
        batch: TcmBaCommitmentBatch,
    ) -> TcmBaCommitmentPersistResult:
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
                    return TcmBaCommitmentPersistResult(False, 0)

                inserted = 0
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
                          %s::uuid, 'tcm_ba_commitment_note', %s,
                          'human-review-required/1.0.0', %s::jsonb,
                          null, 'needs_review', %s::jsonb
                        )
                        """,
                        (
                            str(job["id"]),
                            batch.extractor_version,
                            canonical_json(
                                commitment_candidate_payload(
                                    candidate,
                                    batch.artifact,
                                )
                            ),
                            canonical_json(list(candidate.missing_fields)),
                        ),
                    )
                    inserted += 1
            return TcmBaCommitmentPersistResult(True, inserted)
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
