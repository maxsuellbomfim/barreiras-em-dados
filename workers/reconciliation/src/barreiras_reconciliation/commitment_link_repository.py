"""Leitura dos brutos e gravação append-only das decisões do ADR 0086."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .commitment_contract_links import LinkDecision, MunicipalContract
from .identity_repository import DatabaseConnection


@dataclass(frozen=True)
class PendingCommitment:
    raw_record_id: str
    row: Mapping[str, str]


class CommitmentLinkRepository:
    def __init__(self, connection_factory: Callable[[], DatabaseConnection]) -> None:
        self.connection_factory = connection_factory

    @classmethod
    def from_dsn(cls, database_url: str) -> CommitmentLinkRepository:
        import psycopg
        from psycopg.rows import dict_row

        return cls(lambda: psycopg.connect(database_url, row_factory=dict_row))

    def municipal_contracts(self) -> tuple[MunicipalContract, ...]:
        """Última versão preservada de cada contrato do portal, por id oficial."""
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                select distinct on (record.payload ->> 'id')
                  record.id::text as raw_record_id,
                  record.payload ->> 'id' as portal_id,
                  coalesce(record.payload ->> 'contratoNumero', '') as number,
                  coalesce(record.payload ->> 'favorecido', '') as contractor
                from raw.raw_records as record
                where record.record_type = 'municipal_transparency_contratos'
                  and record.payload ->> 'id' is not null
                order by
                  record.payload ->> 'id',
                  record.collected_at desc,
                  record.id desc
                """
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            MunicipalContract(
                record_key=str(row["raw_record_id"]),
                number=str(row["number"]),
                contractor=str(row["contractor"]),
                portal_id=str(row["portal_id"]),
            )
            for row in rows
        )

    def pending_commitments(
        self, rule_version: str, limit: int
    ) -> tuple[PendingCommitment, ...]:
        if limit < 1:
            raise ValueError("O limite deve ser positivo.")
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                select record.id::text as raw_record_id, record.payload
                from raw.raw_records as record
                where record.record_type = 'municipal_commitment_webrun'
                  and not exists (
                    select 1
                    from finance.commitment_contract_links as link
                    where link.commitment_raw_record_id = record.id
                      and link.rule_version = %s
                  )
                order by record.collected_at, record.id
                limit %s
                """,
                (rule_version, limit),
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            PendingCommitment(
                raw_record_id=str(row["raw_record_id"]),
                row=_payload(row["payload"]),
            )
            for row in rows
        )

    def record_decisions(self, decisions: tuple[tuple[str, LinkDecision], ...]) -> int:
        """Grava (raw_record_id do empenho, decisão); repetição é ignorada."""
        if not decisions:
            return 0
        serialized = json.dumps(
            [
                {
                    "commitment_raw_record_id": raw_record_id,
                    "commitment_key": decision.commitment_key,
                    "state": decision.state,
                    "reason": decision.reason,
                    "cited_excerpt": decision.cited_excerpt,
                    "contract_raw_record_id": decision.contract_record_key,
                    "contract_portal_id": decision.contract_portal_id,
                    "rule_version": decision.rule_version,
                }
                for raw_record_id, decision in decisions
            ],
            ensure_ascii=False,
        )
        connection = self.connection_factory()
        try:
            with connection.transaction():
                row = connection.execute(
                    """
                    with inserted as (
                      insert into finance.commitment_contract_links (
                        commitment_raw_record_id, commitment_key, state, reason,
                        cited_excerpt, contract_raw_record_id, contract_portal_id,
                        rule_version
                      )
                      select
                        item.commitment_raw_record_id, item.commitment_key,
                        item.state, item.reason, item.cited_excerpt,
                        item.contract_raw_record_id, item.contract_portal_id,
                        item.rule_version
                      from jsonb_to_recordset(%s::jsonb) as item (
                        commitment_raw_record_id uuid,
                        commitment_key text,
                        state text,
                        reason text,
                        cited_excerpt text,
                        contract_raw_record_id uuid,
                        contract_portal_id text,
                        rule_version text
                      )
                      on conflict (commitment_raw_record_id, rule_version) do nothing
                      returning 1
                    )
                    select count(*)::integer as inserted from inserted
                    """,
                    (serialized,),
                ).fetchone()
        finally:
            connection.close()
        return int(row["inserted"]) if row else 0


def _payload(value: Any) -> Mapping[str, str]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError("Registro de empenho sem payload de objeto.")
    return {str(key): str(item) for key, item in value.items()}
