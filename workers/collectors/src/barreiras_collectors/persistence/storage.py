"""Adaptadores de objetos imutáveis para desenvolvimento e produção."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import Protocol

from .models import ArtifactIntegrityError, PersistenceError, StoredObject


class SupabaseBucketClient(Protocol):
    def upload(
        self,
        *,
        path: str,
        file: bytes,
        file_options: dict[str, str],
    ) -> object: ...

    def download(self, path: str) -> bytes: ...


class SupabaseStorageObjectStore:
    """Preserva objetos imutáveis e recompõe partes com verificação de hash."""

    _MANIFEST_MAGIC = b"B360-CHUNKED-OBJECT/1\n"
    _MANIFEST_SCHEMA = "barreiras360.chunked-object"
    _DEFAULT_CHUNK_SIZE_BYTES = 32 * 1024 * 1024
    _MAX_CHUNK_SIZE_BYTES = 64 * 1024 * 1024
    _MAX_MANIFEST_PARTS = 4096

    def __init__(
        self,
        bucket_client: SupabaseBucketClient,
        *,
        chunk_size_bytes: int = _DEFAULT_CHUNK_SIZE_BYTES,
    ) -> None:
        if not 1 <= chunk_size_bytes <= self._MAX_CHUNK_SIZE_BYTES:
            raise ValueError("O tamanho das partes do Storage é inválido.")
        self.bucket_client = bucket_client
        self.chunk_size_bytes = chunk_size_bytes

    def put_if_absent(
        self,
        *,
        object_key: str,
        body: bytes,
        content_type: str,
        expected_sha256: str,
    ) -> StoredObject:
        self._validate_object_key(object_key, expected_sha256)
        actual_hash = hashlib.sha256(body).hexdigest()
        if actual_hash != expected_sha256:
            raise ArtifactIntegrityError("O corpo não corresponde ao SHA-256 esperado.")

        if len(body) > self.chunk_size_bytes:
            return self._put_chunked(
                object_key=object_key,
                body=body,
                content_type=content_type,
                expected_sha256=expected_sha256,
            )

        created = True
        try:
            self.bucket_client.upload(
                path=object_key,
                file=body,
                file_options={
                    "content-type": content_type,
                    "cache-control": "31536000",
                    "upsert": "false",
                },
            )
        except Exception as upload_error:
            created = False
            try:
                existing = self.read(object_key)
            except Exception:
                raise PersistenceError(
                    "Falha no upload e o objeto não pôde ser restaurado."
                ) from upload_error
            if hashlib.sha256(existing).hexdigest() != expected_sha256:
                raise ArtifactIntegrityError(
                    "A chave de conteúdo já existe com bytes divergentes."
                ) from upload_error

        restored = self.read(object_key)
        restored_hash = hashlib.sha256(restored).hexdigest()
        if restored_hash != expected_sha256:
            raise ArtifactIntegrityError(
                "A verificação pós-upload encontrou hash divergente."
            )
        return StoredObject(
            object_key=object_key,
            sha256=restored_hash,
            byte_size=len(restored),
            created=created,
        )

    def read(self, object_key: str) -> bytes:
        value = self._download(object_key)
        if not value.startswith(self._MANIFEST_MAGIC):
            return value
        return self._restore_chunked(object_key, value)

    def _put_chunked(
        self,
        *,
        object_key: str,
        body: bytes,
        content_type: str,
        expected_sha256: str,
    ) -> StoredObject:
        parts: list[dict[str, object]] = []
        for index, offset in enumerate(range(0, len(body), self.chunk_size_bytes)):
            chunk = body[offset : offset + self.chunk_size_bytes]
            chunk_sha256 = hashlib.sha256(chunk).hexdigest()
            chunk_key = self._chunk_object_key(object_key, index, chunk_sha256)
            self._put_chunk_if_absent(chunk_key, chunk, chunk_sha256)
            parts.append(
                {
                    "index": index,
                    "object_key": chunk_key,
                    "sha256": chunk_sha256,
                    "byte_size": len(chunk),
                }
            )

        manifest = self._MANIFEST_MAGIC + json.dumps(
            {
                "schema": self._MANIFEST_SCHEMA,
                "version": 1,
                "sha256": expected_sha256,
                "byte_size": len(body),
                "content_type": content_type,
                "chunk_size_bytes": self.chunk_size_bytes,
                "parts": parts,
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        created = True
        try:
            self._upload(
                object_key,
                manifest,
                "application/json",
            )
        except Exception as upload_error:
            created = False
            try:
                existing = self.read(object_key)
            except ArtifactIntegrityError:
                raise
            except Exception:
                raise PersistenceError(
                    "Falha no upload do manifesto e o objeto não pôde ser restaurado."
                ) from upload_error
            if hashlib.sha256(existing).hexdigest() != expected_sha256:
                raise ArtifactIntegrityError(
                    "A chave de conteúdo já existe com bytes divergentes."
                ) from upload_error

        restored = self.read(object_key)
        restored_hash = hashlib.sha256(restored).hexdigest()
        if restored_hash != expected_sha256:
            raise ArtifactIntegrityError(
                "A reconstrução pós-upload encontrou hash divergente."
            )
        return StoredObject(
            object_key=object_key,
            sha256=restored_hash,
            byte_size=len(restored),
            created=created,
        )

    def _put_chunk_if_absent(
        self,
        object_key: str,
        body: bytes,
        expected_sha256: str,
    ) -> None:
        try:
            self._upload(object_key, body, "application/octet-stream")
        except Exception as upload_error:
            try:
                existing = self._download(object_key)
            except Exception:
                raise PersistenceError(
                    "Falha no upload de uma parte e ela não pôde ser restaurada."
                ) from upload_error
            if hashlib.sha256(existing).hexdigest() != expected_sha256:
                raise ArtifactIntegrityError(
                    "Uma parte existente possui bytes divergentes."
                ) from upload_error

        restored = self._download(object_key)
        if hashlib.sha256(restored).hexdigest() != expected_sha256:
            raise ArtifactIntegrityError(
                "A verificação pós-upload de uma parte encontrou hash divergente."
            )

    def _restore_chunked(self, object_key: str, manifest_body: bytes) -> bytes:
        try:
            manifest = json.loads(
                manifest_body[len(self._MANIFEST_MAGIC) :].decode("utf-8")
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ArtifactIntegrityError("O manifesto de partes é inválido.") from error

        if not isinstance(manifest, dict):
            raise ArtifactIntegrityError("O manifesto de partes não é um objeto.")
        original_sha256 = manifest.get("sha256")
        byte_size = manifest.get("byte_size")
        chunk_size = manifest.get("chunk_size_bytes")
        parts = manifest.get("parts")
        if (
            manifest.get("schema") != self._MANIFEST_SCHEMA
            or manifest.get("version") != 1
            or not self._is_sha256(original_sha256)
            or not isinstance(byte_size, int)
            or byte_size <= 0
            or not isinstance(chunk_size, int)
            or not 1 <= chunk_size <= self._MAX_CHUNK_SIZE_BYTES
            or not isinstance(parts, list)
            or not 1 <= len(parts) <= self._MAX_MANIFEST_PARTS
        ):
            raise ArtifactIntegrityError(
                "O contrato do manifesto de partes é inválido."
            )

        validate_content_addressed_key(object_key, original_sha256)
        expected_part_count = (byte_size + chunk_size - 1) // chunk_size
        if len(parts) != expected_part_count:
            raise ArtifactIntegrityError("A quantidade de partes diverge do manifesto.")

        restored_parts: list[bytes] = []
        for index, part in enumerate(parts):
            if not isinstance(part, dict):
                raise ArtifactIntegrityError("Uma entrada de parte é inválida.")
            part_sha256 = part.get("sha256")
            part_size = part.get("byte_size")
            expected_size = min(chunk_size, byte_size - index * chunk_size)
            if (
                part.get("index") != index
                or not self._is_sha256(part_sha256)
                or part_size != expected_size
                or part.get("object_key")
                != self._chunk_object_key(object_key, index, part_sha256)
            ):
                raise ArtifactIntegrityError("Uma parte diverge do manifesto.")
            chunk = self._download(str(part["object_key"]))
            if (
                len(chunk) != part_size
                or hashlib.sha256(chunk).hexdigest() != part_sha256
            ):
                raise ArtifactIntegrityError(
                    "Os bytes de uma parte divergem do manifesto."
                )
            restored_parts.append(chunk)

        restored = b"".join(restored_parts)
        if (
            len(restored) != byte_size
            or hashlib.sha256(restored).hexdigest() != original_sha256
        ):
            raise ArtifactIntegrityError(
                "O artefato reconstruído diverge do manifesto."
            )
        return restored

    def _upload(self, object_key: str, body: bytes, content_type: str) -> None:
        self.bucket_client.upload(
            path=object_key,
            file=body,
            file_options={
                "content-type": content_type,
                "cache-control": "31536000",
                "upsert": "false",
            },
        )

    def _download(self, object_key: str) -> bytes:
        try:
            value = self.bucket_client.download(object_key)
        except Exception as error:
            raise PersistenceError(
                "O objeto não pôde ser restaurado do Storage."
            ) from error
        if not isinstance(value, bytes):
            raise PersistenceError("O Storage não retornou bytes.")
        return value

    @staticmethod
    def _chunk_object_key(object_key: str, index: int, sha256: str) -> str:
        return f"{object_key}.chunks/{index:06d}-{sha256}.part"

    @staticmethod
    def _is_sha256(value: object) -> bool:
        return (
            isinstance(value, str)
            and len(value) == 64
            and all(character in "0123456789abcdef" for character in value)
        )

    @staticmethod
    def _validate_object_key(object_key: str, expected_sha256: str) -> None:
        validate_content_addressed_key(object_key, expected_sha256)


class FilesystemArtifactObjectStore:
    """Preserva objetos por hash sem sobrescrever bytes existentes."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put_if_absent(
        self,
        *,
        object_key: str,
        body: bytes,
        content_type: str,
        expected_sha256: str,
    ) -> StoredObject:
        del content_type
        validate_content_addressed_key(object_key, expected_sha256)
        actual_hash = hashlib.sha256(body).hexdigest()
        if actual_hash != expected_sha256:
            raise ArtifactIntegrityError("O corpo não corresponde ao SHA-256 esperado.")

        target = self._target(object_key, create_parent=True)
        created = False
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(target, flags, 0o600)
        except FileExistsError:
            pass
        except OSError as error:
            raise PersistenceError("O objeto local não pôde ser criado.") from error
        else:
            created = True
            try:
                with os.fdopen(descriptor, "wb") as file:
                    file.write(body)
                    file.flush()
                    os.fsync(file.fileno())
            except BaseException:
                # Um arquivo parcial permanece visível para que a divergência seja
                # detectada no replay; nunca o substituímos silenciosamente.
                raise

        restored = self.read(object_key)
        restored_hash = hashlib.sha256(restored).hexdigest()
        if restored_hash != expected_sha256:
            raise ArtifactIntegrityError(
                "A chave local já existe com bytes divergentes."
            )
        return StoredObject(
            object_key=object_key,
            sha256=restored_hash,
            byte_size=len(restored),
            created=created,
        )

    def read(self, object_key: str) -> bytes:
        target = self._target(object_key, create_parent=False)
        if target.is_symlink():
            raise PersistenceError("Links simbólicos não são aceitos no acervo local.")
        try:
            return target.read_bytes()
        except OSError as error:
            raise PersistenceError("O objeto local não pôde ser restaurado.") from error

    def _target(self, object_key: str, *, create_parent: bool) -> Path:
        relative = PurePosixPath(object_key)
        target = self.root.joinpath(*relative.parts)
        if create_parent:
            target.parent.mkdir(parents=True, exist_ok=True)
        try:
            resolved_parent = target.parent.resolve(strict=True)
            resolved_parent.relative_to(self.root)
        except (OSError, ValueError) as error:
            raise PersistenceError(
                "A chave de objeto escaparia do diretório local permitido."
            ) from error
        return resolved_parent / target.name


def validate_content_addressed_key(
    object_key: str,
    expected_sha256: str,
) -> None:
    parts = object_key.split("/")
    if (
        not object_key
        or object_key.startswith("/")
        or "\\" in object_key
        or any(part in {"", ".", ".."} for part in parts)
        or len(expected_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha256)
        or expected_sha256 not in object_key
    ):
        raise ValueError("Chave de objeto inválida ou não endereçada por hash.")
