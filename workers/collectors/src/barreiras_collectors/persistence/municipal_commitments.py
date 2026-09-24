"""Preserva as grades mensais de despesa do WebRun (ADR 0086).

A grade é gravada intacta e endereçada por SHA-256. Empenhos viram um registro
bruto por chave oficial; liquidações, um registro por linha distinta, porque
várias liquidações podem citar o mesmo empenho. Repetições idênticas
continuam só no bruto.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from ..connectors.municipal_expenses import STAGES, MonthlyGrid, month_bounds
from .models import (
    ArtifactIntegrityError,
    PersistenceBatch,
    PersistenceResult,
    RawRecordInput,
)

MEDIA_TYPE = "text/html; charset=ISO-8859-1"


@dataclass(frozen=True)
class StagePersistence:
    record_type: str
    collector_version: str
    parser_version: str
    schema_name: str
    object_prefix: str
    page_prefix: str
    record_prefix: str
    key_label: str
    one_record_per_key: bool


STAGE_PERSISTENCE = {
    "empenhos": StagePersistence(
        record_type="municipal_commitment_webrun",
        collector_version="municipal-commitments-webrun/1.0.0",
        parser_version="municipal-commitments-grid/1.0.0",
        schema_name="municipal-commitments-webrun-grid",
        object_prefix="municipal-transparency/despesas-webrun/empenhos",
        page_prefix="municipal-commitments",
        record_prefix="municipal-commitment",
        key_label="empenho",
        one_record_per_key=True,
    ),
    "liquidacoes": StagePersistence(
        record_type="municipal_liquidation_webrun",
        collector_version="municipal-liquidations-webrun/1.0.0",
        parser_version="municipal-liquidations-grid/1.0.0",
        schema_name="municipal-liquidations-webrun-grid",
        object_prefix="municipal-transparency/despesas-webrun/liquidacoes",
        page_prefix="municipal-liquidations",
        record_prefix="municipal-liquidation",
        key_label="liquidacao",
        one_record_per_key=False,
    ),
}
_COMMITMENTS = STAGE_PERSISTENCE["empenhos"]
RECORD_TYPE = _COMMITMENTS.record_type
COLLECTOR_VERSION = _COMMITMENTS.collector_version
PARSER_VERSION = _COMMITMENTS.parser_version
SCHEMA_NAME = _COMMITMENTS.schema_name
OBJECT_PREFIX = _COMMITMENTS.object_prefix


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


def month_label(result: MonthlyGrid) -> str:
    return f"{result.year:04d}-{result.month:02d}"


def grid_page(result: MonthlyGrid) -> GridPage:
    stage = STAGE_PERSISTENCE[result.stage]
    first, last = month_bounds(result.year, result.month)
    return GridPage(
        source_code=result.source_code,
        endpoint_code=result.endpoint_code,
        schema_name=stage.schema_name,
        schema_version="1.0.0",
        idempotency_key=(
            f"{stage.page_prefix}:{month_label(result)}:{result.grid_sha256}"
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


def stage_records(result: MonthlyGrid) -> tuple[RawRecordInput, ...]:
    """Registros brutos do mês, sem repetições idênticas da fonte."""
    stage = STAGE_PERSISTENCE[result.stage]
    key_field = STAGES[result.stage].key_field
    records: list[RawRecordInput] = []
    seen: set[str] = set()
    for index, row in enumerate(result.rows):
        key = row[key_field]
        payload_sha256 = _sha256(
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
        identity = key if stage.one_record_per_key else payload_sha256
        if identity in seen:
            continue
        seen.add(identity)
        if stage.one_record_per_key:
            source_record_key = f"prefeitura-despesas-webrun:{stage.key_label}:{key}"
            idempotency_material = (
                f"{stage.record_prefix}:{result.grid_sha256}:{key}:{payload_sha256}"
            )
        else:
            source_record_key = (
                f"prefeitura-despesas-webrun:{stage.key_label}:{key}:"
                f"{payload_sha256[:24]}"
            )
            idempotency_material = (
                f"{stage.record_prefix}:{result.grid_sha256}:{payload_sha256}"
            )
        records.append(
            RawRecordInput(
                source_record_key=source_record_key,
                record_type=stage.record_type,
                record_index=index,
                payload=dict(row),
                payload_sha256=payload_sha256,
                parser_version=stage.parser_version,
                idempotency_key=_sha256(idempotency_material),
            )
        )
    return tuple(records)


commitment_records = stage_records


class MunicipalCommitmentsPersistenceService:
    def __init__(self, *, object_store, repository) -> None:
        self.object_store = object_store
        self.repository = repository

    def persist(self, result: MonthlyGrid) -> PersistenceResult:
        if _sha256_bytes(result.grid_body) != result.grid_sha256:
            raise ArtifactIntegrityError(
                "A grade de despesa não corresponde ao hash informado."
            )
        stage = STAGE_PERSISTENCE[result.stage]
        page = grid_page(result)
        object_key = (
            f"{stage.object_prefix}/sha256/{result.grid_sha256[:2]}/"
            f"{result.grid_sha256}.js"
        )
        records = stage_records(result)
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
                collector_version=stage.collector_version,
                parser_version=stage.parser_version,
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
