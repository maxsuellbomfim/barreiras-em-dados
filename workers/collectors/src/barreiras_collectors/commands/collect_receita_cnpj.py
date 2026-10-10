"""Preserva o cadastro oficial (Receita) dos CNPJs de contratos de Barreiras."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from ..collection_control import (
    CollectionControl,
    CollectionOutcome,
    build_execution_idempotency_key,
)
from ..connectors.receita_cnpj import (
    EMPRESAS_FILES,
    ENDPOINT_CODE,
    ESTABELECIMENTOS_FILES,
    NATUREZAS_FILE,
    SOURCE_CODE,
    WEBDAV_URL,
    build_registry,
    download,
    latest_complete_month,
    read_naturezas,
    scan_empresas,
    scan_estabelecimentos,
)
from ..logging import log_event
from ..persistence.models import (
    ArtifactIntegrityError,
    PersistenceBatch,
    RawRecordInput,
)
from ..persistence.postgres import PostgresCollectionRepository
from ..settings import CollectorSettings, PersistenceSettings
from .pncp_runtime import build_authenticated_object_store

COLLECTOR_VERSION = "receita-cnpj-collector/1.0.0"
PARSER_VERSION = "receita-cnpj-extract/1.1.0"


@dataclass(frozen=True)
class RegistryExtract:
    """Extrato preservado; tem a forma que o repositório de coleta espera."""

    raw_body: bytes
    body_sha256: str
    month: str
    requested_at: str
    received_at: str
    items: tuple[dict[str, str], ...]
    cursor: dict[str, object]
    schema_name: str = "receita-cnpj-registry-extract"
    schema_version: str = "1.0.0"
    artifact_kind: str = "document"
    source_code: str = SOURCE_CODE
    endpoint_code: str = ENDPOINT_CODE
    attempts: int = 1
    http_status: int = 200
    media_type: str = "application/json"
    response_headers: dict[str, str] = field(default_factory=dict)

    @property
    def request_url(self) -> str:
        return f"{WEBDAV_URL}/{self.month}/"

    @property
    def final_url(self) -> str:
        return self.request_url

    @property
    def idempotency_key(self) -> str:
        return hashlib.sha256(
            f"receita-cnpj:{self.month}:{self.body_sha256}".encode()
        ).hexdigest()

    @property
    def body_size_bytes(self) -> int:
        return len(self.raw_body)

    @property
    def collection_status(self) -> str:
        return "success" if self.items else "empty"

    @property
    def window_start(self) -> str:
        return f"{self.month}-01"

    @property
    def window_end(self) -> str:
        return f"{self.month}-01"


def build_extract(
    *,
    month: str,
    targets: frozenset[str],
    files: dict[str, dict[str, object]],
    registry: list[dict[str, str]],
    missing: list[str],
    requested_at: str,
    received_at: str,
) -> RegistryExtract:
    rows = tuple({**row, "registry_month": month} for row in registry)
    targets_sha256 = hashlib.sha256("\n".join(sorted(targets)).encode()).hexdigest()
    document = {
        "schema": "receita-cnpj-registry-extract/1.0.0",
        "month": month,
        "targets": len(targets),
        "targets_sha256": targets_sha256,
        "source_files": files,
        "registry": list(rows),
        "not_found": missing,
    }
    body = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return RegistryExtract(
        raw_body=body,
        body_sha256=hashlib.sha256(body).hexdigest(),
        month=month,
        requested_at=requested_at,
        received_at=received_at,
        items=rows,
        cursor={
            "month": month,
            "targets": len(targets),
            "targets_sha256": targets_sha256,
            "found": len(rows),
            "not_found": len(missing),
            "source_files": {name: meta["sha256"] for name, meta in files.items()},
        },
    )


def records_for(extract: RegistryExtract) -> tuple[RawRecordInput, ...]:
    records = []
    for index, row in enumerate(extract.items):
        canonical = json.dumps(
            row, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        payload_sha256 = hashlib.sha256(canonical.encode()).hexdigest()
        records.append(
            RawRecordInput(
                source_record_key=f"receita:cnpj:{row['cnpj']}:{extract.month}",
                record_type="receita_cnpj_registry",
                record_index=index,
                payload=row,
                payload_sha256=payload_sha256,
                parser_version=PARSER_VERSION,
                idempotency_key=hashlib.sha256(
                    f"receita-cnpj-record:{extract.body_sha256}:{row['cnpj']}:{payload_sha256}".encode()
                ).hexdigest(),
            )
        )
    return tuple(records)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    collector_settings = CollectorSettings.from_env()
    persistence = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    logger = logging.getLogger(__name__)
    if persistence.mode != "postgres-supabase" or persistence.database_url is None:
        raise RuntimeError("O cadastro CNPJ requer PERSISTENCE_MODE=postgres-supabase.")
    repository = PostgresCollectionRepository.from_dsn(persistence.database_url)

    connection = repository.connection_factory()
    try:
        targets = frozenset(
            row["cnpj"]
            for row in connection.execute(
                "select cnpj from finance.get_cnpj_registry_targets()"
            ).fetchall()
        )
    finally:
        connection.close()

    requested_at = datetime.now(UTC).isoformat()
    remote = latest_complete_month()
    month = remote[NATUREZAS_FILE].month
    # Mesmo mês, mesmos alvos e mesma versão do extrato já preservados: não
    # baixa 7 GB de novo. Versão nova do extrato força uma coleta.
    targets_sha256 = hashlib.sha256("\n".join(sorted(targets)).encode()).hexdigest()
    connection = repository.connection_factory()
    try:
        already = connection.execute(
            """
            select 1
            from raw.raw_artifacts as artifact
            where artifact.metadata ->> 'schema_name' = 'receita-cnpj-registry-extract'
              and artifact.metadata -> 'cursor' ->> 'month' = %s
              and artifact.metadata -> 'cursor' ->> 'targets_sha256' = %s
              and artifact.parser_version = %s
            limit 1
            """,
            (month, targets_sha256, PARSER_VERSION),
        ).fetchone()
    finally:
        connection.close()
    if already:
        log_event(
            logger,
            logging.INFO,
            "receita_cnpj_skipped",
            source=SOURCE_CODE,
            month=month,
            targets=len(targets),
            reason="month_and_targets_already_preserved",
        )
        return 0
    today = datetime.now(UTC).date()
    control = CollectionControl(
        repository=repository,
        source_code=SOURCE_CODE,
        endpoint_code=ENDPOINT_CODE,
        idempotency_key=build_execution_idempotency_key(f"receita-cnpj-{month}"),
        collector_version=COLLECTOR_VERSION,
        parser_version=PARSER_VERSION,
        partition_key=f"registry-month:{month}",
        period_start=date.fromisoformat(f"{month}-01"),
        period_end=max(date.fromisoformat(f"{month}-01"), today),
    )
    with control:
        empresas: dict[str, dict[str, str]] = {}
        estabelecimentos: dict[str, dict[str, str]] = {}
        files: dict[str, dict[str, object]] = {}
        bases = frozenset(cnpj[:8] for cnpj in targets)
        with tempfile.TemporaryDirectory() as directory:
            for name in (NATUREZAS_FILE, *EMPRESAS_FILES, *ESTABELECIMENTOS_FILES):
                downloaded = download(remote[name], Path(directory))
                files[name] = {
                    "url": downloaded.remote.url,
                    "size": downloaded.remote.size,
                    "last_modified": downloaded.remote.last_modified,
                    "sha256": downloaded.sha256,
                }
                if name == NATUREZAS_FILE:
                    naturezas = read_naturezas(downloaded.path)
                elif name in EMPRESAS_FILES:
                    empresas.update(scan_empresas(downloaded.path, bases))
                else:
                    estabelecimentos.update(
                        scan_estabelecimentos(downloaded.path, targets)
                    )
                downloaded.path.unlink()
                log_event(
                    logger,
                    logging.INFO,
                    "receita_cnpj_file_processed",
                    source=SOURCE_CODE,
                    file=name,
                    sha256=downloaded.sha256,
                )
        registry, missing = build_registry(
            targets, empresas, estabelecimentos, naturezas
        )
        extract = build_extract(
            month=month,
            targets=targets,
            files=files,
            registry=registry,
            missing=missing,
            requested_at=requested_at,
            received_at=datetime.now(UTC).isoformat(),
        )
        digest = extract.body_sha256
        object_key = f"receita/cnpj/{month}/sha256/{digest[:2]}/{digest}.json"
        # Sessão do Storage aberta só agora: o JWT dura 1 h e o download de
        # 7 GB leva mais que isso (upload recusado em 10/10/2026).
        object_store = build_authenticated_object_store(persistence)
        stored = object_store.put_if_absent(
            object_key=object_key,
            body=extract.raw_body,
            content_type="application/json",
            expected_sha256=extract.body_sha256,
        )
        if (
            hashlib.sha256(object_store.read(object_key)).hexdigest()
            != extract.body_sha256
        ):
            raise ArtifactIntegrityError("O extrato restaurado diverge do coletado.")
        persisted = repository.persist(
            PersistenceBatch(
                page=extract,  # type: ignore[arg-type]
                object_key=object_key,
                artifact_idempotency_key=hashlib.sha256(
                    f"raw-artifact:{extract.idempotency_key}".encode()
                ).hexdigest(),
                collector_version=COLLECTOR_VERSION,
                parser_version=PARSER_VERSION,
                records=records_for(extract),
            )
        )
        control.complete(
            outcome=CollectionOutcome.COMPLETE if registry else CollectionOutcome.EMPTY,
            observed_records=len(registry),
            checkpoint={"month": month, "artifact_sha256": extract.body_sha256},
            metrics={
                "targets": len(targets),
                "found": len(registry),
                "not_found": len(missing),
                "inserted_records": persisted.inserted_records,
                "object_created": stored.created,
            },
        )
    log_event(
        logger,
        logging.INFO,
        "receita_cnpj_completed",
        source=SOURCE_CODE,
        month=month,
        targets=len(targets),
        found=len(registry),
        not_found=len(missing),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
