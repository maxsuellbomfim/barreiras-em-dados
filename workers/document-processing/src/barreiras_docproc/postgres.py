"""Registro transacional de página canônica, job e candidatos."""

from __future__ import annotations

import json
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
                  -- Adiado aguardando OCR: alguma página sem texto e ainda
                  -- sem linha OCR equivalente para o mesmo número de página.
                  and not exists (
                    select 1
                    from raw.document_pages as page
                    where page.raw_artifact_id = artifact.id
                      and page.text_content is null
                      and not exists (
                        select 1
                        from raw.document_pages as supplemental
                        where supplemental.raw_artifact_id = artifact.id
                          and supplemental.page_number = page.page_number
                          and supplemental.text_content is not null
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

    def pending_enrichment_candidates(
        self,
        limit: int,
    ) -> tuple[dict, ...]:
        """Candidatos pendentes sem decisão e ainda sem sugestão assistida."""
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                select
                  result.id::text as result_id,
                  result.extraction_job_id::text as job_id,
                  result.candidate_type,
                  result.result_payload
                from raw.extraction_results as result
                where result.validation_status = 'needs_review'
                  and result.candidate_type in ('nomeacao', 'exoneracao')
                  -- Não gastar IA com candidato de régua aposentada.
                  and result.extractor_version = %s
                  and not exists (
                    select 1
                    from editorial.editorial_reviews as review
                    where review.target_type = 'raw.extraction_results'
                      and review.target_id = result.id
                      and review.decision in ('approved', 'rejected')
                  )
                  and not exists (
                    select 1
                    from raw.extraction_results as enrichment
                    where enrichment.supersedes_id = result.id
                      and enrichment.candidate_type = 'assisted_enrichment'
                  )
                order by result.created_at
                limit %s
                """,
                (self._ruleset_version(), limit),
            )
            found = []
            while True:
                row = rows.fetchone()
                if row is None:
                    break
                payload = row["result_payload"]
                found.append(
                    {
                        "result_id": str(row["result_id"]),
                        "job_id": str(row["job_id"]),
                        "candidate_type": str(row["candidate_type"]),
                        "payload": (
                            payload
                            if isinstance(payload, dict)
                            else json.loads(str(payload))
                        ),
                    }
                )
            return tuple(found)
        finally:
            connection.close()

    def persist_enrichment(
        self,
        *,
        source_result_id: str,
        extraction_job_id: str,
        extractor_version: str,
        payload: dict,
    ) -> None:
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '15s'")
                connection.execute("set local lock_timeout = '5s'")
                connection.execute(
                    """
                    insert into raw.extraction_results (
                      extraction_job_id,
                      supersedes_id,
                      candidate_type,
                      extractor_version,
                      validator_version,
                      result_payload,
                      confidence,
                      validation_status
                    )
                    values (
                      %s::uuid, %s::uuid, 'assisted_enrichment', %s,
                      'human-review-pending/1.0.0', %s::jsonb, null,
                      'needs_review'
                    )
                    """,
                    (
                        extraction_job_id,
                        source_result_id,
                        extractor_version,
                        canonical_json(payload),
                    ),
                )
        finally:
            connection.close()

    def publishable_candidates(self, limit: int) -> tuple[dict, ...]:
        """Candidatos pendentes com sua sugestão assistida mais recente."""
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                select
                  result.id::text as result_id,
                  result.candidate_type,
                  result.result_payload,
                  enrichment.result_payload as assisted_payload
                from raw.extraction_results as result
                left join lateral (
                  select inner_enrichment.result_payload
                  from raw.extraction_results as inner_enrichment
                  where inner_enrichment.supersedes_id = result.id
                    and inner_enrichment.candidate_type
                        = 'assisted_enrichment'
                  order by
                    inner_enrichment.created_at desc,
                    inner_enrichment.id desc
                  limit 1
                ) as enrichment on true
                where result.validation_status = 'needs_review'
                  and result.candidate_type in ('nomeacao', 'exoneracao')
                  -- Só a régua vigente publica: candidato de versão antiga
                  -- carrega os defeitos que a versão nova corrigiu.
                  and result.extractor_version = %s
                  and not exists (
                    select 1
                    from editorial.editorial_reviews as review
                    where review.target_type = 'raw.extraction_results'
                      and review.target_id = result.id
                      and review.decision in ('approved', 'rejected')
                  )
                order by result.created_at
                limit %s
                """,
                (self._ruleset_version(), limit),
            )
            found = []
            while True:
                row = rows.fetchone()
                if row is None:
                    break
                payload = row["result_payload"]
                assisted = row["assisted_payload"]
                found.append(
                    {
                        "result_id": str(row["result_id"]),
                        "candidate_type": str(row["candidate_type"]),
                        "payload": (
                            payload
                            if isinstance(payload, dict)
                            else json.loads(str(payload))
                        ),
                        "assisted": (
                            assisted
                            if isinstance(assisted, dict) or assisted is None
                            else json.loads(str(assisted))
                        ),
                    }
                )
            return tuple(found)
        finally:
            connection.close()

    def pending_digest_artifacts(
        self,
        limit: int,
        prompt_idempotency: Callable[[str], str],
    ) -> tuple[dict, ...]:
        """Edições com texto (diretas e do QD) ainda sem resumo desta
        versão."""
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                select
                  editions.id::text as id,
                  editions.sha256,
                  editions.edition,
                  editions.year
                from (
                  select
                    artifact.id,
                    artifact.sha256,
                    artifact.created_at,
                    (artifact.metadata ->> 'edition')::int as edition,
                    (artifact.metadata ->> 'year')::int as year
                  from raw.raw_artifacts as artifact
                  where artifact.metadata ->> 'schema_name'
                      = 'gazette-direct-edition'
                  union all
                  select distinct on (artifact.id)
                    artifact.id,
                    artifact.sha256,
                    artifact.created_at,
                    (record.payload ->> 'edition')::int,
                    extract(
                      year from (record.payload ->> 'date')::date
                    )::int
                  from raw.raw_artifacts as artifact
                  join raw.raw_records as record
                    on record.record_type = 'querido_diario_gazette'
                   and record.source_record_key
                       = artifact.metadata ->> 'source_record_key'
                  where artifact.metadata ->> 'document_role' = 'txt'
                    and record.payload ->> 'edition' ~ '^[0-9]+$'
                    and record.payload ->> 'date'
                        ~ '^\\d{4}-\\d{2}-\\d{2}'
                  order by artifact.id, record.collected_at desc
                ) as editions
                where exists (
                  select 1
                  from raw.document_pages as page
                  where page.raw_artifact_id = editions.id
                    and page.text_content is not null
                )
                order by editions.created_at
                limit %s
                """,
                (limit * 4,),
            )
            found = []
            while True:
                row = rows.fetchone()
                if row is None:
                    break
                found.append(
                    {
                        "artifact_id": str(row["id"]),
                        "sha256": str(row["sha256"]),
                        "edition": int(row["edition"]),
                        "year": int(row["year"]),
                    }
                )
        finally:
            connection.close()

        # Filtra pelo job idempotente fora do SQL para reusar o mesmo hash
        # do código (uma consulta curta por artefato; volume municipal).
        pending = []
        for artifact in found:
            if len(pending) >= limit:
                break
            if not self._digest_job_exists(
                prompt_idempotency(artifact["sha256"])
            ):
                pending.append(artifact)
        return tuple(pending)

    def _digest_job_exists(self, idempotency_key: str) -> bool:
        connection = self.connection_factory()
        try:
            row = connection.execute(
                """
                select 1 as ok
                from raw.extraction_jobs as job
                where job.idempotency_key = %s
                """,
                (idempotency_key,),
            ).fetchone()
            return row is not None
        finally:
            connection.close()

    def edition_pages_text(self, artifact_id: str) -> str:
        """Texto canônico da edição na ordem das páginas (OCR incluído)."""
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                select distinct on (page.page_number)
                  page.page_number,
                  page.text_content
                from raw.document_pages as page
                where page.raw_artifact_id = %s::uuid
                  and page.text_content is not null
                order by page.page_number, page.created_at desc
                """,
                (artifact_id,),
            )
            pages = []
            while True:
                row = rows.fetchone()
                if row is None:
                    break
                pages.append(str(row["text_content"]))
            return "\n\n".join(pages)
        finally:
            connection.close()

    def persist_digest(
        self,
        *,
        artifact_id: str,
        job_idempotency_key: str,
        extractor_version: str,
        payload: dict,
    ) -> str | None:
        """Job + resultado do resumo em uma transação; None se já existia."""
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '15s'")
                connection.execute("set local lock_timeout = '5s'")
                job = connection.execute(
                    """
                    insert into raw.extraction_jobs (
                      raw_artifact_id,
                      job_type,
                      idempotency_key,
                      status,
                      attempt_count
                    )
                    values (%s::uuid, 'edition_digest', %s, 'succeeded', 1)
                    on conflict (idempotency_key) do nothing
                    returning id::text as id
                    """,
                    (artifact_id, job_idempotency_key),
                ).fetchone()
                if job is None:
                    return None
                result = connection.execute(
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
                      %s::uuid, 'edition_digest', %s,
                      'anchor-verified/1.0.0', %s::jsonb, null, 'needs_review'
                    )
                    returning id::text as id
                    """,
                    (
                        str(job["id"]),
                        extractor_version,
                        canonical_json(payload),
                    ),
                ).fetchone()
                if result is None:
                    raise ProcessingError(
                        "O resumo da edição não recebeu identificador."
                    )
                return str(result["id"])
        finally:
            connection.close()

    def record_assist_attempts(self, command: str, attempts) -> None:
        """Registra o desfecho de cada tentativa da cascata assistida.

        Sem isto, "nenhuma sugestão gerada" era indistinguível de "tudo
        certo" sem abrir o log do Actions.
        """
        if not attempts:
            return
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '15s'")
                for attempt in attempts:
                    connection.execute(
                        """
                        insert into audit.assist_diagnostics (
                          command, provider, model, outcome,
                          http_status, detail
                        )
                        values (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            command[:120],
                            attempt.provider[:60],
                            attempt.model,
                            attempt.outcome,
                            attempt.http_status,
                            (attempt.detail or None),
                        ),
                    )
        finally:
            connection.close()

    def automated_review_available(self) -> bool:
        """A migration da publicação automática já foi aplicada?"""
        connection = self.connection_factory()
        try:
            row = connection.execute(
                """
                select 1 as ok
                from pg_proc as proc
                join pg_namespace as namespace
                  on namespace.oid = proc.pronamespace
                where namespace.nspname = 'editorial'
                  and proc.proname = 'record_automated_review'
                """
            ).fetchone()
            return row is not None
        finally:
            connection.close()

    def record_automated_review(
        self,
        *,
        result_id: str,
        rationale: str,
        verification: dict,
    ) -> str:
        connection = self.connection_factory()
        try:
            row = connection.execute(
                """
                select editorial.record_automated_review(
                  %s::uuid, %s, %s::jsonb
                )::text as review_id
                """,
                (result_id, rationale, canonical_json(verification)),
            ).fetchone()
            if row is None:
                raise ProcessingError(
                    "A publicação automática não devolveu identificador."
                )
            return str(row["review_id"])
        finally:
            connection.close()

    def supplemental_page_texts(self, raw_artifact_id: str) -> dict[int, str]:
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                select page.page_number, page.text_content
                from raw.document_pages as page
                where page.raw_artifact_id = %s::uuid
                  and page.extraction_method = 'ocr'
                  and page.text_content is not null
                """,
                (raw_artifact_id,),
            )
            texts: dict[int, str] = {}
            while True:
                row = rows.fetchone()
                if row is None:
                    break
                texts[int(row["page_number"])] = str(row["text_content"])
            return texts
        finally:
            connection.close()

    def pending_ocr_pages(
        self,
        limit_pages: int,
    ) -> tuple[tuple[TextArtifact, tuple[int, ...]], ...]:
        """Páginas nulas ainda sem linha OCR, agrupadas por artefato."""
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                select
                  artifact.id::text as id,
                  artifact.sha256,
                  artifact.object_key,
                  page.page_number
                from raw.document_pages as page
                join raw.raw_artifacts as artifact
                  on artifact.id = page.raw_artifact_id
                where page.text_content is null
                  and not exists (
                    select 1
                    from raw.document_pages as supplemental
                    where supplemental.raw_artifact_id
                        = page.raw_artifact_id
                      and supplemental.page_number = page.page_number
                      and supplemental.text_content is not null
                  )
                order by artifact.created_at, artifact.id, page.page_number
                limit %s
                """,
                (limit_pages,),
            )
            grouped: dict[str, tuple[TextArtifact, list[int]]] = {}
            while True:
                row = rows.fetchone()
                if row is None:
                    break
                artifact_id = str(row["id"])
                if artifact_id not in grouped:
                    grouped[artifact_id] = (
                        TextArtifact(
                            raw_artifact_id=artifact_id,
                            sha256=str(row["sha256"]),
                            object_key=str(row["object_key"]),
                        ),
                        [],
                    )
                grouped[artifact_id][1].append(int(row["page_number"]))
            return tuple(
                (artifact, tuple(pages))
                for artifact, pages in grouped.values()
            )
        finally:
            connection.close()

    def persist_pages(self, artifact, pages) -> None:
        """Registra páginas canônicas sem criar job (adiado para OCR)."""
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '15s'")
                connection.execute("set local lock_timeout = '5s'")
                self._insert_pages(
                    connection,
                    artifact.raw_artifact_id,
                    pages,
                )
        finally:
            connection.close()

    @classmethod
    def _document_page(
        cls,
        connection: DatabaseConnection,
        batch: ExtractionBatch,
    ) -> None:
        cls._insert_pages(
            connection,
            batch.artifact.raw_artifact_id,
            batch.pages,
        )

    @staticmethod
    def _insert_pages(
        connection: DatabaseConnection,
        raw_artifact_id: str,
        pages,
    ) -> None:
        for page in pages:
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
                values (%s::uuid, %s, %s, %s, %s, %s)
                on conflict (raw_artifact_id, page_number, parser_version)
                  do nothing
                returning id::text as id
                """,
                (
                    raw_artifact_id,
                    page.page_number,
                    page.parser_version,
                    page.extraction_method,
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
                    raw_artifact_id,
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
