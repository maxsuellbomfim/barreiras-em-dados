"""Manifestos locais imutáveis para desenvolvimento sem provedor de nuvem."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any

from .models import (
    DocumentBatch,
    PersistenceBatch,
    PersistenceContractError,
    PersistenceError,
    RepositoryDocumentResult,
    RepositoryPersistResult,
)

_LOCAL_ID_NAMESPACE = uuid.UUID("1953761d-b679-5e40-a3bd-72f1cd109324")


class FilesystemCollectionRepository:
    """Grava um manifesto canônico por execução, sem substituir versões."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def persist(self, batch: PersistenceBatch) -> RepositoryPersistResult:
        run_key = _require_digest(batch.page.idempotency_key, "idempotency_key")
        collection_run_id = str(
            uuid.uuid5(_LOCAL_ID_NAMESPACE, f"collection-run:{run_key}")
        )
        raw_artifact_id = str(
            uuid.uuid5(
                _LOCAL_ID_NAMESPACE,
                f"raw-artifact:{batch.artifact_idempotency_key}",
            )
        )
        manifest = self._manifest(
            batch,
            collection_run_id=collection_run_id,
            raw_artifact_id=raw_artifact_id,
        )
        body = _canonical_json(manifest) + b"\n"
        manifest_hash = hashlib.sha256(body).hexdigest()
        manifest_key = hashlib.sha256(
            f"{run_key}:{batch.parser_version}".encode()
        ).hexdigest()
        directory = self._manifest_directory(manifest_key)
        expected = directory / f"{manifest_hash}.json"
        existing = tuple(directory.glob("*.json")) if directory.exists() else ()

        if existing:
            if len(existing) != 1:
                raise PersistenceContractError(
                    "A execução local possui múltiplos manifestos para o mesmo parser."
                )
            prior = self._read_verified_manifest(existing[0])
            if self._stable_manifest(prior) != self._stable_manifest(manifest):
                raise PersistenceContractError(
                    "A execução local já possui uma identidade estável diferente."
                )
            created = False
        else:
            directory.mkdir(parents=True, exist_ok=True)
            created = self._write_exclusive(expected, body)
            prior = self._read_verified_manifest(expected)
            if prior != manifest:
                raise PersistenceContractError(
                    "O manifesto restaurado diverge do conteúdo gravado."
                )

        record_count = len(batch.records)
        return RepositoryPersistResult(
            collection_run_id=collection_run_id,
            raw_artifact_id=raw_artifact_id,
            inserted_records=record_count if created else 0,
            existing_records=0 if created else record_count,
        )

    def persist_document(self, batch: DocumentBatch) -> RepositoryDocumentResult:
        idempotency = _require_digest(batch.idempotency_key, "idempotency_key")
        raw_artifact_id = str(
            uuid.uuid5(_LOCAL_ID_NAMESPACE, f"document-artifact:{idempotency}")
        )
        manifest = self._document_manifest(batch, raw_artifact_id=raw_artifact_id)
        body = _canonical_json(manifest) + b"\n"
        manifest_hash = hashlib.sha256(body).hexdigest()
        directory = (
            self.root
            / "document-manifests"
            / "sha256"
            / idempotency[:2]
            / idempotency
        )
        try:
            directory.parent.resolve().relative_to(self.root)
        except ValueError as error:
            raise PersistenceError(
                "O manifesto escaparia do diretório local permitido."
            ) from error

        existing = tuple(directory.glob("*.json")) if directory.exists() else ()
        if existing:
            if len(existing) != 1:
                raise PersistenceContractError(
                    "O documento local possui múltiplos manifestos."
                )
            prior = self._read_verified_manifest(existing[0])
            if self._stable_document_manifest(
                prior
            ) != self._stable_document_manifest(manifest):
                raise PersistenceContractError(
                    "O documento local já possui uma identidade estável diferente."
                )
            return RepositoryDocumentResult(
                raw_artifact_id=raw_artifact_id,
                created=False,
            )

        directory.mkdir(parents=True, exist_ok=True)
        created = self._write_exclusive(directory / f"{manifest_hash}.json", body)
        restored = self._read_verified_manifest(directory / f"{manifest_hash}.json")
        if restored != manifest:
            raise PersistenceContractError(
                "O manifesto restaurado diverge do conteúdo gravado."
            )
        return RepositoryDocumentResult(
            raw_artifact_id=raw_artifact_id,
            created=created,
        )

    @staticmethod
    def _document_manifest(
        batch: DocumentBatch,
        *,
        raw_artifact_id: str,
    ) -> dict[str, Any]:
        document = batch.document
        return {
            "schema_name": "local-document-manifest",
            "schema_version": "1.0.0",
            "raw_artifact_id": raw_artifact_id,
            "idempotency_key": batch.idempotency_key,
            "collection_run_id": batch.collection_run_id,
            "parent_artifact_id": batch.parent_artifact_id,
            "source_record_key": batch.source_record_key,
            "collector_version": batch.collector_version,
            "document": {
                "role": document.role,
                "source_url": document.source_url,
                "final_url": document.final_url,
                "requested_at": document.requested_at,
                "received_at": document.received_at,
                "http_status": document.http_status,
                "sha256": document.body_sha256,
                "byte_size": document.body_size_bytes,
                "content_type": document.media_type,
                "object_key": batch.object_key,
            },
        }

    @staticmethod
    def _stable_document_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
        document = manifest.get("document")
        if not isinstance(document, dict):
            raise PersistenceContractError("O manifesto de documento está incompleto.")
        return {
            "schema_name": manifest.get("schema_name"),
            "schema_version": manifest.get("schema_version"),
            "raw_artifact_id": manifest.get("raw_artifact_id"),
            "idempotency_key": manifest.get("idempotency_key"),
            "parent_artifact_id": manifest.get("parent_artifact_id"),
            "source_record_key": manifest.get("source_record_key"),
            "document": {
                "role": document.get("role"),
                "source_url": document.get("source_url"),
                "sha256": document.get("sha256"),
                "byte_size": document.get("byte_size"),
                "object_key": document.get("object_key"),
            },
        }

    def _manifest_directory(self, manifest_key: str) -> Path:
        directory = (
            self.root
            / "collection-manifests"
            / "sha256"
            / manifest_key[:2]
            / manifest_key
        )
        try:
            directory.parent.resolve().relative_to(self.root)
        except ValueError as error:
            raise PersistenceError(
                "O manifesto escaparia do diretório local permitido."
            ) from error
        return directory

    @staticmethod
    def _write_exclusive(path: Path, body: bytes) -> bool:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError:
            return False
        except OSError as error:
            raise PersistenceError("O manifesto local não pôde ser criado.") from error
        with os.fdopen(descriptor, "wb") as file:
            file.write(body)
            file.flush()
            os.fsync(file.fileno())
        return True

    @staticmethod
    def _read_verified_manifest(path: Path) -> dict[str, Any]:
        if path.is_symlink():
            raise PersistenceError("Manifestos locais não podem ser links simbólicos.")
        try:
            restored = path.read_bytes()
        except OSError as error:
            raise PersistenceError(
                "O manifesto local não pôde ser restaurado."
            ) from error
        file_hash = _require_digest(path.stem, "hash do manifesto")
        if hashlib.sha256(restored).hexdigest() != file_hash:
            raise PersistenceContractError(
                "O manifesto local foi alterado ou está corrompido."
            )
        try:
            value = json.loads(restored)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PersistenceContractError(
                "O manifesto local não contém JSON UTF-8 válido."
            ) from error
        if not isinstance(value, dict):
            raise PersistenceContractError("A raiz do manifesto local não é um objeto.")
        return value

    @staticmethod
    def _stable_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
        collection = manifest.get("collection")
        artifact = manifest.get("artifact")
        if not isinstance(collection, dict) or not isinstance(artifact, dict):
            raise PersistenceContractError("O manifesto local está incompleto.")
        return {
            "schema_name": manifest.get("schema_name"),
            "schema_version": manifest.get("schema_version"),
            "collection_run_id": manifest.get("collection_run_id"),
            "raw_artifact_id": manifest.get("raw_artifact_id"),
            "parser_version": manifest.get("parser_version"),
            "artifact": {
                "idempotency_key": artifact.get("idempotency_key"),
                "object_key": artifact.get("object_key"),
                "sha256": artifact.get("sha256"),
                "byte_size": artifact.get("byte_size"),
            },
            "collection": {
                "schema_name": collection.get("schema_name"),
                "schema_version": collection.get("schema_version"),
                "source_code": collection.get("source_code"),
                "endpoint_code": collection.get("endpoint_code"),
                "idempotency_key": collection.get("idempotency_key"),
                "request_url": collection.get("request_url"),
                "cursor": collection.get("cursor"),
            },
            "records": manifest.get("records"),
        }

    @staticmethod
    def _manifest(
        batch: PersistenceBatch,
        *,
        collection_run_id: str,
        raw_artifact_id: str,
    ) -> dict[str, Any]:
        page = batch.page
        return {
            "schema_name": "local-collection-manifest",
            "schema_version": "1.0.0",
            "collection_run_id": collection_run_id,
            "raw_artifact_id": raw_artifact_id,
            "collector_version": batch.collector_version,
            "parser_version": batch.parser_version,
            "artifact": {
                "idempotency_key": batch.artifact_idempotency_key,
                "object_key": batch.object_key,
                "sha256": page.body_sha256,
                "byte_size": page.body_size_bytes,
                "content_type": page.media_type,
            },
            "collection": {
                "schema_name": page.schema_name,
                "schema_version": page.schema_version,
                "source_code": page.source_code,
                "endpoint_code": page.endpoint_code,
                "idempotency_key": page.idempotency_key,
                "request_url": page.request_url,
                "final_url": page.final_url,
                "requested_at": page.requested_at,
                "received_at": page.received_at,
                "attempts": page.attempts,
                "http_status": page.http_status,
                "status": page.collection_status,
                "response_headers": dict(page.response_headers),
                "cursor": dict(page.cursor),
                "window": {
                    "start": page.window_start,
                    "end": page.window_end,
                },
            },
            "records": [
                {
                    "source_record_key": record.source_record_key,
                    "record_type": record.record_type,
                    "record_index": record.record_index,
                    "payload": record.payload,
                    "payload_sha256": record.payload_sha256,
                    "parser_version": record.parser_version,
                    "idempotency_key": record.idempotency_key,
                }
                for record in batch.records
            ],
        }


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _require_digest(value: str, name: str) -> str:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise PersistenceContractError(f"{name} não é um SHA-256 hexadecimal.")
    return value
