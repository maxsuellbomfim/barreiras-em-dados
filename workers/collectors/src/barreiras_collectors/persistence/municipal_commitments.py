"""Preserva a grade mensal de empenhos do WebRun (ADR 0086).

A grade é gravada intacta e endereçada por SHA-256; cada chave oficial
distinta vira um registro bruto com a linha literal da fonte. Repetições
idênticas continuam só no bruto.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from ..connectors.municipal_expenses import FIELD_KEY, MonthlyCommitments, month_bounds
from .models import (
    ArtifactIntegrityError,
    PersistenceBatch,
    PersistenceResult,
    RawRecordInput,
)

RECORD_TYPE = "municipal_commitment_webrun"
COLLECTOR_VERSION = "municipal-commitments-webrun/1.0.0"
PARSER_VERSION = "municipal-commitments-grid/1.0.0"
SCHEMA_NAME = "municipal-commitments-webrun-grid"
MEDIA_TYPE = "text/html; charset=ISO-8859-1"
OBJECT_PREFIX = "municipal-transparency/despesas-webrun/empenhos"


@dataclass(frozen=True)
class GridPage:
    """Atributos que ``PostgresCollectionRepository.persist`` lê da resposta."""

    source_code: str
    endpoint_code: str
    schema_name: str
    schema_version: str
    idempotency_key: str
    request_url: str
    final_url: str
    requested_at: str
    received_at: str
    attempts: int
    http_status: int
    collection_status: str
    body_sha256: str
    body_size_bytes: int
    media_type: str
    response_headers: Mapping[str, str]
    cursor: Mapping[str, object]
    window_start: str
    window_end: str


def month_label(result: MonthlyCommitments) -> str:
    return f"{result.year:04d}-{result.month:02d}"


def grid_page(result: MonthlyCommitments) -> GridPage:
    first, last = month_bounds(result.year, result.month)
    return GridPage(
        source_code=result.source_code,
        endpoint_code=result.endpoint_code,
        schema_name=SCHEMA_NAME,
        schema_version="1.0.0",
        idempotency_key=(
            f"municipal-commitments:{month_label(result)}:{result.grid_sha256}"
        ),
        request_url=result.grid_url,
        final_url=result.grid_url,
        requested_at=result.requested_at,
        received_at=result.received_at,
        attempts=1,
        http_status=200,
        collection_status=result.coverage,
        body_sha256=result.grid_sha256,
        body_size_bytes=len(result.grid_body),
        media_type=MEDIA_TYPE,
        response_headers=dict(result.grid_headers),
        cursor={"month": month_label(result), "declared_total": result.declared_total},
        window_start=first.isoformat(),
        window_end=last.isoformat(),
    )


def commitment_records(result: MonthlyCommitments) -> tuple[RawRecordInput, ...]:
    """Um registro por chave oficial, na posição da primeira ocorrência."""
    records: list[RawRecordInput] = []
    seen: set[str] = set()
    for index, row in enumerate(result.rows):
        key = row[FIELD_KEY]
        if key in seen:
            continue
        seen.add(key)
        payload_sha256 = _sha256(
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
        records.append(
            RawRecordInput(
                source_record_key=f"prefeitura-despesas-webrun:empenho:{key}",
                record_type=RECORD_TYPE,
                record_index=index,
                payload=dict(row),
                payload_sha256=payload_sha256,
                parser_version=PARSER_VERSION,
                idempotency_key=_sha256(
                    f"municipal-commitment:{result.grid_sha256}:{key}:{payload_sha256}"
                ),
            )
        )
    return tuple(records)


class MunicipalCommitmentsPersistenceService:
    def __init__(self, *, object_store, repository) -> None:
        self.object_store = object_store
        self.repository = repository

    def persist(self, result: MonthlyCommitments) -> PersistenceResult:
        if _sha256_bytes(result.grid_body) != result.grid_sha256:
            raise ArtifactIntegrityError(
                "A grade de empenhos não corresponde ao hash informado."
            )
        page = grid_page(result)
        object_key = (
            f"{OBJECT_PREFIX}/sha256/{result.grid_sha256[:2]}/{result.grid_sha256}.js"
        )
        records = commitment_records(result)
        # put_if_absent relê o objeto e confere o SHA-256 antes de devolver.
        stored = self.object_store.put_if_absent(
            object_key=object_key,
            body=result.grid_body,
            content_type=MEDIA_TYPE,
            expected_sha256=result.grid_sha256,
        )
        if stored.sha256 != result.grid_sha256 or stored.byte_size != len(
            result.grid_body
        ):
            raise ArtifactIntegrityError("A grade restaurada diverge da coletada.")
        persisted = self.repository.persist(
            PersistenceBatch(
                page=page,  # type: ignore[arg-type]
                object_key=object_key,
                artifact_idempotency_key=_sha256(
                    f"raw-artifact:{page.idempotency_key}"
                ),
                collector_version=COLLECTOR_VERSION,
                parser_version=PARSER_VERSION,
                records=records,
            )
        )
        return PersistenceResult(
            collection_run_id=persisted.collection_run_id,
            raw_artifact_id=persisted.raw_artifact_id,
            object_key=object_key,
            sha256=result.grid_sha256,
            object_created=stored.created,
            inserted_records=persisted.inserted_records,
            existing_records=persisted.existing_records,
        )


def _sha256(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
