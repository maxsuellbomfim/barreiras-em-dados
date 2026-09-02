"""Acesso mínimo ao recorte eleitoral e ao registro privado de identidades."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from .private_identifiers import ProtectedIdentifier, ProtectedSourcePayload


class QueryResult(Protocol):
    def fetchall(self) -> list[Mapping[str, Any]]: ...

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


@dataclass(frozen=True, slots=True)
class IdentityTarget:
    source_kind: str
    source_external_id: str
    election_year: int
    office: str
    candidate_id: str
    origin_raw_record_id: str
    source_collected_at: datetime
    votes_in_barreiras: int


@dataclass(frozen=True, slots=True)
class IdentityRegistration:
    target: IdentityTarget
    source_record_key: str
    source_url: str
    archive_sha256: str
    state_file_sha256: str
    parser_version: str
    display_name: str
    normalized_name: str
    ballot_name: str
    protected_identifier: ProtectedIdentifier = field(repr=False)
    protected_source: ProtectedSourcePayload = field(repr=False)


@dataclass(frozen=True, slots=True)
class IdentifierGapRegistration:
    target: IdentityTarget
    source_record_key: str
    source_url: str
    archive_sha256: str
    state_file_sha256: str
    parser_version: str
    reason: str
    protected_source: ProtectedSourcePayload = field(repr=False)


class IdentityRepository:
    def __init__(self, connection_factory: Callable[[], DatabaseConnection]) -> None:
        self.connection_factory = connection_factory

    @classmethod
    def from_dsn(cls, database_url: str) -> IdentityRepository:
        import psycopg
        from psycopg.rows import dict_row

        return cls(lambda: psycopg.connect(database_url, row_factory=dict_row))

    def eligible_targets(self, election_year: int) -> tuple[IdentityTarget, ...]:
        if not 1994 <= election_year <= 2100:
            raise ValueError("Ano eleitoral fora do intervalo permitido.")
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                with latest_vote as (
                  select distinct on (
                    record.payload ->> 'ano',
                    record.payload ->> 'cargo',
                    record.payload ->> 'sq_candidato'
                  )
                    record.id as origin_raw_record_id,
                    record.collected_at as source_collected_at,
                    record.payload ->> 'ano' as election_year,
                    record.payload ->> 'cargo' as office,
                    record.payload ->> 'sq_candidato' as candidate_id,
                    (record.payload ->> 'votos_em_barreiras')::integer
                      as votes_in_barreiras
                  from raw.raw_records as record
                  where record.record_type = 'tse_votacao_barreiras'
                    and record.payload ->> 'ano' = %s::text
                    and record.payload ->> 'turno' = '1'
                    and record.payload ->> 'votos_em_barreiras' ~ '^[0-9]+$'
                  order by
                    record.payload ->> 'ano',
                    record.payload ->> 'cargo',
                    record.payload ->> 'sq_candidato',
                    record.collected_at desc,
                    record.id desc
                ), base as (
                  select
                    crosswalk.source_kind,
                    crosswalk.representative_external_id,
                    crosswalk.election_year,
                    crosswalk.office,
                    crosswalk.candidate_id,
                    vote.origin_raw_record_id,
                    vote.source_collected_at,
                    vote.votes_in_barreiras
                  from political.representative_tse_crosswalk as crosswalk
                  join latest_vote as vote
                    on vote.election_year = crosswalk.election_year::text
                   and lower(vote.office) = lower(crosswalk.office)
                   and vote.candidate_id = crosswalk.candidate_id
                  where crosswalk.election_year = %s
                    and crosswalk.review_status = 'approved'
                    and crosswalk.vote_scope = 'person'
                ), ranked as (
                  select
                    base.*,
                    case
                      when base.source_kind in ('federal', 'state') then
                        row_number() over (
                          partition by base.source_kind, base.election_year, base.office
                          order by base.votes_in_barreiras desc, base.candidate_id
                        )
                    end as territorial_rank
                  from base
                )
                select *
                from ranked
                where source_kind in ('municipal', 'executive')
                   or territorial_rank <= 10
                order by source_kind, votes_in_barreiras desc, candidate_id
                """,
                (election_year, election_year),
            ).fetchall()
            return tuple(
                IdentityTarget(
                    source_kind=str(row["source_kind"]),
                    source_external_id=str(row["representative_external_id"]),
                    election_year=int(row["election_year"]),
                    office=str(row["office"]),
                    candidate_id=str(row["candidate_id"]),
                    origin_raw_record_id=str(row["origin_raw_record_id"]),
                    source_collected_at=row["source_collected_at"],
                    votes_in_barreiras=int(row["votes_in_barreiras"]),
                )
                for row in rows
            )
        finally:
            connection.close()

    def evidenced_candidate_ids(self, election_year: int) -> frozenset[str]:
        if not 1994 <= election_year <= 2100:
            raise ValueError("Ano eleitoral fora do intervalo permitido.")
        prefix = f"candidate:{election_year}:"
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                select distinct source_record_key
                from private.person_identifier_sources
                where source_name = 'tse_candidate_registry'
                  and election_year = %s
                  and source_record_key like %s
                """,
                (election_year, f"{prefix}%"),
            ).fetchall()
            return frozenset(
                key.removeprefix(prefix)
                for row in rows
                if (key := str(row["source_record_key"])).startswith(prefix)
                and key.removeprefix(prefix)
            )
        finally:
            connection.close()

    def register(self, registration: IdentityRegistration) -> str:
        target = registration.target
        identifier = registration.protected_identifier
        source = registration.protected_source
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '15s'")
                connection.execute("set local lock_timeout = '5s'")
                row = connection.execute(
                    """
                    select status
                    from identity.register_tse_identity(
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        registration.source_record_key,
                        target.election_year,
                        registration.source_url,
                        source.encrypted_payload,
                        source.nonce,
                        source.authentication_tag,
                        source.payload_sha256,
                        registration.archive_sha256,
                        registration.state_file_sha256,
                        source.key_version,
                        registration.parser_version,
                        target.source_collected_at,
                        target.source_kind,
                        target.source_external_id,
                        target.office,
                        target.origin_raw_record_id,
                        identifier.encrypted_value,
                        identifier.nonce,
                        identifier.authentication_tag,
                        identifier.fingerprint,
                        identifier.last_four,
                        registration.display_name,
                        registration.normalized_name,
                        registration.ballot_name,
                    ),
                ).fetchone()
                if row is None or row.get("status") not in {
                    "inserted",
                    "unchanged",
                    "conflicted",
                }:
                    raise RuntimeError("Registro privado retornou estado inválido.")
                return str(row["status"])
        finally:
            connection.close()

    def register_unavailable(self, registration: IdentifierGapRegistration) -> str:
        target = registration.target
        source = registration.protected_source
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '15s'")
                connection.execute("set local lock_timeout = '5s'")
                row = connection.execute(
                    """
                    select status
                    from identity.register_tse_identifier_gap(
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        registration.source_record_key,
                        target.election_year,
                        registration.source_url,
                        source.encrypted_payload,
                        source.nonce,
                        source.authentication_tag,
                        source.payload_sha256,
                        registration.archive_sha256,
                        registration.state_file_sha256,
                        source.key_version,
                        registration.parser_version,
                        target.source_collected_at,
                        target.source_kind,
                        target.source_external_id,
                        target.office,
                        target.origin_raw_record_id,
                        registration.reason,
                    ),
                ).fetchone()
                if row is None or row.get("status") not in {
                    "inserted",
                    "unchanged",
                }:
                    raise RuntimeError("Lacuna privada retornou estado inválido.")
                return str(row["status"])
        finally:
            connection.close()
