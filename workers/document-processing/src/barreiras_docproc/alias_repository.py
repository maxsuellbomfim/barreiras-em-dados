"""Persistência interna das sugestões de aliases de representantes."""

from __future__ import annotations

import json
from collections.abc import Callable

from barreiras_collectors.persistence.postgres import DatabaseConnection

from .alias_assist import ALIAS_ASSIST_PROMPT_VERSION


class RepresentativeAliasRepository:
    """Leitura de nomes publicados e gravação idempotente de sugestões."""

    def __init__(self, connection_factory: Callable[[], DatabaseConnection]) -> None:
        self.connection_factory = connection_factory

    @classmethod
    def from_dsn(cls, database_url: str) -> RepresentativeAliasRepository:
        from barreiras_collectors.persistence.postgres import (
            PostgresCollectionRepository,
        )

        collection = PostgresCollectionRepository.from_dsn(database_url)
        return cls(collection.connection_factory)

    def pending_author_aliases(self, limit: int) -> tuple[dict, ...]:
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                with authors as (
                  select
                    nullif(btrim(coalesce(
                      record.payload ->> 'autoria',
                      record.payload ->> 'autor',
                      record.payload ->> 'author'
                    )), '') as author_name,
                    record.source_record_key
                  from raw.raw_records as record
                  where record.record_type in (
                    'municipal_transparency_leis',
                    'municipal_transparency_indicacoes'
                  )
                ), people as (
                  select distinct on (record.source_record_key)
                    record.source_record_key as representative_external_id,
                    nullif(btrim(record.payload ->> 'nome'), '') as canonical_name,
                    nullif(btrim(record.payload ->> 'partido'), '') as party
                  from raw.raw_records as record
                  where record.record_type = 'cm_barreiras_vereador'
                    and record.payload ->> 'nome' is not null
                  order by record.source_record_key, record.collected_at desc
                ), candidates as (
                  select
                    crosswalk.representative_external_id,
                    crosswalk.candidate_id,
                    people.canonical_name,
                    people.party
                  from political.representative_tse_crosswalk as crosswalk
                  join people
                    on people.representative_external_id
                     = crosswalk.representative_external_id
                  where crosswalk.source_kind = 'municipal'
                    and crosswalk.review_status = 'approved'
                )
                select
                  authors.author_name,
                  array_agg(distinct authors.source_record_key)
                    filter (where authors.source_record_key is not null)
                    as source_record_keys,
                  count(*)::integer as item_count,
                  coalesce(
                    jsonb_agg(
                      distinct jsonb_build_object(
                        'representative_external_id',
                        candidates.representative_external_id,
                        'candidate_id', candidates.candidate_id,
                        'canonical_name', candidates.canonical_name,
                        'party', candidates.party
                      )
                    ) filter (where candidates.representative_external_id is not null),
                    '[]'::jsonb
                  ) as candidates
                from authors
                cross join candidates
                where authors.author_name is not null
                  and not exists (
                    select 1
                    from political.representative_alias_suggestions as suggestion
                    where suggestion.source_kind = 'municipal'
                      and suggestion.observed_name = authors.author_name
                      and suggestion.prompt_version = %s
                  )
                group by authors.author_name
                order by count(*) desc, authors.author_name
                limit %s
                """,
                (ALIAS_ASSIST_PROMPT_VERSION, limit),
            )
            found: list[dict] = []
            while True:
                row = rows.fetchone()
                if row is None:
                    break
                candidates = row["candidates"]
                found.append(
                    {
                        "observed_name": str(row["author_name"]),
                        "source_record_keys": [
                            str(value)
                            for value in (row["source_record_keys"] or [])
                            if value
                        ],
                        "item_count": int(row["item_count"]),
                        "candidates": (
                            candidates
                            if isinstance(candidates, list)
                            else json.loads(str(candidates))
                        ),
                    }
                )
            return tuple(found)
        finally:
            connection.close()

    def persist_suggestion(
        self,
        *,
        observed_name: str,
        source_record_keys: list[str],
        item_count: int,
        candidates: list[dict],
        provider: str,
        model: str,
        result: dict,
        raw_response: str,
    ) -> None:
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '15s'")
                connection.execute(
                    """
                    insert into political.representative_alias_suggestions (
                      source_kind, observed_name, source_record_keys, item_count,
                      candidates, decision, candidate_external_id, alias_kind,
                      confidence, rationale, evidence, provider, model,
                      prompt_version, validator_version, raw_response, status
                    )
                    values (
                      'municipal', %s, %s, %s, %s::jsonb, %s, %s, %s, %s,
                      %s, %s::jsonb, %s, %s, %s, %s, %s, 'pending'
                    )
                    on conflict (source_kind, observed_name, prompt_version)
                    do update set
                      source_record_keys = excluded.source_record_keys,
                      item_count = excluded.item_count,
                      candidates = excluded.candidates,
                      decision = excluded.decision,
                      candidate_external_id = excluded.candidate_external_id,
                      alias_kind = excluded.alias_kind,
                      confidence = excluded.confidence,
                      rationale = excluded.rationale,
                      evidence = excluded.evidence,
                      provider = excluded.provider,
                      model = excluded.model,
                      validator_version = excluded.validator_version,
                      raw_response = excluded.raw_response,
                      status = 'pending',
                      updated_at = statement_timestamp()
                    """,
                    (
                        observed_name,
                        source_record_keys,
                        item_count,
                        json.dumps(candidates, ensure_ascii=False),
                        result["decision"],
                        result["candidate_external_id"],
                        result["alias_kind"],
                        result["confidence"],
                        result["rationale"],
                        json.dumps(result["evidence"], ensure_ascii=False),
                        provider,
                        model,
                        ALIAS_ASSIST_PROMPT_VERSION,
                        result["validator_version"],
                        raw_response[:20_000],
                    ),
                )
        finally:
            connection.close()
