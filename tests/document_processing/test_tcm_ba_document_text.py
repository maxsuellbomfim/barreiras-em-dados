from __future__ import annotations

import hashlib
import io
import unittest

from barreiras_docproc.commands.process_tcm_ba_documents import (
    batch_exit_code,
    normalize_artifact_sha256,
)
from barreiras_docproc.processing import ArtifactMismatchError, TextArtifact
from barreiras_docproc.tcm_ba_document_text import TcmBaDocumentTextService


def build_pdf(page_texts: list[str | None]) -> bytes:
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    for text in page_texts:
        page = writer.add_blank_page(width=612, height=792)
        if text is None:
            continue
        content = DecodedStreamObject()
        escaped = text.replace("(", r"\(").replace(")", r"\)")
        content.set_data(
            f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("latin-1")
        )
        page[NameObject("/Contents")] = writer._add_object(content)
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {
                        NameObject("/F1"): DictionaryObject(
                            {
                                NameObject("/Type"): NameObject("/Font"),
                                NameObject("/Subtype"): NameObject("/Type1"),
                                NameObject("/BaseFont"): NameObject("/Helvetica"),
                            }
                        )
                    }
                )
            }
        )
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


class FakeReader:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self, object_key: str) -> bytes:
        return self.body


class FakeRepository:
    def __init__(self) -> None:
        self.persisted = []

    def persist_tcm_document_text(
        self,
        artifact,
        pages,
        *,
        job_type,
        job_idempotency_key,
    ) -> bool:
        self.persisted.append((artifact, pages))
        self.job_type = job_type
        self.job_idempotency_key = job_idempotency_key
        return True


def artifact_for(body: bytes, *, sha256: str | None = None) -> TextArtifact:
    digest = sha256 or hashlib.sha256(body).hexdigest()
    return TextArtifact(
        raw_artifact_id="00000000-0000-0000-0000-000000000901",
        sha256=digest,
        object_key=f"tcm-ba/monthly-documents/2021/01/pdf/sha256/{digest[:2]}/{digest}.pdf",
    )


class TcmBaDocumentTextServiceTests(unittest.TestCase):
    def test_normalizes_and_validates_optional_exact_artifact_hash(self) -> None:
        self.assertIsNone(normalize_artifact_sha256(""))
        self.assertEqual(
            normalize_artifact_sha256(" A" + "B" * 63 + " "),
            "a" + "b" * 63,
        )
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            normalize_artifact_sha256("curto")

    def test_batch_fails_closed_without_pending_pdf_or_after_any_failure(self) -> None:
        self.assertEqual(batch_exit_code(pending_found=5, failed=0), 0)
        self.assertEqual(batch_exit_code(pending_found=0, failed=0), 1)
        self.assertEqual(batch_exit_code(pending_found=5, failed=1), 1)

    def test_persists_every_page_and_marks_scanned_page_for_ocr(self) -> None:
        body = build_pdf(["NOTA DE EMPENHO 123", None])
        repository = FakeRepository()
        artifact = artifact_for(body)

        result = TcmBaDocumentTextService(
            object_reader=FakeReader(body),
            repository=repository,
        ).process(artifact)

        self.assertEqual(result.pages_total, 2)
        self.assertEqual(result.pages_with_embedded_text, 1)
        self.assertEqual(result.pages_awaiting_ocr, 1)
        self.assertTrue(result.job_created)
        persisted_artifact, pages = repository.persisted[0]
        self.assertEqual(persisted_artifact, artifact)
        self.assertEqual(len(pages), 2)
        self.assertIn("NOTA DE EMPENHO 123", pages[0].text or "")
        self.assertIsNone(pages[1].text)
        self.assertEqual(repository.job_type, "tcm_ba_document_text")
        self.assertEqual(len(repository.job_idempotency_key), 64)

    def test_rejects_restored_bytes_with_wrong_hash(self) -> None:
        body = build_pdf(["CONTRATO 1/2021"])
        repository = FakeRepository()
        artifact = artifact_for(body, sha256="0" * 64)

        with self.assertRaises(ArtifactMismatchError):
            TcmBaDocumentTextService(
                object_reader=FakeReader(body),
                repository=repository,
            ).process(artifact)

        self.assertEqual(repository.persisted, [])


if __name__ == "__main__":
    unittest.main()
