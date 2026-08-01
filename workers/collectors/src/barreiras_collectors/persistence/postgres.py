"""Registro transacional no PostgreSQL sem chamadas externas na transação."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from .models import (
    DirectEditionBatch,
    DocumentBatch,
    PersistenceBatch,
    PersistenceContractError,
    RepositoryDirectEditionResult,
    RepositoryDocumentResult,
    RepositoryPersistResult,
)


class QueryResult(Protocol):
    def fetchone(self) -> Mapping[str, Any] | None: ...


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


class PostgresCollectionRepository:
    """Persiste execução, observação bruta e registros com UPSERT atômico."""

    def __init__(self, connection_factory: Callable[[], DatabaseConnection]) -> None:
        self.connection_factory = connection_factory

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

    @classmethod
    def _document_artifact(
        cls,
        connection: DatabaseConnection,
        batch: DocumentBatch,
        endpoint_id: str,
    ) -> RepositoryDocumentResult:
        document = batch.document
        metadata = {
            "schema_name": "gazette-document",
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
        expected = (
            batch.parent_artifact_id,
            document.body_sha256,
            document.body_size_bytes,
            batch.object_key,
        )
        actual = (
            str(existing["parent_artifact_id"]) if existing else None,
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
        metadata = {
            "schema_name": batch.page.schema_name,
            "schema_version": batch.page.schema_version,
            "request_url": batch.page.request_url,
            "final_url": batch.page.final_url,
            "cursor": batch.page.cursor,
        }
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
              %s::uuid, %s::uuid, %s, 'http_response', %s, %s::timestamptz,
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
                  raw_artifact_id::text as raw_artifact_id,
                  record_index,
                  payload_sha256,
                  parser_version
                from raw.raw_records
                where idempotency_key = %s
                """,
                (record.idempotency_key,),
            ).fetchone()
            expected = (
                artifact_id,
                record.record_index,
                record.payload_sha256,
                record.parser_version,
            )
            actual = (
                str(prior["raw_artifact_id"]) if prior else None,
                int(prior["record_index"]) if prior else None,
                str(prior["payload_sha256"]) if prior else None,
                str(prior["parser_version"]) if prior else None,
            )
            if prior is None or actual != expected:
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
