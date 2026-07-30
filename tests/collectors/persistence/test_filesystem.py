from __future__ import annotations

import hashlib
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from barreiras_collectors.persistence.filesystem import (
    FilesystemCollectionRepository,
)
from barreiras_collectors.persistence.models import (
    ArtifactIntegrityError,
    PersistenceContractError,
)
from barreiras_collectors.persistence.service import (
    QueridoDiarioPersistenceService,
)
from barreiras_collectors.persistence.storage import (
    FilesystemArtifactObjectStore,
)

from .test_service import make_page


class FilesystemPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.service = QueridoDiarioPersistenceService(
            object_store=FilesystemArtifactObjectStore(self.root / "objects"),
            repository=FilesystemCollectionRepository(self.root / "manifests"),
        )

    def test_replay_preserves_one_object_and_one_manifest(self) -> None:
        page = make_page()

        first = self.service.persist(page)
        second = self.service.persist(page)

        object_path = self.root / "objects" / Path(first.object_key)
        manifests = tuple((self.root / "manifests").rglob("*.json"))
        self.assertTrue(first.object_created)
        self.assertFalse(second.object_created)
        self.assertEqual(object_path.read_bytes(), page.raw_body)
        self.assertEqual(len(manifests), 1)
        self.assertEqual(first.inserted_records, 2)
        self.assertEqual(second.existing_records, 2)

    def test_detects_object_changed_after_preservation(self) -> None:
        page = make_page()
        result = self.service.persist(page)
        object_path = self.root / "objects" / Path(result.object_key)
        object_path.write_bytes(b"alterado")

        with self.assertRaises(ArtifactIntegrityError):
            self.service.persist(page)

    def test_detects_manifest_changed_after_preservation(self) -> None:
        page = make_page()
        self.service.persist(page)
        manifest = next((self.root / "manifests").rglob("*.json"))
        manifest.write_bytes(b"{}\n")

        with self.assertRaises(PersistenceContractError):
            self.service.persist(page)

    def test_same_run_key_cannot_receive_different_manifest(self) -> None:
        page = make_page()
        self.service.persist(page)
        changed_observation = replace(
            page,
            request_url=f"{page.request_url}#changed",
        )

        with self.assertRaises(PersistenceContractError):
            self.service.persist(changed_observation)

    def test_new_parser_version_adds_manifest_without_copying_object(self) -> None:
        page = make_page()
        first = self.service.persist(page)
        new_parser_service = QueridoDiarioPersistenceService(
            object_store=FilesystemArtifactObjectStore(self.root / "objects"),
            repository=FilesystemCollectionRepository(self.root / "manifests"),
            parser_version="querido-diario-gazette-page/2.0.0",
        )

        second = new_parser_service.persist(page)

        self.assertTrue(first.object_created)
        self.assertFalse(second.object_created)
        self.assertEqual(len(tuple((self.root / "objects").rglob("*.json"))), 1)
        self.assertEqual(len(tuple((self.root / "manifests").rglob("*.json"))), 2)
        self.assertEqual(second.inserted_records, 2)

    def test_rejects_path_traversal_even_when_key_contains_hash(self) -> None:
        body = b"conteudo"
        digest = hashlib.sha256(body).hexdigest()
        store = FilesystemArtifactObjectStore(self.root / "objects")

        with self.assertRaises(ValueError):
            store.put_if_absent(
                object_key=f"../{digest}.json",
                body=body,
                content_type="application/json",
                expected_sha256=digest,
            )


if __name__ == "__main__":
    unittest.main()
