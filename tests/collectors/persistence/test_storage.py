from __future__ import annotations

import hashlib
import unittest

from barreiras_collectors.persistence.models import ArtifactIntegrityError
from barreiras_collectors.persistence.storage import SupabaseStorageObjectStore


class FakeBucket:
    def __init__(self, allowed_content_types: set[str] | None = None) -> None:
        self.objects: dict[str, bytes] = {}
        self.uploaded_sizes: list[int] = []
        self.allowed_content_types = allowed_content_types

    def upload(
        self,
        *,
        path: str,
        file: bytes,
        file_options: dict[str, str],
    ) -> object:
        if file_options["upsert"] != "false":
            raise AssertionError("O teste exige objetos imutáveis.")
        if (
            self.allowed_content_types is not None
            and file_options["content-type"] not in self.allowed_content_types
        ):
            raise RuntimeError("invalid_mime_type")
        if path in self.objects:
            raise RuntimeError("Duplicate")
        self.objects[path] = file
        self.uploaded_sizes.append(len(file))
        return {"path": path}

    def download(self, path: str) -> bytes:
        return self.objects[path]


class SupabaseStorageObjectStoreTests(unittest.TestCase):
    def test_chunk_manifest_uses_a_mime_type_allowed_by_the_bucket(self) -> None:
        bucket = FakeBucket(
            allowed_content_types={"application/json", "application/octet-stream"}
        )
        store = SupabaseStorageObjectStore(bucket, chunk_size_bytes=16)
        body = b"pdf-oficial-grande-" * 8
        digest = hashlib.sha256(body).hexdigest()
        object_key = f"querido-diario/documents/sha256/{digest[:2]}/{digest}.pdf"

        stored = store.put_if_absent(
            object_key=object_key,
            body=body,
            content_type="application/pdf",
            expected_sha256=digest,
        )

        self.assertTrue(stored.created)
        self.assertEqual(store.read(object_key), body)

    def test_existing_small_object_remains_backward_compatible(self) -> None:
        bucket = FakeBucket()
        store = SupabaseStorageObjectStore(bucket, chunk_size_bytes=64)
        body = b"objeto-preservado-antes-do-formato-segmentado"
        digest = hashlib.sha256(body).hexdigest()
        object_key = f"querido-diario/documents/sha256/{digest[:2]}/{digest}.txt"
        bucket.objects[object_key] = body

        stored = store.put_if_absent(
            object_key=object_key,
            body=body,
            content_type="text/plain",
            expected_sha256=digest,
        )

        self.assertFalse(stored.created)
        self.assertEqual(store.read(object_key), body)

    def test_large_object_is_chunked_and_restored_as_original_bytes(self) -> None:
        bucket = FakeBucket()
        store = SupabaseStorageObjectStore(bucket, chunk_size_bytes=16)
        body = b"documento-oficial-grande-" * 4
        digest = hashlib.sha256(body).hexdigest()
        object_key = f"querido-diario/documents/sha256/{digest[:2]}/{digest}.pdf"

        stored = store.put_if_absent(
            object_key=object_key,
            body=body,
            content_type="application/pdf",
            expected_sha256=digest,
        )

        self.assertTrue(stored.created)
        self.assertEqual(stored.sha256, digest)
        self.assertEqual(stored.byte_size, len(body))
        self.assertEqual(store.read(object_key), body)
        self.assertNotEqual(bucket.objects[object_key], body)
        self.assertGreater(len(bucket.objects), 2)
        chunk_sizes = [
            len(value)
            for key, value in bucket.objects.items()
            if key.startswith(f"{object_key}.chunks/")
        ]
        self.assertTrue(chunk_sizes)
        self.assertTrue(all(size <= 16 for size in chunk_sizes))

    def test_large_object_replay_reuses_verified_manifest_and_parts(self) -> None:
        bucket = FakeBucket()
        store = SupabaseStorageObjectStore(bucket, chunk_size_bytes=16)
        body = b"edicao-do-diario-" * 8
        digest = hashlib.sha256(body).hexdigest()
        object_key = f"querido-diario/documents/sha256/{digest[:2]}/{digest}.pdf"

        first = store.put_if_absent(
            object_key=object_key,
            body=body,
            content_type="application/pdf",
            expected_sha256=digest,
        )
        object_count = len(bucket.objects)
        second = store.put_if_absent(
            object_key=object_key,
            body=body,
            content_type="application/pdf",
            expected_sha256=digest,
        )

        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(len(bucket.objects), object_count)
        self.assertEqual(store.read(object_key), body)

    def test_tampered_chunk_is_rejected_during_restoration(self) -> None:
        bucket = FakeBucket()
        store = SupabaseStorageObjectStore(bucket, chunk_size_bytes=16)
        body = b"conteudo-oficial-" * 8
        digest = hashlib.sha256(body).hexdigest()
        object_key = f"querido-diario/documents/sha256/{digest[:2]}/{digest}.pdf"
        store.put_if_absent(
            object_key=object_key,
            body=body,
            content_type="application/pdf",
            expected_sha256=digest,
        )
        chunk_key = next(
            key for key in bucket.objects if key.startswith(f"{object_key}.chunks/")
        )
        bucket.objects[chunk_key] = b"parte-adulterada"

        with self.assertRaises(ArtifactIntegrityError):
            store.read(object_key)


if __name__ == "__main__":
    unittest.main()
