"""Adaptadores de objetos imutáveis para desenvolvimento e produção."""

from __future__ import annotations

import hashlib
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
    """Usa upload sem upsert e aceita replay somente após verificar os bytes."""

    def __init__(self, bucket_client: SupabaseBucketClient) -> None:
        self.bucket_client = bucket_client

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
        value = self.bucket_client.download(object_key)
        if not isinstance(value, bytes):
            raise PersistenceError("O Storage não retornou bytes.")
        return value

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
