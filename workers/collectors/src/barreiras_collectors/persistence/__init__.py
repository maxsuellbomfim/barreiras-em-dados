"""Persistência auditável para respostas brutas dos coletores."""

from .models import (
    ArtifactIntegrityError,
    PersistenceBatch,
    PersistenceResult,
    RawRecordInput,
    RepositoryPersistResult,
    StoredObject,
)
from .service import QueridoDiarioPersistenceService

__all__ = [
    "ArtifactIntegrityError",
    "PersistenceBatch",
    "PersistenceResult",
    "QueridoDiarioPersistenceService",
    "RawRecordInput",
    "RepositoryPersistResult",
    "StoredObject",
]
