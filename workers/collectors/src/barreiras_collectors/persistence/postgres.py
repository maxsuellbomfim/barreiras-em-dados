"""Registro transacional no PostgreSQL sem chamadas externas na transação."""

from __future__ import annotations

import hashlib
import json
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
                    returning source_endpoint_id::text as endpoint_id
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
                (str(row["source_record_key"]), str(row["source_url"]))
                for row in rows
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
        cursor_after = {
            "offset": batch.page.cursor["offset"] + len(batch.records),
            "size": batch.page.cursor["size"],
        }
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
                    "catalog_blob_url": getattr(
                        batch.page, "catalog_blob_url", None
                    ),
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
        inserted = 0
        existing = 0
        for record in batch.records:
            row = connection.execute(
                """
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
                values (
                  %s::uuid, %s, %s, %s, %s::jsonb, %s, %s, %s, %s::timestamptz
                )
                on conflict (idempotency_key) do nothing
                returning id::text as id
                """,
                (
                    artifact_id,
                    record.source_record_key,
                    record.record_type,
                    record.record_index,
                    cls._json(record.payload),
                    record.payload_sha256,
                    record.parser_version,
                    record.idempotency_key,
                    batch.page.received_at,
                ),
            ).fetchone()
            if row is not None:
                inserted += 1
                continue

            prior = connection.execute(
                """
                select
                  record.source_record_key,
                  record.record_type,
                  record.payload_sha256,
                  record.parser_version,
                  artifact.sha256 as artifact_sha256
                from raw.raw_records as record
                join raw.raw_artifacts as artifact
                  on artifact.id = record.raw_artifact_id
                where record.idempotency_key = %s
                """,
                (record.idempotency_key,),
            ).fetchone()
            if not _compatible_existing_record(
                prior,
                artifact_sha256=batch.page.body_sha256,
                source_record_key=record.source_record_key,
                record_type=record.record_type,
                payload_sha256=record.payload_sha256,
                parser_version=record.parser_version,
            ):
                raise PersistenceContractError(
                    "Conflito de idempotência em registro bruto."
                )
            existing += 1
        return inserted, existing

    @staticmethod
    def _json(value: object) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
