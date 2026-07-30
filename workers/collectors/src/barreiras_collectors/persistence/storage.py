"""Adaptador mínimo para um bucket do Supabase Storage."""

from __future__ import annotations

import hashlib
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
        if (
            not object_key
            or object_key.startswith("/")
            or "\\" in object_key
            or ".." in object_key.split("/")
            or expected_sha256 not in object_key
        ):
            raise ValueError("Chave de objeto inválida ou não endereçada por hash.")
