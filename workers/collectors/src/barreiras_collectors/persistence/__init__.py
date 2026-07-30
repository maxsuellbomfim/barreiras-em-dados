"""Persistência auditável para respostas brutas dos coletores."""

from .filesystem import FilesystemCollectionRepository
from .models import (
    ArtifactIntegrityError,
    PersistenceBatch,
    PersistenceResult,
    RawRecordInput,
    RepositoryPersistResult,
    StoredObject,
)
from .service import QueridoDiarioPersistenceService
from .storage import FilesystemArtifactObjectStore

__all__ = [
    "ArtifactIntegrityError",
    "FilesystemArtifactObjectStore",
    "FilesystemCollectionRepository",
    "PersistenceBatch",
    "PersistenceResult",
    "QueridoDiarioPersistenceService",
    "RawRecordInput",
    "RepositoryPersistResult",
    "StoredObject",
]
