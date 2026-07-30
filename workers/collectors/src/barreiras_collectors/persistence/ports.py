"""Portas pequenas para manter Storage e banco substituíveis em testes."""

from __future__ import annotations

from typing import Protocol

from .models import (
    PersistenceBatch,
    RepositoryPersistResult,
    StoredObject,
)


class ArtifactObjectStore(Protocol):
    def put_if_absent(
        self,
        *,
        object_key: str,
        body: bytes,
        content_type: str,
        expected_sha256: str,
    ) -> StoredObject: ...

    def read(self, object_key: str) -> bytes: ...


class CollectionRepository(Protocol):
    def persist(self, batch: PersistenceBatch) -> RepositoryPersistResult: ...
