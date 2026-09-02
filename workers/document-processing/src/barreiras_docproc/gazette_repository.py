"""Persistência isolada e append-only dos documentos integrais do Diário."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .gazette_documents import DocumentBlock, GazetteDocumentDraft, block_sha256
from .processing import PageInput, ProcessingError


@dataclass(frozen=True)
class GazetteArtifact:
    raw_artifact_id: str
    sha256: str
    edition: int
    edition_year: int
    edition_date: str | None
    created_at: str


@dataclass(frozen=True)
class GazetteDocumentBatch:
    artifact: GazetteArtifact
    pages: tuple[PageInput, ...]
    blocks: tuple[DocumentBlock, ...]
    documents: tuple[GazetteDocumentDraft, ...]
    idempotency_key: str
    segmenter_version: str
    validator_version: str


@dataclass(frozen=True)
class PersistResult:
    created: bool
    documents_inserted: int


class GazetteDocumentRepository:
    """Acesso SQL específico do fluxo integral; não amplia ``postgres.py``."""

    def __init__(self, connection_factory: Callable[[], object]) -> None:
        self.connection_factory = connection_factory

    @classmethod
    def from_dsn(cls, database_url: str) -> GazetteDocumentRepository:
        from psycopg import connect
        from psycopg.rows import dict_row

        return cls(lambda: connect(database_url, row_factory=dict_row))

    def pending_artifacts(
        self,
        limit: int,
        *,
        edition: int | None = None,
        edition_year: int | None = None,
    ) -> Sequence[GazetteArtifact]:
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                with candidate_editions as (
                  select
                    artifact.id,
                    artifact.sha256,
                    artifact.created_at,
                    (artifact.metadata ->> 'edition')::integer as edition,
                    coalesce(
                      (artifact.metadata ->> 'year')::integer,
                      extract(year from (artifact.metadata ->> 'date')::date)::integer
                    ) as edition_year,
                    coalesce(
                      (artifact.metadata ->> 'date')::date,
                      (artifact.metadata ->> 'edition_date')::date
                    ) as edition_date,
                    0 as source_priority
                  from raw.raw_artifacts as artifact
                  where artifact.metadata ->> 'schema_name' = 'gazette-direct-edition'
                    and coalesce(artifact.metadata ->> 'edition', '') ~ '^[0-9]+$'
                    and coalesce(artifact.metadata ->> 'year', '') ~ '^[0-9]{4}$'
                  union all
                  select
                    artifact.id,
                    artifact.sha256,
                    artifact.created_at,
                    (record.payload ->> 'edition')::integer as edition,
                    extract(year from (record.payload ->> 'date')::date)::integer
                      as edition_year,
                    (record.payload ->> 'date')::date as edition_date,
                    1 as source_priority
                  from raw.raw_artifacts as artifact
                  join lateral (
                    select record.payload, record.collected_at
                    from raw.raw_records as record
                    where record.record_type = 'querido_diario_gazette'
                      and record.source_record_key
                        = artifact.metadata ->> 'source_record_key'
                      and record.payload ->> 'edition' ~ '^[0-9]+$'
                      and record.payload ->> 'date' ~ '^\\d{4}-\\d{2}-\\d{2}$'
                    order by record.collected_at desc, record.id desc
                    limit 1
                  ) as record on true
                  where artifact.metadata ->> 'document_role' = 'txt'
                    and artifact.metadata ? 'source_record_key'
                ), selected_editions as (
                select
                  edition.id::text as id,
                  edition.sha256,
                  edition.edition,
                  edition.edition_year,
                  edition.edition_date,
                  edition.source_priority,
                  edition.created_at::text as created_at
                from candidate_editions as edition
                join raw.document_pages as page
                  on page.raw_artifact_id = edition.id
                where (%s::integer is null or edition.edition = %s::integer)
                  and (%s::integer is null or edition.edition_year = %s::integer)
                  and (
                    (%s::integer is not null and %s::integer is not null)
                    or not exists (
                      select 1
                      from editorial.gazette_document_versions as version
                      where version.raw_artifact_id = edition.id
                    )
                  )
                group by edition.id, edition.sha256, edition.edition,
                  edition.edition_year, edition.edition_date, edition.created_at,
                  edition.source_priority
                having min(page.page_number) = 1
                  and count(distinct page.page_number)
                    filter (where page.text_content is not null)
                    = max(page.page_number)
                order by edition.edition_year desc, edition.edition desc,
                  edition.source_priority asc, edition.created_at desc
                limit %s
                )
                select
                  edition.id,
                  edition.sha256,
                  edition.edition,
                  edition.edition_year,
                  coalesce(edition.edition_date, publication.edition_date)
                    as edition_date,
                  edition.created_at
                from selected_editions as edition
                left join lateral (
                  select (record.payload ->> 'date')::date as edition_date
                  from raw.raw_records as record
                  where edition.edition_date is null
                    and record.record_type = 'barreiras_diario_publication'
                    and record.payload ->> 'edition' = edition.edition::text
                    and record.payload ->> 'date' ~ '^\\d{4}-\\d{2}-\\d{2}$'
                    and extract(year from (record.payload ->> 'date')::date)::integer
                      = edition.edition_year
                  order by record.collected_at desc
                  limit 1
                ) as publication on true
                order by edition.edition_year desc, edition.edition desc,
                  edition.source_priority asc, edition.created_at desc
                """,
                (
                    edition,
                    edition,
                    edition_year,
                    edition_year,
                    edition,
                    edition_year,
                    limit,
                ),
            )
            found = []
            while (row := rows.fetchone()) is not None:
                found.append(
                    GazetteArtifact(
                        raw_artifact_id=str(row["id"]),
                        sha256=str(row["sha256"]),
                        edition=int(row["edition"]),
                        edition_year=int(row["edition_year"]),
                        edition_date=(
                            str(row["edition_date"])
                            if row["edition_date"] is not None
                            else None
                        ),
                        created_at=str(row["created_at"]),
                    )
                )
            return tuple(found)
        finally:
            connection.close()

    def batch_exists(self, artifact_id: str, idempotency_key: str) -> bool:
        connection = self.connection_factory()
        try:
            row = connection.execute(
                """
                select 1 as ok
                from editorial.gazette_document_versions
                where raw_artifact_id = %s::uuid
                  and batch_idempotency_key = %s
                limit 1
                """,
                (artifact_id, idempotency_key),
            ).fetchone()
            return row is not None
        finally:
            connection.close()

    def page_inputs(self, artifact_id: str) -> Sequence[PageInput]:
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                select distinct on (page.page_number)
                  page.page_number,
                  page.parser_version,
                  page.text_content,
                  page.text_sha256,
                  page.extraction_method
                from raw.document_pages as page
                where page.raw_artifact_id = %s::uuid
                  and page.text_content is not null
                order by page.page_number,
                  case when page.extraction_method = 'ocr' then 0 else 1 end,
                  page.created_at desc
                """,
                (artifact_id,),
            )
            return tuple(
                PageInput(
                    page_number=int(row["page_number"]),
                    parser_version=str(row["parser_version"]),
                    text=str(row["text_content"]),
                    sha256=(str(row["text_sha256"]) if row["text_sha256"] else None),
                    extraction_method=str(row["extraction_method"]),
                )
                for row in iter(rows.fetchone, None)
            )
        finally:
            connection.close()

    def persist_version(self, batch: GazetteDocumentBatch) -> PersistResult:
        if not batch.blocks or not batch.documents:
            raise ProcessingError("Lote documental sem blocos ou documentos.")
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '15s'")
                connection.execute("set local lock_timeout = '5s'")
                existing = connection.execute(
                    """
                    select 1 from editorial.gazette_document_versions
                    where raw_artifact_id = %s::uuid
                      and batch_idempotency_key = %s
                    limit 1
                    """,
                    (batch.artifact.raw_artifact_id, batch.idempotency_key),
                ).fetchone()
                if existing is not None:
                    return PersistResult(created=False, documents_inserted=0)

                pages_by_number = {page.page_number: page for page in batch.pages}
                block_ids: list[str] = []
                for block in batch.blocks:
                    page = pages_by_number.get(block.page_number)
                    if page is None:
                        raise ProcessingError("Bloco sem página de origem no lote.")
                    inserted = connection.execute(
                        """
                        with source_page as (
                          select id
                          from raw.document_pages
                          where raw_artifact_id = %s::uuid
                            and page_number = %s
                            and parser_version = %s
                        )
                        insert into raw.document_blocks (
                          document_page_id, block_order, text_content, text_sha256,
                          bbox, extraction_method, extractor_version
                        )
                        select id, %s, %s, %s, %s::jsonb, %s, %s
                        from source_page
                        on conflict (document_page_id, block_order, extractor_version)
                          do nothing
                        returning id::text as id
                        """,
                        (
                            batch.artifact.raw_artifact_id,
                            page.page_number,
                            page.parser_version,
                            block.block_order,
                            block.text,
                            block.sha256,
                            None,
                            page.extraction_method,
                            page.parser_version,
                        ),
                    ).fetchone()
                    if inserted is None:
                        existing_block = connection.execute(
                            """
                            select block.id::text as id, block.text_sha256
                            from raw.document_blocks as block
                            join raw.document_pages as page
                              on page.id = block.document_page_id
                            where page.raw_artifact_id = %s::uuid
                              and page.page_number = %s
                              and block.block_order = %s
                              and block.extractor_version = %s
                            """,
                            (
                                batch.artifact.raw_artifact_id,
                                block.page_number,
                                block.block_order,
                                page.parser_version,
                            ),
                        ).fetchone()
                        if (
                            existing_block is None
                            or str(existing_block["text_sha256"]) != block.sha256
                        ):
                            raise ProcessingError(
                                "Bloco existente diverge do texto literal."
                            )
                        block_ids.append(str(existing_block["id"]))
                    else:
                        block_ids.append(str(inserted["id"]))

                inserted_documents = 0
                for document_order, document in enumerate(batch.documents, start=1):
                    try:
                        first_block_id = block_ids[document.first_block]
                        last_block_id = block_ids[document.last_block]
                    except IndexError as error:
                        raise ProcessingError(
                            "Documento aponta para bloco inexistente."
                        ) from error
                    previous = connection.execute(
                        """
                        select version.id::text as id
                        from editorial.gazette_document_versions as version
                        where version.edition = %s
                          and version.edition_year = %s
                          and version.document_order = %s
                          and version.publication_status in (
                            'validated', 'edition_fallback'
                          )
                          and not exists (
                            select 1
                            from editorial.gazette_document_versions as successor
                            where successor.supersedes_id = version.id
                          )
                        order by version.created_at desc
                        limit 1
                        """,
                        (
                            batch.artifact.edition,
                            batch.artifact.edition_year,
                            document_order,
                        ),
                    ).fetchone()
                    document_key = hashlib.sha256(
                        f"{batch.idempotency_key}:{document_order}".encode()
                    ).hexdigest()
                    created = connection.execute(
                        """
                        insert into editorial.gazette_document_versions (
                          supersedes_id, raw_artifact_id, edition, edition_year,
                          edition_date, document_order, first_block_id, last_block_id,
                          page_start, page_end,
                          literal_title, document_type, full_text, text_sha256,
                          publication_status, segmenter_version, validator_version,
                          batch_idempotency_key, idempotency_key, published_at
                        ) values (
                          %s::uuid, %s::uuid, %s, %s, %s::date,
                          %s, %s::uuid, %s::uuid, %s, %s,
                          %s, %s, %s, %s,
                          %s, %s, %s, %s, %s, statement_timestamp()
                        ) on conflict (idempotency_key) do nothing
                        returning id::text as id
                        """,
                        (
                            str(previous["id"]) if previous else None,
                            batch.artifact.raw_artifact_id,
                            batch.artifact.edition,
                            batch.artifact.edition_year,
                            batch.artifact.edition_date,
                            document_order,
                            first_block_id,
                            last_block_id,
                            document.page_start,
                            document.page_end,
                            document.literal_title,
                            document.document_type,
                            document.full_text,
                            block_sha256(document.full_text),
                            document.status,
                            batch.segmenter_version,
                            batch.validator_version,
                            batch.idempotency_key,
                            document_key,
                        ),
                    ).fetchone()
                    if created is not None:
                        linked_blocks = block_ids[
                            document.first_block : document.last_block + 1
                        ]
                        if not linked_blocks:
                            raise ProcessingError("Documento sem blocos literais.")
                        connection.execute(
                            """
                            insert into editorial.gazette_document_version_blocks (
                              version_id, block_id, sequence_order
                            )
                            select %s::uuid, link.block_id, link.sequence_order
                            from unnest(%s::uuid[], %s::integer[])
                              as link(block_id, sequence_order)
                            """,
                            (
                                str(created["id"]),
                                linked_blocks,
                                list(range(len(linked_blocks))),
                            ),
                        )
                        inserted_documents += 1
                return PersistResult(
                    created=True,
                    documents_inserted=inserted_documents,
                )
        finally:
            connection.close()

    def record_failure(self, artifact_id: str, code: str, detail: str) -> None:
        """Registra código sanitizado, sem texto de PDF ou exceção bruta."""
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute(
                    """
                    insert into raw.extraction_jobs (
                      raw_artifact_id, job_type, idempotency_key, status,
                      attempt_count, last_error_code, last_error_detail
                    ) values (
                      %s::uuid, 'integral_gazette_documents', %s, 'failed',
                      1, %s, %s
                    )
                    on conflict (idempotency_key) do update set
                      status = 'failed',
                      attempt_count = raw.extraction_jobs.attempt_count + 1,
                      last_error_code = excluded.last_error_code,
                      last_error_detail = excluded.last_error_detail,
                      updated_at = statement_timestamp()
                    """,
                    (
                        artifact_id,
                        f"integral-gazette-failure:{artifact_id}",
                        code[:80],
                        detail[:300],
                    ),
                )
        finally:
            connection.close()
