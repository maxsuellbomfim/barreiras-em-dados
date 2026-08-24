"""Persistência versionada dos totais anuais literais do SICONFI."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

from barreiras_collectors.persistence.postgres import DatabaseConnection

from .siconfi_annual_totals import (
    SICONFI_ANNUAL_TOTALS_JOB_TYPE,
    SICONFI_ANNUAL_TOTALS_PARSER_VERSION,
    SICONFI_ANNUAL_TOTALS_VALIDATOR_VERSION,
    SiconfiAnnualRawLine,
    SiconfiAnnualSnapshot,
    SiconfiAnnualTotal,
)


@dataclass(frozen=True)
class SiconfiAnnualPersistResult:
    job_created: bool
    totals_inserted: int
    totals_existing: int


def annual_job_idempotency_key(artifact_sha256: str) -> str:
    material = ":".join(
        (
            SICONFI_ANNUAL_TOTALS_JOB_TYPE,
            artifact_sha256,
            SICONFI_ANNUAL_TOTALS_PARSER_VERSION,
            SICONFI_ANNUAL_TOTALS_VALIDATOR_VERSION,
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class SiconfiAnnualTotalsRepository:
    def __init__(self, connection_factory: Callable[[], DatabaseConnection]) -> None:
        self.connection_factory = connection_factory

    @classmethod
    def from_dsn(cls, database_url: str) -> SiconfiAnnualTotalsRepository:
        from barreiras_collectors.persistence.postgres import (
            PostgresCollectionRepository,
        )

        collection = PostgresCollectionRepository.from_dsn(database_url)
        return cls(collection.connection_factory)

    def pending_snapshots(self, limit: int) -> tuple[SiconfiAnnualSnapshot, ...]:
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                with latest_artifacts as materialized (
                  select distinct on ((record.payload ->> 'exercicio')::smallint)
                    artifact.id,
                    artifact.sha256,
                    artifact.source_url,
                    artifact.retrieved_at,
                    (record.payload ->> 'exercicio')::smallint as fiscal_year
                  from raw.raw_records as record
                  join raw.raw_artifacts as artifact
                    on artifact.id = record.raw_artifact_id
                  where record.record_type = 'siconfi_dca_line'
                    and record.payload ->> 'cod_ibge' = '2903201'
                    and (record.payload ->> 'exercicio') ~ '^[0-9]{4}$'
                  order by
                    (record.payload ->> 'exercicio')::smallint,
                    artifact.retrieved_at desc,
                    artifact.id desc
                ),
                pending_artifacts as (
                  select latest.*
                  from latest_artifacts as latest
                  where not exists (
                    select 1
                    from raw.extraction_jobs as job
                    where job.raw_artifact_id = latest.id
                      and job.job_type = %s
                      and job.status in ('succeeded', 'dead_lettered')
                  )
                  order by latest.fiscal_year
                  limit %s
                )
                select
                  pending.id::text as artifact_id,
                  pending.sha256,
                  pending.source_url,
                  pending.retrieved_at::text,
                  pending.fiscal_year,
                  record.id::text as raw_record_id,
                  record.payload
                from pending_artifacts as pending
                join raw.raw_records as record
                  on record.raw_artifact_id = pending.id
                 and record.record_type = 'siconfi_dca_line'
                where record.payload ->> 'anexo' in (
                    'DCA-Anexo I-C', 'DCA-Anexo I-D'
                  )
                  and record.payload ->> 'rotulo' = 'Padrão'
                  and record.payload ->> 'cod_conta' in (
                    'TotalReceitas', 'TotalDespesas'
                  )
                order by pending.fiscal_year, record.record_index, record.id
                """,
                (SICONFI_ANNUAL_TOTALS_JOB_TYPE, limit),
            ).fetchall()
        finally:
            connection.close()

        grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in rows:
            grouped[str(row["artifact_id"])].append(row)
        snapshots = []
        for artifact_rows in grouped.values():
            first = artifact_rows[0]
            snapshots.append(
                SiconfiAnnualSnapshot(
                    fiscal_year=int(first["fiscal_year"]),
                    raw_artifact_id=str(first["artifact_id"]),
                    artifact_sha256=str(first["sha256"]),
                    source_url=str(first["source_url"]),
                    retrieved_at=str(first["retrieved_at"]),
                    rows=tuple(
                        SiconfiAnnualRawLine(
                            raw_record_id=str(row["raw_record_id"]),
                            payload=row["payload"],  # type: ignore[arg-type]
                        )
                        for row in artifact_rows
                    ),
                )
            )
        return tuple(sorted(snapshots, key=lambda item: item.fiscal_year))

    def persist_totals(
        self,
        snapshot: SiconfiAnnualSnapshot,
        totals: tuple[SiconfiAnnualTotal, ...],
    ) -> SiconfiAnnualPersistResult:
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
                        snapshot.raw_artifact_id,
                        SICONFI_ANNUAL_TOTALS_JOB_TYPE,
                        annual_job_idempotency_key(snapshot.artifact_sha256),
                    ),
                ).fetchone()
                if job is None:
                    return SiconfiAnnualPersistResult(False, 0, len(totals))

                body = connection.execute(
                    """
                    select id::text as id
                    from org.public_bodies
                    where ibge_code = '2903201' and body_type = 'executive'
                    order by version desc, created_at desc, id desc
                    limit 1
                    """
                ).fetchone()
                if body is None:
                    raise RuntimeError("Órgão executivo de Barreiras não cadastrado.")

                inserted = 0
                existing = 0
                for total in totals:
                    current = connection.execute(
                        """
                        select current.id::text as id, current.version
                        from finance.siconfi_annual_totals as current
                        where current.fiscal_year = %s
                          and current.metric_key = %s
                          and not exists (
                            select 1
                            from finance.siconfi_annual_totals as successor
                            where successor.supersedes_id = current.id
                          )
                        order by current.version desc, current.id desc
                        limit 1
                        """,
                        (total.fiscal_year, total.metric_key),
                    ).fetchone()
                    persisted = connection.execute(
                        """
                        insert into finance.siconfi_annual_totals (
                          origin_raw_record_id, source_artifact_id,
                          public_body_id, supersedes_id, version, fiscal_year,
                          metric_key, amount, official_annex, official_label,
                          official_column_label, official_account_code,
                          official_account_label, validation_status,
                          methodology_version
                        )
                        values (
                          %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s, %s,
                          %s, %s, %s, %s, %s, %s, %s, 'validated', %s
                        )
                        on conflict (origin_raw_record_id) do nothing
                        returning id::text as id
                        """,
                        (
                            total.raw_record_id,
                            total.raw_artifact_id,
                            str(body["id"]),
                            str(current["id"]) if current else None,
                            int(current["version"]) + 1 if current else 1,
                            total.fiscal_year,
                            total.metric_key,
                            total.amount,
                            total.official_annex,
                            total.official_label,
                            total.official_column_label,
                            total.official_account_code,
                            total.official_account_label,
                            total.methodology_version,
                        ),
                    ).fetchone()
                    if persisted is None:
                        existing += 1
                        continue
                    inserted += 1
                    total_id = str(persisted["id"])
                    locator = json.dumps(
                        {
                            "annex": total.official_annex,
                            "label": total.official_label,
                            "column": total.official_column_label,
                            "account_code": total.official_account_code,
                            "fiscal_year": total.fiscal_year,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    connection.execute(
                        """
                        insert into evidence.evidence_items (
                          target_type, target_id, raw_artifact_id,
                          raw_record_id, evidence_kind, source_url, excerpt,
                          locator, content_sha256, parser_version, is_primary
                        ) values (
                          'finance.siconfi_annual_totals', %s::uuid, %s::uuid,
                          %s::uuid, 'source_record', %s, %s, %s::jsonb, %s,
                          %s, true
                        )
                        """,
                        (
                            total_id,
                            total.raw_artifact_id,
                            total.raw_record_id,
                            snapshot.source_url,
                            total.evidence_text,
                            locator,
                            snapshot.artifact_sha256,
                            total.methodology_version,
                        ),
                    )
                    payload = json.dumps(
                        {
                            "fiscal_year": total.fiscal_year,
                            "metric_key": total.metric_key,
                            "amount": format(total.amount, "f"),
                            "evidence_sha256": total.evidence_sha256,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    connection.execute(
                        """
                        insert into raw.extraction_results (
                          extraction_job_id, candidate_type,
                          extractor_version, validator_version, result_payload,
                          confidence, validation_status, validation_errors
                        ) values (
                          %s::uuid, 'siconfi_annual_total', %s, %s,
                          %s::jsonb, null, 'valid', '[]'::jsonb
                        )
                        """,
                        (
                            str(job["id"]),
                            SICONFI_ANNUAL_TOTALS_PARSER_VERSION,
                            SICONFI_ANNUAL_TOTALS_VALIDATOR_VERSION,
                            payload,
                        ),
                    )
            return SiconfiAnnualPersistResult(True, inserted, existing)
        finally:
            connection.close()

    def persist_failure(
        self,
        snapshot: SiconfiAnnualSnapshot,
        *,
        error_code: str,
        error_detail: str,
    ) -> None:
        connection = self.connection_factory()
        try:
            with connection.transaction():
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
                        snapshot.raw_artifact_id,
                        SICONFI_ANNUAL_TOTALS_JOB_TYPE,
                        annual_job_idempotency_key(snapshot.artifact_sha256),
                        error_code[:64],
                        error_detail[:500],
                    ),
                )
        finally:
            connection.close()
