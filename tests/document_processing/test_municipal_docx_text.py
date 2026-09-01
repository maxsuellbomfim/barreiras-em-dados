from __future__ import annotations

import hashlib
import io
import unittest
import zipfile

from barreiras_docproc.commands.process_municipal_docx import batch_exit_code
from barreiras_docproc.municipal_docx_text import MunicipalDocxTextService
from barreiras_docproc.processing import ArtifactMismatchError, TextArtifact

WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def build_docx(text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
              <Default Extension="xml" ContentType="application/xml"/>
            </Types>""",
        )
        archive.writestr(
            "word/document.xml",
            f"""<w:document xmlns:w="{WORD_NAMESPACE}">
              <w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>
            </w:document>""",
        )
    return buffer.getvalue()


class FakeReader:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self, object_key: str) -> bytes:
        return self.body


class FakeRepository:
    def __init__(self) -> None:
        self.persisted = []

    def persist_municipal_docx_text(
        self,
        artifact,
        pages,
        *,
        job_type,
        job_idempotency_key,
    ) -> bool:
        self.persisted.append((artifact, pages, job_type, job_idempotency_key))
        return True


def artifact_for(body: bytes, *, sha256: str | None = None) -> TextArtifact:
    digest = sha256 or hashlib.sha256(body).hexdigest()
    return TextArtifact(
        raw_artifact_id="00000000-0000-0000-0000-000000000911",
        sha256=digest,
        object_key=(
            "municipal-transparency/documents/sha256/"
            f"{digest[:2]}/{digest}.docx"
        ),
    )


class MunicipalDocxTextServiceTests(unittest.TestCase):
    def test_persists_one_logical_text_unit_with_hash_and_version(self) -> None:
        body = build_docx("Lei municipal nº 1.234")
        repository = FakeRepository()
        artifact = artifact_for(body)

        result = MunicipalDocxTextService(
            object_reader=FakeReader(body),
            repository=repository,
        ).process(artifact)

        self.assertTrue(result.job_created)
        self.assertEqual(result.text_characters, 22)
        self.assertEqual(result.blocks_total, 1)
        persisted_artifact, pages, job_type, idempotency_key = repository.persisted[0]
        self.assertEqual(persisted_artifact, artifact)
        self.assertEqual(job_type, "municipal_docx_text")
        self.assertEqual(len(idempotency_key), 64)
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].page_number, 1)
        self.assertEqual(pages[0].text, "Lei municipal nº 1.234")
        self.assertEqual(
            pages[0].sha256,
            hashlib.sha256("Lei municipal nº 1.234".encode()).hexdigest(),
        )

    def test_rejects_restored_docx_with_wrong_hash_before_persisting(self) -> None:
        body = build_docx("Lei municipal nº 1.234")
        repository = FakeRepository()
        artifact = artifact_for(body, sha256="0" * 64)

        with self.assertRaises(ArtifactMismatchError):
            MunicipalDocxTextService(
                object_reader=FakeReader(body),
                repository=repository,
            ).process(artifact)

        self.assertEqual(repository.persisted, [])

    def test_batch_requires_proven_coverage_and_fails_on_any_error(self) -> None:
        self.assertEqual(
            batch_exit_code(failed=0, processed_total=4, minimum_total=4),
            0,
        )
        self.assertEqual(
            batch_exit_code(failed=0, processed_total=0, minimum_total=4),
            1,
        )
        self.assertEqual(
            batch_exit_code(failed=1, processed_total=4, minimum_total=4),
            1,
        )


if __name__ == "__main__":
    unittest.main()
