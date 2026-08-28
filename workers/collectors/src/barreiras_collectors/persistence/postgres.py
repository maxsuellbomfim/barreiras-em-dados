"""Registro transacional no PostgreSQL sem chamadas externas na transação."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from datetime import date, datetime
from typing import Any, Protocol

from ..connectors.direct_diary import DirectEditionTarget
from ..connectors.official_diary_catalog import ALLOWED_HOSTS as CATALOG_ALLOWED_HOSTS
from ..http import validate_https_url
from .models import (
    DirectEditionBatch,
    DocumentBatch,
    OfficialDocumentSearchBatch,
    PersistenceBatch,
    PersistenceContractError,
    RepositoryDirectEditionResult,
    RepositoryDocumentResult,
    RepositoryPersistResult,
    RepositorySearchResult,
    TcmBaDocumentAuditArtifact,
    TcmBaDocumentAuditSnapshot,
    TcmBaDocumentReference,
    TcmBaDocumentSelection,
)


class QueryResult(Protocol):
    def fetchone(self) -> Mapping[str, Any] | None: ...

    def fetchall(self) -> list[Mapping[str, Any]]: ...


class TransactionContext(Protocol):
    def __enter__(self) -> object: ...

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> bool | None: ...


class DatabaseConnection(Protocol):
    def execute(
        self,
        query: str,
        params: tuple[object, ...] | None = None,
    ) -> QueryResult: ...

    def transaction(self) -> TransactionContext: ...

    def close(self) -> None: ...


def _compatible_existing_record(
    prior: Mapping[str, Any] | None,
    *,
    artifact_sha256: str,
    source_record_key: str,
    record_type: str,
    payload_sha256: str,
    parser_version: str,
) -> bool:
    """Aceita replay do mesmo conteúdo mesmo quando o UUID do bruto mudou.

    O UUID do artefato é uma identidade interna da captura. A identidade
    idempotente do registro é formada pelo conteúdo preservado, pela chave
    oficial, pelo tipo e pelo parser; a posição na página pode mudar sem
    alterar o registro.
    """
    if prior is None:
        return False
    return (
        str(prior.get("artifact_sha256")) == artifact_sha256
        and str(prior.get("source_record_key")) == source_record_key
        and str(prior.get("record_type")) == record_type
        and str(prior.get("payload_sha256")) == payload_sha256
        and str(prior.get("parser_version")) == parser_version
    )


class PostgresCollectionRepository:
    """Persiste execução, observação bruta e registros com UPSERT atômico."""

    def __init__(self, connection_factory: Callable[[], DatabaseConnection]) -> None:
        self.connection_factory = connection_factory

    def collection_partition_checkpoint(
        self,
        *,
        source_code: str,
        endpoint_code: str,
        partition_key: str,
    ) -> dict[str, object] | None:
        """Lê o último checkpoint da partição sem expor tabelas ao frontend."""
        connection = self.connection_factory()
        try:
            row = connection.execute(
                """
                select partition.checkpoint
                from source.collection_partitions as partition
                join source.source_endpoints as endpoint
                  on endpoint.id = partition.source_endpoint_id
                join source.data_sources as source
                  on source.id = endpoint.data_source_id
                where source.slug = %s
                  and endpoint.slug = %s
                  and partition.partition_key = %s
                """,
                (source_code, endpoint_code, partition_key),
            ).fetchone()
            if row is None or not isinstance(row.get("checkpoint"), Mapping):
                return None
            return dict(row["checkpoint"])
        finally:
            connection.close()

    def tcm_ba_document_references(
        self,
        *,
        competence: str,
        limit: int,
    ) -> TcmBaDocumentSelection:
        """Seleciona documentos exatos de um catálogo mensal completo do TCM-BA."""
        if not re.fullmatch(r"(0[1-9]|1[0-2])/\d{4}", competence):
            raise ValueError("competence deve usar MM/AAAA.")
        if limit < 1 or limit > 5:
            raise ValueError("limit deve estar entre 1 e 5.")
        month, year = (int(part) for part in competence.split("/"))
        partition_key = f"competence:{year:04d}-{month:02d}"
        connection = self.connection_factory()
        try:
            coverage = connection.execute(
                """
                select
                  partition.source_endpoint_id,
                  partition.observed_records,
                  run.started_at,
                  run.completed_at
                from source.collection_partitions as partition
                join source.source_endpoints as endpoint
                  on endpoint.id = partition.source_endpoint_id
                join source.data_sources as source
                  on source.id = endpoint.data_source_id
                join source.collection_runs as run
                  on run.id = partition.collection_run_id
                where source.slug = 'tcm-ba'
                  and endpoint.slug = 'prestacoes-contas-mensais'
                  and partition.partition_key = %s
                  and partition.status = 'complete'
                  and partition.completed_at is not null
                  and partition.observed_records > 0
                  and run.status = 'succeeded'
                  and run.metrics ->> 'collection_outcome' = 'complete'
                """,
                (partition_key,),
            ).fetchone()
            if coverage is None:
                raise PersistenceContractError(
                    "Catálogo mensal TCM-BA não possui cobertura completa."
                )
            endpoint_id = str(coverage["source_endpoint_id"])
            started_at = coverage["started_at"]
            completed_at = coverage["completed_at"]
            expected = int(coverage["observed_records"])
            counted = connection.execute(
                """
                with ranked_artifacts as materialized (
                  select
                    artifact.id,
                    row_number() over (
                      partition by
                        (artifact.metadata -> 'cursor' ->> 'stage_index')::integer
                      order by child_run.started_at desc,
                               artifact.retrieved_at desc,
                               artifact.id desc
                    ) as observation_rank
                  from raw.raw_artifacts as artifact
                  join source.collection_runs as child_run
                    on child_run.id = artifact.collection_run_id
                  where artifact.source_endpoint_id = %s
                    and artifact.metadata ->> 'schema_name' =
                      'tcm-ba-monthly-public-accounts-interaction'
                    and artifact.metadata -> 'cursor' ->> 'stage_index'
                        ~ '^[0-9]+$'
                    and child_run.status = 'succeeded'
                    and child_run.started_at >= %s
                    and child_run.started_at <= %s
                )
                select
                  count(*) as documents,
                  count(distinct record.source_record_key) as unique_keys,
                  count(distinct (
                    (record.payload ->> 'page_number') || ':' ||
                    record.record_index::text
                  )) as unique_positions,
                  min(
                    ((record.payload ->> 'page_number')::integer - 1) * 10
                    + record.record_index + 1
                  ) as first_position,
                  max(
                    ((record.payload ->> 'page_number')::integer - 1) * 10
                    + record.record_index + 1
                  ) as last_position,
                  array_agg(
                    record.source_record_key
                    order by (record.payload ->> 'page_number')::integer,
                             record.record_index
                  ) as source_record_keys
                from raw.raw_records as record
                join ranked_artifacts as artifact
                  on artifact.id = record.raw_artifact_id
                 and artifact.observation_rank = 1
                where record.record_type = 'tcm_ba_monthly_document'
                  and record.payload ->> 'competence' = %s
                  and record.payload ->> 'page_number' ~ '^[1-9][0-9]*$'
                  and record.record_index between 0 and 9
                """,
                (endpoint_id, started_at, completed_at, competence),
            ).fetchone()
            metric_names = (
                "documents",
                "unique_keys",
                "unique_positions",
                "first_position",
                "last_position",
            )
            metrics = {
                key: int(counted[key])
                if counted is not None and counted[key] is not None
                else 0
                for key in metric_names
            }
            if (
                any(
                    metrics[key] != expected
                    for key in (
                        "documents",
                        "unique_keys",
                        "unique_positions",
                        "last_position",
                    )
                )
                or metrics["first_position"] != 1
            ):
                raise PersistenceContractError(
                    "Registros brutos TCM-BA divergem da cobertura mensal."
                )
            current_keys = tuple(
                str(value) for value in (counted["source_record_keys"] or ())
            )
            if len(current_keys) != expected or len(set(current_keys)) != expected:
                raise PersistenceContractError(
                    "Chaves do catálogo mensal TCM-BA estão incompletas."
                )
            pdf_prefix = f"tcm-ba/monthly-documents/{year:04d}/{month:02d}/pdf/" + chr(
                37
            )
            preserved_rows = connection.execute(
                """
                select distinct
                  artifact.metadata ->> 'source_record_key' as source_record_key
                from raw.raw_artifacts as artifact
                where artifact.source_endpoint_id = %s
                  and artifact.artifact_kind = 'document'
                  and artifact.metadata ->> 'schema_name' =
                    'tcm-ba-monthly-document'
                  and artifact.object_key like %s
                  and artifact.metadata ->> 'source_record_key' is not null
                """,
                (endpoint_id, pdf_prefix),
            ).fetchall()
            preserved_keys = sorted(
                set(current_keys).intersection(
                    str(row["source_record_key"]) for row in preserved_rows
                )
            )
            rows = connection.execute(
                """
                with ranked_artifacts as materialized (
                  select
                    artifact.id,
                    row_number() over (
                      partition by
                        (artifact.metadata -> 'cursor' ->> 'stage_index')::integer
                      order by child_run.started_at desc,
                               artifact.retrieved_at desc,
                               artifact.id desc
                    ) as observation_rank
                  from raw.raw_artifacts as artifact
                  join source.collection_runs as child_run
                    on child_run.id = artifact.collection_run_id
                  where artifact.source_endpoint_id = %s
                    and artifact.metadata ->> 'schema_name' =
                      'tcm-ba-monthly-public-accounts-interaction'
                    and artifact.metadata -> 'cursor' ->> 'stage_index'
                        ~ '^[0-9]+$'
                    and child_run.status = 'succeeded'
                    and child_run.started_at >= %s
                    and child_run.started_at <= %s
                )
                select
                  record.source_record_key,
                  artifact.id as parent_artifact_id,
                  record.record_index,
                  record.payload
                from raw.raw_records as record
                join ranked_artifacts as artifact
                  on artifact.id = record.raw_artifact_id
                 and artifact.observation_rank = 1
                where record.record_type = 'tcm_ba_monthly_document'
                  and record.payload ->> 'competence' = %s
                  and not (
                    record.source_record_key = any(%s::text[])
                  )
                order by
                  (record.payload ->> 'page_number')::integer,
                  record.record_index
                limit %s
                """,
                (
                    endpoint_id,
                    started_at,
                    completed_at,
                    competence,
                    preserved_keys,
                    limit,
                ),
            ).fetchall()
            references = tuple(
                self._tcm_ba_document_reference(
                    row,
                    competence=competence,
                    expected=expected,
                )
                for row in rows
            )
            preserved_documents = len(preserved_keys)
            pending = expected - preserved_documents
            if pending < 0 or len(references) != min(limit, pending):
                raise PersistenceContractError(
                    "Fila documental TCM-BA diverge dos artefatos preservados."
                )
            return TcmBaDocumentSelection(
                competence=competence,
                expected_total_documents=expected,
                preserved_documents=preserved_documents,
                pending_documents=pending,
                references=references,
            )
        finally:
            connection.close()

    def next_tcm_ba_document_competence(
        self,
        *,
        year_from: int = 2021,
    ) -> str | None:
        """Seleciona a competência mais antiga com catálogo completo."""
        if year_from < 2000 or year_from > 2100:
            raise ValueError("year_from deve estar entre 2000 e 2100.")
        connection = self.connection_factory()
        try:
            row = connection.execute(
                """
                select to_char(catalog.period_start, 'MM/YYYY') as competence
                from source.collection_partitions as catalog
                join source.source_endpoints as endpoint
                  on endpoint.id = catalog.source_endpoint_id
                join source.data_sources as source
                  on source.id = endpoint.data_source_id
                join source.collection_runs as catalog_run
                  on catalog_run.id = catalog.collection_run_id
                left join source.collection_partitions as documents
                  on documents.source_endpoint_id = catalog.source_endpoint_id
                 and documents.partition_key = replace(
                       catalog.partition_key,
                       'competence:',
                       'documents:'
                     )
                where source.slug = 'tcm-ba'
                  and endpoint.slug = 'prestacoes-contas-mensais'
                  and catalog.partition_key ~ '^competence:[0-9]{4}-[0-9]{2}$'
                  and catalog.period_start >= make_date(%s, 1, 1)
                  and catalog.status = 'complete'
                  and catalog.completed_at is not null
                  and catalog.observed_records > 0
                  and catalog_run.status = 'succeeded'
                  and catalog_run.metrics ->> 'collection_outcome' = 'complete'
                  and (
                    documents.id is null
                    or documents.status <> 'complete'
                    or documents.completed_at is null
                    or documents.observed_records < catalog.observed_records
                  )
                order by catalog.period_start, catalog.partition_key
                limit 1
                """,
                (year_from,),
            ).fetchone()
            if row is None:
                return None
            competence = str(row.get("competence") or "").strip()
            if not re.fullmatch(r"(0[1-9]|1[0-2])/\d{4}", competence):
                raise PersistenceContractError(
                    "A competência documental planejada é inválida."
                )
            return competence
        finally:
            connection.close()

    def tcm_ba_document_audit_snapshot(
        self,
        *,
        competence: str,
    ) -> TcmBaDocumentAuditSnapshot:
        """Lê cobertura, linhagem e artefatos do último lote documental."""
        if not re.fullmatch(r"(0[1-9]|1[0-2])/\d{4}", competence):
            raise ValueError("competence deve usar MM/AAAA.")
        month, year = (int(part) for part in competence.split("/"))
        partition_key = f"documents:{year:04d}-{month:02d}"
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set transaction read only")
                connection.execute("set local statement_timeout = '15s'")
                row = connection.execute(
                    """
                    select
                      partition.status,
                      partition.completed_at,
                      partition.observed_records,
                      partition.checkpoint,
                      partition.collection_run_id::text as run_id,
                      run.status as run_status,
                      run.metrics
                    from source.collection_partitions as partition
                    join source.source_endpoints as endpoint
                      on endpoint.id = partition.source_endpoint_id
                    join source.data_sources as source
                      on source.id = endpoint.data_source_id
                    join source.collection_runs as run
                      on run.id = partition.collection_run_id
                    where source.slug = 'tcm-ba'
                      and endpoint.slug = 'prestacoes-contas-mensais'
                      and partition.partition_key = %s
                    """,
                    (partition_key,),
                ).fetchone()
                if row is None:
                    raise PersistenceContractError(
                        "Partição documental TCM-BA não foi localizada."
                    )
                checkpoint = row.get("checkpoint")
                metrics = row.get("metrics")
                if not isinstance(checkpoint, Mapping) or not isinstance(
                    metrics, Mapping
                ):
                    raise PersistenceContractError(
                        "Controle documental TCM-BA possui métricas inválidas."
                    )
                run_id = str(row["run_id"])
                artifact_rows = connection.execute(
                    """
                    select
                      artifact.id::text as artifact_id,
                      artifact.parent_artifact_id::text as parent_artifact_id,
                      artifact.object_key,
                      artifact.sha256,
                      artifact.byte_size,
                      artifact.content_type,
                      artifact.http_status,
                      artifact.metadata ->> 'schema_name' as schema_name,
                      artifact.metadata ->> 'source_record_key'
                        as source_record_key
                    from raw.raw_artifacts as artifact
                    where artifact.collection_run_id = %s::uuid
                    order by artifact.retrieved_at, artifact.id
                    """,
                    (run_id,),
                ).fetchall()
                catalog_links = int(
                    connection.execute(
                        """
                        select count(*) as total
                        from raw.raw_artifacts as prepare
                        join raw.raw_artifacts as catalog
                          on catalog.id = prepare.parent_artifact_id
                        join raw.raw_records as record
                          on record.raw_artifact_id = catalog.id
                         and record.source_record_key =
                           prepare.metadata ->> 'source_record_key'
                        where prepare.collection_run_id = %s::uuid
                          and prepare.metadata ->> 'schema_name' =
                            'tcm-ba-document-download-prepare'
                          and record.record_type = 'tcm_ba_monthly_document'
                        """,
                        (run_id,),
                    ).fetchone()["total"]
                )
                current_open_failures = int(
                    connection.execute(
                        """
                        select count(*) as total
                        from source.collection_failures
                        where collection_run_id = %s::uuid
                          and status <> 'resolved'
                        """,
                        (run_id,),
                    ).fetchone()["total"]
                )
                historical_open_failures = int(
                    connection.execute(
                        """
                        select count(*) as total
                        from source.collection_failures
                        where partition_key = %s
                          and status <> 'resolved'
                        """,
                        (partition_key,),
                    ).fetchone()["total"]
                )
            try:
                artifacts = tuple(
                    TcmBaDocumentAuditArtifact(
                        artifact_id=str(item["artifact_id"]),
                        parent_artifact_id=str(item["parent_artifact_id"]),
                        object_key=str(item["object_key"]),
                        sha256=str(item["sha256"]),
                        byte_size=int(item["byte_size"]),
                        content_type=str(item["content_type"]),
                        http_status=int(item["http_status"]),
                        schema_name=str(item["schema_name"]),
                        source_record_key=str(item["source_record_key"]),
                    )
                    for item in artifact_rows
                )
                return TcmBaDocumentAuditSnapshot(
                    competence=competence,
                    partition_status=str(row["status"]),
                    partition_completed_at=row["completed_at"],
                    observed_records=int(row["observed_records"]),
                    checkpoint=dict(checkpoint),
                    run_status=str(row["run_status"]),
                    metrics=dict(metrics),
                    artifacts=artifacts,
                    catalog_links=catalog_links,
                    current_open_failures=current_open_failures,
                    historical_open_failures=historical_open_failures,
                )
            except (KeyError, TypeError, ValueError) as error:
                raise PersistenceContractError(
                    "Snapshot documental TCM-BA está incompleto."
                ) from error
        finally:
            connection.close()

    @staticmethod
    def _tcm_ba_document_reference(
        row: Mapping[str, Any],
        *,
        competence: str,
        expected: int,
    ) -> TcmBaDocumentReference:
        payload = row.get("payload")
        if not isinstance(payload, Mapping):
            raise PersistenceContractError("Payload bruto TCM-BA é inválido.")
        try:
            page_number = int(payload["page_number"])
            record_index = int(row["record_index"])
            document_position = (page_number - 1) * 10 + record_index + 1
            values = {
                key: str(payload[key]).strip()
                for key in ("category", "name", "inserted_at", "download_form_id")
            }
            source_record_key = str(row["source_record_key"]).strip()
            parent_artifact_id = str(row["parent_artifact_id"]).strip()
        except (KeyError, TypeError, ValueError) as error:
            raise PersistenceContractError(
                "Referência bruta TCM-BA está incompleta."
            ) from error
        if (
            page_number < 1
            or record_index < 0
            or record_index > 9
            or document_position < 1
            or document_position > expected
            or not all(values.values())
            or not source_record_key.startswith(f"tcm-ba:document:{competence}:")
            or not parent_artifact_id
        ):
            raise PersistenceContractError(
                "Referência bruta TCM-BA viola o contrato mensal."
            )
        return TcmBaDocumentReference(
            competence=competence,
            expected_total_documents=expected,
            document_position=document_position,
            source_record_key=source_record_key,
            parent_artifact_id=parent_artifact_id,
            category=values["category"],
            name=values["name"],
            inserted_at=values["inserted_at"],
            page_number=page_number,
            download_form_id=values["download_form_id"],
        )

    def historical_proposal_ids(
        self,
        *,
        year_from: int,
        year_to: int,
    ) -> frozenset[str]:
        """Obtém somente propostas municipais já preservadas e validadas."""
        if year_from < 2008 or year_to < year_from:
            raise ValueError("O período histórico solicitado é inválido.")
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                select distinct record.payload ->> 'id_proposta' as id_proposta
                from raw.raw_records as record
                where record.record_type = 'transferegov_historical_proposal'
                  and record.payload ->> 'cod_municipio_ibge' = '2903201'
                  and record.payload ->> 'id_proposta' ~ '^[0-9]+$'
                  and record.payload ->> 'ano_proposta' ~ '^[0-9]{4}$'
                  and (record.payload ->> 'ano_proposta')::integer
                      between %s and %s
                order by id_proposta
                """,
                (year_from, year_to),
            ).fetchall()
            return frozenset(str(row["id_proposta"]) for row in rows)
        finally:
            connection.close()

    def published_supplier_cnpjs(self) -> frozenset[str]:
        """CNPJs de fornecedores já publicados (PNCP e contratos municipais)."""
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                select distinct record.payload ->> 'niFornecedor' as cnpj
                from raw.raw_records as record
                where record.record_type = 'pncp_resultado'
                  and record.payload ->> 'niFornecedor' ~ '^[0-9]{14}$'
                union
                select distinct regexp_replace(
                  record.payload ->> 'documento', '[^0-9]', '', 'g'
                ) as cnpj
                from raw.raw_records as record
                where record.record_type = 'municipal_transparency_contratos'
                  and length(regexp_replace(
                    coalesce(record.payload ->> 'documento', ''), '[^0-9]', '', 'g'
                  )) = 14
                order by cnpj
                """,
                (),
            ).fetchall()
            return frozenset(str(row["cnpj"]) for row in rows)
        finally:
            connection.close()

    def start_controlled_run(
        self,
        *,
        source_code: str,
        endpoint_code: str,
        idempotency_key: str,
        collector_version: str,
        parser_version: str,
        period_start: date,
        period_end: date,
        started_at: datetime,
    ) -> str:
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '15s'")
                connection.execute("set local lock_timeout = '5s'")
                endpoint_id = self._endpoint_id(connection, source_code, endpoint_code)
                row = connection.execute(
                    """
                    insert into source.collection_runs (
                      source_endpoint_id, idempotency_key, collector_version,
                      parser_version, collection_window_start,
                      collection_window_end, status, attempt_count,
                      started_at, heartbeat_at, metrics
                    ) values (
                      %s::uuid, %s, %s, %s, %s::date, %s::date,
                      'running', 1, %s::timestamptz, %s::timestamptz,
                      '{"control_plane":true}'::jsonb
                    )
                    on conflict (idempotency_key) do nothing
                    returning id::text as id
                    """,
                    (
                        endpoint_id,
                        idempotency_key,
                        collector_version,
                        parser_version,
                        period_start,
                        period_end,
                        started_at,
                        started_at,
                    ),
                ).fetchone()
                if row is not None:
                    return str(row["id"])
                existing = connection.execute(
                    """
                    select id::text as id, source_endpoint_id::text as endpoint_id
                    from source.collection_runs
                    where idempotency_key = %s
                    """,
                    (idempotency_key,),
                ).fetchone()
                if existing is None or str(existing["endpoint_id"]) != endpoint_id:
                    raise PersistenceContractError(
                        "Conflito de idempotência no controle da coleta."
                    )
                return str(existing["id"])
        finally:
            connection.close()

    def complete_controlled_run(
        self,
        *,
        run_id: str,
        partition_key: str,
        period_start: date,
        period_end: date,
        outcome: str,
        observed_records: int,
        checkpoint: Mapping[str, object],
        metrics: Mapping[str, object],
        block_reason: str | None,
        partial_failure: Mapping[str, object] | None,
        completed_at: datetime,
    ) -> None:
        run_status = "partial" if outcome in {"partial", "blocked"} else "succeeded"
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '15s'")
                connection.execute("set local lock_timeout = '5s'")
                run = connection.execute(
                    """
                    update source.collection_runs
                    set status = %s,
                        cursor_after = %s::jsonb,
                        completed_at = %s::timestamptz,
                        heartbeat_at = %s::timestamptz,
                        metrics = metrics || %s::jsonb,
                        error_code = null,
                        error_detail = null
                    where id = %s::uuid
                    returning source_endpoint_id::text as endpoint_id,
                              attempt_count
                    """,
                    (
                        run_status,
                        self._json(checkpoint),
                        completed_at,
                        completed_at,
                        self._json({**metrics, "collection_outcome": outcome}),
                        run_id,
                    ),
                ).fetchone()
                if run is None:
                    raise PersistenceContractError("Execução controlada inexistente.")
                connection.execute(
                    """
                    insert into source.collection_partitions (
                      source_endpoint_id, partition_key, period_start, period_end,
                      status, observed_records, collection_run_id, checkpoint,
                      last_attempted_at, completed_at, block_reason
                    ) values (
                      %s::uuid, %s, %s::date, %s::date, %s, %s, %s::uuid,
                      %s::jsonb, %s::timestamptz, %s::timestamptz, %s
                    )
                    on conflict (source_endpoint_id, partition_key) do update
                    set period_start = excluded.period_start,
                        period_end = excluded.period_end,
                        status = excluded.status,
                        observed_records = excluded.observed_records,
                        collection_run_id = excluded.collection_run_id,
                        checkpoint = excluded.checkpoint,
                        last_attempted_at = excluded.last_attempted_at,
                        completed_at = excluded.completed_at,
                        block_reason = excluded.block_reason
                    """,
                    (
                        str(run["endpoint_id"]),
                        partition_key,
                        period_start,
                        period_end,
                        outcome,
                        observed_records,
                        run_id,
                        self._json(checkpoint),
                        completed_at,
                        completed_at,
                        block_reason,
                    ),
                )
                if partial_failure is not None:
                    retryable = bool(partial_failure["retryable"])
                    connection.execute(
                        """
                        insert into source.collection_failures (
                          collection_run_id, source_endpoint_id, partition_key,
                          status, error_type, error_detail, attempt_count,
                          retryable, failed_at
                        ) values (
                          %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s,
                          %s::timestamptz
                        )
                        on conflict (collection_run_id) do update
                        set status = excluded.status,
                            error_type = excluded.error_type,
                            error_detail = excluded.error_detail,
                            attempt_count = excluded.attempt_count,
                            retryable = excluded.retryable,
                            failed_at = excluded.failed_at,
                            resolved_at = null,
                            resolution_run_id = null
                        """,
                        (
                            run_id,
                            str(run["endpoint_id"]),
                            partition_key,
                            "retry_scheduled" if retryable else "open",
                            str(partial_failure["error_type"]),
                            str(partial_failure["error_detail"]),
                            int(run["attempt_count"]),
                            retryable,
                            completed_at,
                        ),
                    )
                elif outcome in {"complete", "empty"}:
                    connection.execute(
                        """
                        update source.collection_failures
                        set status = 'resolved',
                            resolved_at = %s::timestamptz,
                            resolution_run_id = %s::uuid
                        where source_endpoint_id = %s::uuid
                          and partition_key = %s
                          and status <> 'resolved'
                        """,
                        (
                            completed_at,
                            run_id,
                            str(run["endpoint_id"]),
                            partition_key,
                        ),
                    )
        finally:
            connection.close()

    def fail_controlled_run(
        self,
        *,
        run_id: str,
        partition_key: str,
        period_start: date,
        period_end: date,
        error_type: str,
        error_detail: str,
        retryable: bool,
        failed_at: datetime,
    ) -> None:
        failure_status = "retry_scheduled" if retryable else "open"
        run_status = "retry_scheduled" if retryable else "failed"
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '15s'")
                connection.execute("set local lock_timeout = '5s'")
                run = connection.execute(
                    """
                    update source.collection_runs
                    set status = %s,
                        completed_at = %s::timestamptz,
                        heartbeat_at = %s::timestamptz,
                        error_code = %s,
                        error_detail = %s
                    where id = %s::uuid
                    returning source_endpoint_id::text as endpoint_id,
                              attempt_count
                    """,
                    (
                        run_status,
                        failed_at,
                        failed_at,
                        error_type,
                        error_detail,
                        run_id,
                    ),
                ).fetchone()
                if run is None:
                    raise PersistenceContractError("Execução controlada inexistente.")
                connection.execute(
                    """
                    insert into source.collection_failures (
                      collection_run_id, source_endpoint_id, partition_key,
                      status, error_type, error_detail, attempt_count,
                      retryable, failed_at
                    ) values (
                      %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s,
                      %s::timestamptz
                    )
                    on conflict (collection_run_id) do nothing
                    """,
                    (
                        run_id,
                        str(run["endpoint_id"]),
                        partition_key,
                        failure_status,
                        error_type,
                        error_detail,
                        int(run["attempt_count"]),
                        retryable,
                        failed_at,
                    ),
                )
                connection.execute(
                    """
                    insert into source.collection_partitions (
                      source_endpoint_id, partition_key, period_start, period_end,
                      status, observed_records, collection_run_id,
                      last_attempted_at, completed_at, block_reason
                    ) values (
                      %s::uuid, %s, %s::date, %s::date, 'failed', 0,
                      %s::uuid, %s::timestamptz, null, %s
                    )
                    on conflict (source_endpoint_id, partition_key) do update
                    set status = 'failed',
                        collection_run_id = excluded.collection_run_id,
                        last_attempted_at = excluded.last_attempted_at,
                        completed_at = null,
                        block_reason = excluded.block_reason
                    """,
                    (
                        str(run["endpoint_id"]),
                        partition_key,
                        period_start,
                        period_end,
                        run_id,
                        failed_at,
                        error_type,
                    ),
                )
        finally:
            connection.close()

    def normalize_pncp_contracts(self, limit: int = 500) -> Mapping[str, Any]:
        """Materializa contratos PNCP já preservados, sem inferir empenhos."""
        if not 1 <= limit <= 5000:
            raise ValueError("limit deve estar entre 1 e 5000")
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '15s'")
                connection.execute("set local lock_timeout = '5s'")
                row = connection.execute(
                    """
                    select procurements_inserted,
                           suppliers_inserted,
                           contracts_inserted,
                           contracts_skipped
                      from procurement.normalize_pncp_contracts(%s)
                    """,
                    (limit,),
                ).fetchone()
            if row is None:
                raise PersistenceContractError(
                    "A normalização PNCP não retornou métricas."
                )
            return row
        finally:
            connection.close()

    def normalize_pncp_items(self, limit: int = 500) -> Mapping[str, Any]:
        """Materializa itens PNCP preservados, mantendo o vínculo oficial."""
        if not 1 <= limit <= 5000:
            raise ValueError("limit deve estar entre 1 e 5000")
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '15s'")
                connection.execute("set local lock_timeout = '5s'")
                row = connection.execute(
                    """
                    select items_inserted,
                           items_skipped
                      from procurement.normalize_pncp_items(%s)
                    """,
                    (limit,),
                ).fetchone()
            if row is None:
                raise PersistenceContractError(
                    "A normalização dos itens PNCP não retornou métricas."
                )
            return row
        finally:
            connection.close()

    @classmethod
    def from_dsn(cls, database_url: str) -> PostgresCollectionRepository:
        if not database_url.strip():
            raise ValueError("DATABASE_URL é obrigatória.")
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:
            raise RuntimeError(
                "Instale a dependência opcional 'postgres' para usar PostgreSQL."
            ) from error

        def connect() -> DatabaseConnection:
            return psycopg.connect(  # type: ignore[return-value]
                database_url,
                autocommit=True,
                row_factory=dict_row,
            )

        return cls(connect)

    def persist(self, batch: PersistenceBatch) -> RepositoryPersistResult:
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '15s'")
                connection.execute("set local lock_timeout = '5s'")
                endpoint_id = self._endpoint_id(
                    connection,
                    batch.page.source_code,
                    batch.page.endpoint_code,
                )
                run_id = self._collection_run_id(connection, batch, endpoint_id)
                artifact_id = self._artifact_id(
                    connection,
                    batch,
                    endpoint_id,
                    run_id,
                )
                inserted, existing = self._records(
                    connection,
                    batch,
                    artifact_id,
                )
            return RepositoryPersistResult(
                collection_run_id=run_id,
                raw_artifact_id=artifact_id,
                inserted_records=inserted,
                existing_records=existing,
            )
        finally:
            connection.close()

    def persist_official_document_searches(
        self,
        batch: OfficialDocumentSearchBatch,
    ) -> RepositorySearchResult:
        if not batch.searches or not batch.evidence_artifacts:
            raise ValueError("Busca oficial exige períodos e evidências.")
        ordered_evidence = tuple(
            sorted(batch.evidence_artifacts, key=lambda item: item.raw_artifact_id)
        )
        manifest_sha256 = hashlib.sha256(
            "\n".join(
                f"{item.raw_artifact_id}:{item.sha256}" for item in ordered_evidence
            ).encode("utf-8")
        ).hexdigest()
        checked_at = max(item.retrieved_at for item in ordered_evidence)
        connection = self.connection_factory()
        inserted = 0
        existing = 0
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '15s'")
                connection.execute("set local lock_timeout = '5s'")
                endpoint_id = self._endpoint_id(
                    connection,
                    batch.source_code,
                    batch.endpoint_code,
                )
                for evidence in ordered_evidence:
                    row = connection.execute(
                        """
                        select id::text as id
                        from raw.raw_artifacts
                        where id = %s::uuid
                          and source_endpoint_id = %s::uuid
                          and artifact_kind = 'http_response'
                          and sha256 = %s
                        """,
                        (evidence.raw_artifact_id, endpoint_id, evidence.sha256),
                    ).fetchone()
                    if row is None:
                        raise PersistenceContractError(
                            "Evidência da busca não pertence ao bruto preservado."
                        )

                for search in batch.searches:
                    search_row = connection.execute(
                        """
                        insert into source.official_document_searches (
                          source_endpoint_id, resource, period_start, period_end,
                          search_status, match_count, evidence_manifest_sha256,
                          evidence_artifact_count, checked_at, methodology_version
                        ) values (
                          %s::uuid, %s, %s::date, %s::date, %s, %s, %s, %s,
                          %s::timestamptz, %s
                        )
                        on conflict (
                          source_endpoint_id, resource, period_start,
                          evidence_manifest_sha256
                        ) do nothing
                        returning id::text as id
                        """,
                        (
                            endpoint_id,
                            batch.resource,
                            search.period_start,
                            search.period_end,
                            search.search_status,
                            search.match_count,
                            manifest_sha256,
                            len(ordered_evidence),
                            checked_at,
                            batch.methodology_version,
                        ),
                    ).fetchone()
                    if search_row is None:
                        prior = connection.execute(
                            """
                            select id::text as id, search_status, match_count,
                                   evidence_artifact_count, methodology_version
                            from source.official_document_searches
                            where source_endpoint_id = %s::uuid
                              and resource = %s
                              and period_start = %s::date
                              and evidence_manifest_sha256 = %s
                            """,
                            (
                                endpoint_id,
                                batch.resource,
                                search.period_start,
                                manifest_sha256,
                            ),
                        ).fetchone()
                        if (
                            prior is None
                            or str(prior["search_status"]) != search.search_status
                            or int(prior["match_count"]) != search.match_count
                            or int(prior["evidence_artifact_count"])
                            != len(ordered_evidence)
                            or str(prior["methodology_version"])
                            != batch.methodology_version
                        ):
                            raise PersistenceContractError(
                                "Conflito de idempotência na busca oficial."
                            )
                        search_id = str(prior["id"])
                        existing += 1
                    else:
                        search_id = str(search_row["id"])
                        inserted += 1
                    for order, evidence in enumerate(ordered_evidence, start=1):
                        connection.execute(
                            """
                            insert into source.official_document_search_artifacts (
                              official_document_search_id, raw_artifact_id,
                              artifact_order
                            ) values (%s::uuid, %s::uuid, %s)
                            on conflict do nothing
                            """,
                            (search_id, evidence.raw_artifact_id, order),
                        )
            return RepositorySearchResult(
                inserted_searches=inserted,
                existing_searches=existing,
            )
        finally:
            connection.close()

    def next_direct_edition_number(self, first_edition: int) -> int:
        """Próxima edição a sondar, derivada do que já está preservado."""
        connection = self.connection_factory()
        try:
            row = connection.execute(
                """
                select greatest(
                  coalesce((
                    select max((artifact.metadata ->> 'edition')::integer)
                    from raw.raw_artifacts as artifact
                    where artifact.metadata ->> 'schema_name'
                        = 'gazette-direct-edition'
                  ), 0),
                  coalesce((
                    select max((record.payload ->> 'edition')::integer)
                    from raw.raw_records as record
                    where record.record_type = 'querido_diario_gazette'
                      and record.payload ->> 'edition' ~ '^[0-9]+$'
                  ), 0),
                  %s - 1
                ) + 1 as next_edition
                """,
                (first_edition,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise PersistenceContractError(
                "Não foi possível derivar o cursor de edições."
            )
        return int(row["next_edition"])

    def pending_direct_catalog_editions(
        self,
        limit: int,
    ) -> tuple[DirectEditionTarget, ...]:
        """Edições oficiais conhecidas que ainda não possuem PDF preservado."""
        if limit < 1:
            raise ValueError("O limite deve ser positivo.")
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                with latest_publications as (
                  select distinct on (
                    (record.payload ->> 'edition')::integer,
                    (record.payload ->> 'date')::date
                  )
                    (record.payload ->> 'edition')::integer as edition_number,
                    extract(
                      year from (record.payload ->> 'date')::date
                    )::integer as edition_year,
                    record.payload ->> 'publication_url' as publication_url
                  from raw.raw_records as record
                  where record.record_type = 'barreiras_diario_publication'
                    and record.payload ->> 'edition' ~ '^[0-9]+$'
                    and record.payload ->> 'date'
                        ~ '^\\d{4}-\\d{2}-\\d{2}$'
                    and record.payload ->> 'publication_url' is not null
                  order by
                    (record.payload ->> 'edition')::integer,
                    (record.payload ->> 'date')::date,
                    record.collected_at desc
                )
                select
                  publication.edition_number,
                  publication.edition_year,
                  publication.publication_url
                from latest_publications as publication
                where not exists (
                  select 1
                  from raw.raw_artifacts as artifact
                  where artifact.metadata ->> 'schema_name'
                      = 'gazette-direct-edition'
                    and artifact.metadata ->> 'edition'
                        = publication.edition_number::text
                    and artifact.metadata ->> 'year'
                        = publication.edition_year::text
                )
                order by publication.edition_number desc
                limit %s
                """,
                (limit,),
            )
            targets: list[DirectEditionTarget] = []
            while (row := rows.fetchone()) is not None:
                publication_url = str(row["publication_url"])
                validate_https_url(publication_url, CATALOG_ALLOWED_HOSTS)
                targets.append(
                    DirectEditionTarget(
                        edition_number=int(row["edition_number"]),
                        year=int(row["edition_year"]),
                        publication_url=publication_url,
                    )
                )
            return tuple(targets)
        finally:
            connection.close()

    def persist_direct_edition(
        self,
        batch: DirectEditionBatch,
    ) -> RepositoryDirectEditionResult:
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '15s'")
                connection.execute("set local lock_timeout = '5s'")
                endpoint_id = self._endpoint_id(
                    connection,
                    batch.source_code,
                    batch.endpoint_code,
                )
                document = batch.document
                run_row = connection.execute(
                    """
                    insert into source.collection_runs (
                      source_endpoint_id,
                      idempotency_key,
                      collector_version,
                      parser_version,
                      cursor_before,
                      cursor_after,
                      status,
                      attempt_count,
                      started_at,
                      completed_at,
                      heartbeat_at,
                      metrics
                    )
                    values (
                      %s::uuid, %s, %s, 'not-applicable',
                      %s::jsonb, %s::jsonb, 'succeeded', %s,
                      %s::timestamptz, %s::timestamptz, %s::timestamptz,
                      %s::jsonb
                    )
                    on conflict (idempotency_key) do nothing
                    returning id::text as id
                    """,
                    (
                        endpoint_id,
                        batch.run_idempotency_key,
                        batch.collector_version,
                        self._json({"edition": batch.edition_number - 1}),
                        self._json({"edition": batch.edition_number}),
                        document.attempts,
                        document.requested_at,
                        document.received_at,
                        document.received_at,
                        self._json(
                            {
                                "edition": batch.edition_number,
                                "year": batch.edition_year,
                                "body_size_bytes": document.body_size_bytes,
                            }
                        ),
                    ),
                ).fetchone()
                if run_row is not None:
                    run_id = str(run_row["id"])
                else:
                    existing_run = connection.execute(
                        """
                        select id::text as id
                        from source.collection_runs
                        where idempotency_key = %s
                        """,
                        (batch.run_idempotency_key,),
                    ).fetchone()
                    if existing_run is None:
                        raise PersistenceContractError(
                            "Conflito de idempotência na execução direta."
                        )
                    run_id = str(existing_run["id"])

                metadata = {
                    "schema_name": "gazette-direct-edition",
                    "schema_version": "1.0.0",
                    "edition": batch.edition_number,
                    "year": batch.edition_year,
                    "document_role": "pdf",
                    "final_url": document.final_url,
                }
                artifact_row = connection.execute(
                    """
                    insert into raw.raw_artifacts (
                      collection_run_id,
                      source_endpoint_id,
                      idempotency_key,
                      artifact_kind,
                      source_url,
                      retrieved_at,
                      source_etag,
                      http_status,
                      content_type,
                      byte_size,
                      sha256,
                      object_key,
                      collector_version,
                      response_headers,
                      metadata
                    )
                    values (
                      %s::uuid, %s::uuid, %s, 'document', %s,
                      %s::timestamptz, %s, %s, %s, %s, %s, %s, %s,
                      %s::jsonb, %s::jsonb
                    )
                    on conflict (idempotency_key) do nothing
                    returning id::text as id
                    """,
                    (
                        run_id,
                        endpoint_id,
                        batch.artifact_idempotency_key,
                        document.source_url,
                        document.received_at,
                        dict(document.response_headers).get("etag"),
                        document.http_status,
                        document.media_type,
                        document.body_size_bytes,
                        document.body_sha256,
                        batch.object_key,
                        batch.collector_version,
                        self._json(dict(document.response_headers)),
                        self._json(metadata),
                    ),
                ).fetchone()
                if artifact_row is not None:
                    return RepositoryDirectEditionResult(
                        collection_run_id=run_id,
                        raw_artifact_id=str(artifact_row["id"]),
                        created=True,
                    )

                existing = connection.execute(
                    """
                    select id::text as id, sha256, byte_size, object_key
                    from raw.raw_artifacts
                    where idempotency_key = %s
                    """,
                    (batch.artifact_idempotency_key,),
                ).fetchone()
                if (
                    existing is None
                    or str(existing["sha256"]) != document.body_sha256
                    or int(existing["byte_size"]) != document.body_size_bytes
                    or str(existing["object_key"]) != batch.object_key
                ):
                    raise PersistenceContractError(
                        "Conflito de idempotência na edição direta."
                    )
                return RepositoryDirectEditionResult(
                    collection_run_id=run_id,
                    raw_artifact_id=str(existing["id"]),
                    created=False,
                )
        finally:
            connection.close()

    def pncp_backfill_anchor(self) -> date | None:
        """Data mais antiga com cobertura integral classificada no PNCP."""
        connection = self.connection_factory()
        try:
            row = connection.execute(
                """
                select min(partition.period_start)::date as anchor
                from source.collection_partitions as partition
                join source.collection_runs as run
                  on run.id = partition.collection_run_id
                join source.source_endpoints as endpoint
                  on endpoint.id = partition.source_endpoint_id
                join source.data_sources as data_source
                  on data_source.id = endpoint.data_source_id
                where data_source.slug = 'pncp'
                  and endpoint.slug = 'consulta-contratacoes'
                  and partition.status in ('complete', 'empty')
                  and run.status = 'succeeded'
                  and partition.period_start is not null
                """
            ).fetchone()
        finally:
            connection.close()
        if row is None or row["anchor"] is None:
            return None
        value = row["anchor"]
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value))

    def pncp_pending_itens(
        self,
        *,
        refresh_days: int,
        limit: int,
        offset: int = 0,
    ) -> list[tuple[str, int, int]]:
        """Contratações sem itens preservados ou recentes o bastante para
        revisitar (homologação chega semanas após a publicação)."""
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                with contratacao as (
                  select distinct on (record.payload ->> 'numeroControlePNCP')
                    record.payload ->> 'numeroControlePNCP' as control,
                    (record.payload ->> 'anoCompra')::int as ano,
                    (record.payload ->> 'sequencialCompra')::int as sequencial,
                    case
                      when record.payload ->> 'dataPublicacaoPncp'
                          ~ '^\\d{4}-\\d{2}-\\d{2}'
                      then left(
                        record.payload ->> 'dataPublicacaoPncp', 10
                      )::date
                    end as published_on
                  from raw.raw_records as record
                  where record.record_type = 'pncp_contratacao'
                    and record.payload ->> 'anoCompra' ~ '^[0-9]+$'
                    and record.payload ->> 'sequencialCompra' ~ '^[0-9]+$'
                  order by
                    record.payload ->> 'numeroControlePNCP',
                    record.created_at desc
                )
                select control, ano, sequencial
                from contratacao
                where coalesce(
                    published_on >= current_date - %s::int, false
                  )
                  or not exists (
                    select 1
                    from raw.raw_artifacts as artifact
                    where artifact.metadata ->> 'schema_name'
                        = 'pncp-itens-page'
                      and (artifact.metadata -> 'cursor' ->> 'ano')::int
                        = contratacao.ano
                      and (
                        artifact.metadata -> 'cursor' ->> 'sequencial'
                      )::int = contratacao.sequencial
                  )
                order by published_on desc nulls last, control
                limit %s offset %s
                """,
                (refresh_days, limit, offset),
            ).fetchall()
        finally:
            connection.close()
        return [
            (str(row["control"]), int(row["ano"]), int(row["sequencial"]))
            for row in rows
        ]

    def pncp_pending_contratos(
        self,
        *,
        refresh_days: int,
        limit: int,
        offset: int = 0,
    ) -> list[tuple[str, int, int]]:
        """ContrataÃ§Ãµes sem snapshot de contratos/empenhos preservado."""
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                with contratacao as (
                  select distinct on (record.payload ->> 'numeroControlePNCP')
                    record.payload ->> 'numeroControlePNCP' as control,
                    (record.payload ->> 'anoCompra')::int as ano,
                    (record.payload ->> 'sequencialCompra')::int as sequencial,
                    case
                      when record.payload ->> 'dataPublicacaoPncp'
                          ~ '^\\d{4}-\\d{2}-\\d{2}'
                      then left(
                        record.payload ->> 'dataPublicacaoPncp', 10
                      )::date
                    end as published_on
                  from raw.raw_records as record
                  where record.record_type = 'pncp_contratacao'
                    and record.payload ->> 'anoCompra' ~ '^[0-9]+$'
                    and record.payload ->> 'sequencialCompra' ~ '^[0-9]+$'
                  order by
                    record.payload ->> 'numeroControlePNCP',
                    record.created_at desc
                )
                select control, ano, sequencial
                from contratacao
                where coalesce(
                    published_on >= current_date - %s::int, false
                  )
                  or not exists (
                    select 1
                    from raw.raw_artifacts as artifact
                    where artifact.metadata ->> 'schema_name'
                        = 'pncp-contratos-page'
                      and (artifact.metadata -> 'cursor' ->> 'ano')::int
                        = contratacao.ano
                      and (
                        artifact.metadata -> 'cursor' ->> 'sequencial'
                      )::int = contratacao.sequencial
                  )
                order by published_on desc nulls last, control
                limit %s offset %s
                """,
                (refresh_days, limit, offset),
            ).fetchall()
        finally:
            connection.close()
        return [
            (str(row["control"]), int(row["ano"]), int(row["sequencial"]))
            for row in rows
        ]

    def pncp_itens_com_resultado(self, control: str) -> set[int]:
        """Itens da contratação que já têm algum resultado preservado."""
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                select distinct (record.payload ->> 'numeroItem')::bigint
                  as numero_item
                from raw.raw_records as record
                where record.record_type = 'pncp_resultado'
                  and record.payload ->> 'numeroControlePNCPCompra' = %s
                  and record.payload ->> 'numeroItem' ~ '^[0-9]+$'
                """,
                (control,),
            ).fetchall()
        finally:
            connection.close()
        return {int(row["numero_item"]) for row in rows}

    def persist_registry_snapshot(
        self,
        snapshot,
        *,
        object_key: str,
        artifact_idempotency_key: str,
        run_idempotency_key: str,
        collector_version: str,
    ) -> RepositoryDirectEditionResult:
        from ..connectors.pncp import ENDPOINT_CODE, SOURCE_CODE

        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '15s'")
                connection.execute("set local lock_timeout = '5s'")
                endpoint_id = self._endpoint_id(
                    connection,
                    SOURCE_CODE,
                    ENDPOINT_CODE,
                )
                run_row = connection.execute(
                    """
                    insert into source.collection_runs (
                      source_endpoint_id, idempotency_key,
                      collector_version, parser_version,
                      cursor_before, cursor_after, status, attempt_count,
                      started_at, completed_at, heartbeat_at, metrics
                    )
                    values (
                      %s::uuid, %s, %s, 'not-applicable',
                      %s::jsonb, %s::jsonb, 'succeeded', 1,
                      %s::timestamptz, %s::timestamptz, %s::timestamptz,
                      %s::jsonb
                    )
                    on conflict (idempotency_key) do nothing
                    returning id::text as id
                    """,
                    (
                        endpoint_id,
                        run_idempotency_key,
                        collector_version,
                        self._json({"resource": snapshot.resource}),
                        self._json({"resource": snapshot.resource}),
                        snapshot.fetched_at,
                        snapshot.fetched_at,
                        snapshot.fetched_at,
                        self._json(
                            {
                                "resource": snapshot.resource,
                                "body_size_bytes": len(snapshot.body),
                            }
                        ),
                    ),
                ).fetchone()
                if run_row is not None:
                    run_id = str(run_row["id"])
                else:
                    existing_run = connection.execute(
                        """
                        select id::text as id from source.collection_runs
                        where idempotency_key = %s
                        """,
                        (run_idempotency_key,),
                    ).fetchone()
                    if existing_run is None:
                        raise PersistenceContractError(
                            "Conflito de idempotência no snapshot PNCP."
                        )
                    run_id = str(existing_run["id"])

                artifact_row = connection.execute(
                    """
                    insert into raw.raw_artifacts (
                      collection_run_id, source_endpoint_id,
                      idempotency_key, artifact_kind, source_url,
                      retrieved_at, http_status, content_type, byte_size,
                      sha256, object_key, collector_version, metadata
                    )
                    values (
                      %s::uuid, %s::uuid, %s, 'http_response', %s,
                      %s::timestamptz, %s, %s, %s, %s, %s, %s, %s::jsonb
                    )
                    on conflict (idempotency_key) do nothing
                    returning id::text as id
                    """,
                    (
                        run_id,
                        endpoint_id,
                        artifact_idempotency_key,
                        snapshot.url,
                        snapshot.fetched_at,
                        snapshot.http_status,
                        snapshot.media_type,
                        len(snapshot.body),
                        snapshot.body_sha256,
                        object_key,
                        collector_version,
                        self._json(
                            {
                                "schema_name": "pncp-registry-snapshot",
                                "schema_version": "1.0.0",
                                "resource": snapshot.resource,
                                "cnpj": "13654405000195",
                                "final_url": snapshot.final_url,
                            }
                        ),
                    ),
                ).fetchone()
                if artifact_row is not None:
                    return RepositoryDirectEditionResult(
                        collection_run_id=run_id,
                        raw_artifact_id=str(artifact_row["id"]),
                        created=True,
                    )
                existing = connection.execute(
                    """
                    select id::text as id, sha256, object_key
                    from raw.raw_artifacts
                    where idempotency_key = %s
                    """,
                    (artifact_idempotency_key,),
                ).fetchone()
                if (
                    existing is None
                    or str(existing["sha256"]) != snapshot.body_sha256
                    or str(existing["object_key"]) != object_key
                ):
                    raise PersistenceContractError(
                        "Conflito de idempotência no artefato PNCP."
                    )
                return RepositoryDirectEditionResult(
                    collection_run_id=run_id,
                    raw_artifact_id=str(existing["id"]),
                    created=False,
                )
        finally:
            connection.close()

    def persist_document(self, batch: DocumentBatch) -> RepositoryDocumentResult:
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '15s'")
                connection.execute("set local lock_timeout = '5s'")
                endpoint_id = self._endpoint_id(
                    connection,
                    batch.source_code,
                    batch.endpoint_code,
                )
                return self._document_artifact(connection, batch, endpoint_id)
        finally:
            connection.close()

    def municipal_document_identities(
        self,
        source_record_keys: tuple[str, ...],
    ) -> frozenset[tuple[str, str]]:
        if not source_record_keys:
            return frozenset()
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                select distinct
                  artifact.metadata ->> 'source_record_key' as source_record_key,
                  artifact.source_url
                from raw.raw_artifacts as artifact
                where artifact.artifact_kind = 'document'
                  and artifact.metadata ->> 'schema_name' =
                    'municipal-transparency-document'
                  and artifact.metadata ->> 'source_record_key' = any(%s)
                """,
                (list(source_record_keys),),
            ).fetchall()
            return frozenset(
                (str(row["source_record_key"]), str(row["source_url"])) for row in rows
            )
        finally:
            connection.close()

    @classmethod
    def _document_artifact(
        cls,
        connection: DatabaseConnection,
        batch: DocumentBatch,
        endpoint_id: str,
    ) -> RepositoryDocumentResult:
        document = batch.document
        metadata = {
            "schema_name": batch.document_schema_name,
            "schema_version": "1.0.0",
            "source_record_key": batch.source_record_key,
            "document_role": document.role,
            "final_url": document.final_url,
        }
        row = connection.execute(
            """
            insert into raw.raw_artifacts (
              collection_run_id,
              source_endpoint_id,
              parent_artifact_id,
              idempotency_key,
              artifact_kind,
              source_url,
              retrieved_at,
              source_etag,
              http_status,
              content_type,
              byte_size,
              sha256,
              object_key,
              collector_version,
              response_headers,
              metadata
            )
            values (
              %s::uuid, %s::uuid,
              %s::uuid, %s, 'document', %s, %s::timestamptz,
              %s, %s, %s, %s, %s, %s, %s,
              %s::jsonb, %s::jsonb
            )
            on conflict (idempotency_key) do nothing
            returning id::text as id
            """,
            (
                batch.collection_run_id,
                endpoint_id,
                batch.parent_artifact_id,
                batch.idempotency_key,
                document.source_url,
                document.received_at,
                dict(document.response_headers).get("etag"),
                document.http_status,
                document.media_type,
                document.body_size_bytes,
                document.body_sha256,
                batch.object_key,
                batch.collector_version,
                cls._json(dict(document.response_headers)),
                cls._json(metadata),
            ),
        ).fetchone()
        if row is not None:
            return RepositoryDocumentResult(
                raw_artifact_id=str(row["id"]),
                created=True,
            )

        existing = connection.execute(
            """
            select
              id::text as id,
              parent_artifact_id::text as parent_artifact_id,
              sha256,
              byte_size,
              object_key
            from raw.raw_artifacts
            where idempotency_key = %s
            """,
            (batch.idempotency_key,),
        ).fetchone()
        # O documento é identificado pelo conteúdo e pela chave idempotente.
        # O artefato pai é a resposta bruta da API e pode mudar quando a mesma
        # fonte é coletada com outro tamanho de página; isso não torna o PDF
        # divergente nem deve bloquear uma recoleção legítima.
        expected = (
            document.body_sha256,
            document.body_size_bytes,
            batch.object_key,
        )
        actual = (
            str(existing["sha256"]) if existing else None,
            int(existing["byte_size"]) if existing else None,
            str(existing["object_key"]) if existing else None,
        )
        if existing is None or actual != expected:
            raise PersistenceContractError(
                "Conflito de idempotência no artefato de documento."
            )
        return RepositoryDocumentResult(
            raw_artifact_id=str(existing["id"]),
            created=False,
        )

    @staticmethod
    def _endpoint_id(
        connection: DatabaseConnection,
        source_code: str,
        endpoint_code: str,
    ) -> str:
        row = connection.execute(
            """
            select endpoint.id::text as id
            from source.source_endpoints as endpoint
            join source.data_sources as source
              on source.id = endpoint.data_source_id
            where source.slug = %s
              and endpoint.slug = %s
              and source.status = 'active'
              and endpoint.enabled
            """,
            (source_code, endpoint_code),
        ).fetchone()
        if row is None:
            raise PersistenceContractError(
                "Fonte ou endpoint não está cadastrado e habilitado."
            )
        return str(row["id"])

    @classmethod
    def _collection_run_id(
        cls,
        connection: DatabaseConnection,
        batch: PersistenceBatch,
        endpoint_id: str,
    ) -> str:
        cursor_after = dict(batch.page.cursor)
        cursor_offset = cursor_after.get("offset")
        if isinstance(cursor_offset, int) and not isinstance(cursor_offset, bool):
            cursor_after["offset"] = cursor_offset + len(batch.records)
        metrics = {
            "pages": 1,
            "records": len(batch.records),
            "body_size_bytes": batch.page.body_size_bytes,
            "http_status": batch.page.http_status,
            "collection_status": batch.page.collection_status,
        }
        row = connection.execute(
            """
            insert into source.collection_runs (
              source_endpoint_id,
              idempotency_key,
              collector_version,
              parser_version,
              collection_window_start,
              collection_window_end,
              cursor_before,
              cursor_after,
              status,
              attempt_count,
              started_at,
              completed_at,
              heartbeat_at,
              metrics
            )
            values (
              %s::uuid, %s, %s, %s, %s::timestamptz, %s::timestamptz,
              %s::jsonb, %s::jsonb, 'succeeded',
              %s, %s::timestamptz, %s::timestamptz, %s::timestamptz, %s::jsonb
            )
            on conflict (idempotency_key) do nothing
            returning id::text as id
            """,
            (
                endpoint_id,
                batch.page.idempotency_key,
                batch.collector_version,
                batch.parser_version,
                batch.page.window_start,
                batch.page.window_end,
                cls._json(batch.page.cursor),
                cls._json(cursor_after),
                batch.page.attempts,
                batch.page.requested_at,
                batch.page.received_at,
                batch.page.received_at,
                cls._json(metrics),
            ),
        ).fetchone()
        if row is not None:
            return str(row["id"])

        existing = connection.execute(
            """
            select id::text as id, source_endpoint_id::text as endpoint_id
            from source.collection_runs
            where idempotency_key = %s
            """,
            (batch.page.idempotency_key,),
        ).fetchone()
        if existing is None or str(existing["endpoint_id"]) != endpoint_id:
            raise PersistenceContractError(
                "Conflito de idempotência na execução de coleta."
            )
        return str(existing["id"])

    @classmethod
    def _artifact_id(
        cls,
        connection: DatabaseConnection,
        batch: PersistenceBatch,
        endpoint_id: str,
        run_id: str,
    ) -> str:
        headers = batch.page.response_headers
        artifact_kind = getattr(batch.page, "artifact_kind", "http_response")
        if artifact_kind not in {"http_response", "archive", "document"}:
            raise PersistenceContractError("Tipo de artefato bruto não permitido.")
        metadata = {
            "schema_name": batch.page.schema_name,
            "schema_version": batch.page.schema_version,
            "request_url": batch.page.request_url,
            "final_url": batch.page.final_url,
            "cursor": batch.page.cursor,
        }
        if artifact_kind == "archive":
            metadata.update(
                {
                    "catalog_blob_url": getattr(batch.page, "catalog_blob_url", None),
                    "catalog_etag": getattr(batch.page, "catalog_etag", None),
                    "catalog_last_modified": getattr(
                        batch.page, "catalog_last_modified", None
                    ),
                }
            )
        elif artifact_kind == "document":
            metadata.update(
                {
                    "fiscal_year": getattr(batch.page, "fiscal_year", None),
                    "annex_code": getattr(batch.page, "annex_code", None),
                    "budget_stage": (
                        batch.page.items[0].get("budget_stage")
                        if batch.page.items
                        else None
                    ),
                    "territorial_scope": (
                        batch.page.items[0].get("territorial_scope")
                        if batch.page.items
                        else None
                    ),
                }
            )
        row = connection.execute(
            """
            insert into raw.raw_artifacts (
              collection_run_id,
              source_endpoint_id,
              idempotency_key,
              artifact_kind,
              source_url,
              retrieved_at,
              source_etag,
              http_status,
              content_type,
              byte_size,
              sha256,
              object_key,
              collector_version,
              parser_version,
              response_headers,
              metadata
            )
            values (
              %s::uuid, %s::uuid, %s, %s, %s, %s::timestamptz,
              %s, %s, %s, %s, %s, %s, %s, 'not-applicable',
              %s::jsonb, %s::jsonb
            )
            on conflict (idempotency_key) do nothing
            returning id::text as id
            """,
            (
                run_id,
                endpoint_id,
                batch.artifact_idempotency_key,
                artifact_kind,
                batch.page.final_url,
                batch.page.received_at,
                headers.get("etag"),
                batch.page.http_status,
                batch.page.media_type,
                batch.page.body_size_bytes,
                batch.page.body_sha256,
                batch.object_key,
                batch.collector_version,
                cls._json(headers),
                cls._json(metadata),
            ),
        ).fetchone()
        if row is not None:
            return str(row["id"])

        existing = connection.execute(
            """
            select
              id::text as id,
              collection_run_id::text as collection_run_id,
              sha256,
              byte_size,
              object_key
            from raw.raw_artifacts
            where idempotency_key = %s
            """,
            (batch.artifact_idempotency_key,),
        ).fetchone()
        expected = (
            run_id,
            batch.page.body_sha256,
            batch.page.body_size_bytes,
            batch.object_key,
        )
        actual = (
            str(existing["collection_run_id"]) if existing else None,
            str(existing["sha256"]) if existing else None,
            int(existing["byte_size"]) if existing else None,
            str(existing["object_key"]) if existing else None,
        )
        if existing is None or actual != expected:
            raise PersistenceContractError(
                "Conflito de idempotência no artefato bruto."
            )
        return str(existing["id"])

    @classmethod
    def _records(
        cls,
        connection: DatabaseConnection,
        batch: PersistenceBatch,
        artifact_id: str,
    ) -> tuple[int, int]:
        if not batch.records:
            return 0, 0

        serialized_records = cls._json(
            [
                {
                    "source_record_key": record.source_record_key,
                    "record_type": record.record_type,
                    "record_index": record.record_index,
                    "payload": record.payload,
                    "payload_sha256": record.payload_sha256,
                    "parser_version": record.parser_version,
                    "idempotency_key": record.idempotency_key,
                    "collected_at": batch.page.received_at,
                }
                for record in batch.records
            ]
        )
        row = connection.execute(
            """
            with incoming as materialized (
              select *
              from jsonb_to_recordset(%s::jsonb) as item (
                source_record_key text,
                record_type text,
                record_index integer,
                payload jsonb,
                payload_sha256 text,
                parser_version text,
                idempotency_key text,
                collected_at timestamptz
              )
            ),
            prior as materialized (
              select
                item.idempotency_key,
                record.source_record_key,
                record.record_type,
                record.payload_sha256,
                record.parser_version,
                artifact.sha256 as artifact_sha256
              from incoming as item
              join raw.raw_records as record
                on record.idempotency_key = item.idempotency_key
              join raw.raw_artifacts as artifact
                on artifact.id = record.raw_artifact_id
            ),
            inserted as (
              insert into raw.raw_records (
                raw_artifact_id,
                source_record_key,
                record_type,
                record_index,
                payload,
                payload_sha256,
                parser_version,
                idempotency_key,
                collected_at
              )
              select
                %s::uuid,
                item.source_record_key,
                item.record_type,
                item.record_index,
                item.payload,
                item.payload_sha256,
                item.parser_version,
                item.idempotency_key,
                item.collected_at
              from incoming as item
              on conflict (idempotency_key) do nothing
              returning idempotency_key
            )
            select
              (select count(*) from inserted)::integer as inserted_records,
              (
                (select count(*) from incoming)
                - (select count(*) from inserted)
              )::integer as existing_records,
              (
                select count(*)
                from prior
                join incoming as item using (idempotency_key)
                where prior.artifact_sha256 is distinct from %s
                   or prior.source_record_key is distinct from item.source_record_key
                   or prior.record_type is distinct from item.record_type
                   or prior.payload_sha256 is distinct from item.payload_sha256
                   or prior.parser_version is distinct from item.parser_version
              )::integer as conflicting_records
            """,
            (serialized_records, artifact_id, batch.page.body_sha256),
        ).fetchone()
        if row is None:
            raise PersistenceContractError(
                "A persistência em lote não retornou o balanço de registros."
            )
        if int(row["conflicting_records"]) > 0:
            raise PersistenceContractError(
                "Conflito de idempotência em registro bruto."
            )
        return int(row["inserted_records"]), int(row["existing_records"])

    @staticmethod
    def _json(value: object) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
