from __future__ import annotations

import unittest

from barreiras_docproc.commands.process_tcm_ba_document_families import (
    batch_exit_code,
    run_batch,
)
from barreiras_docproc.processing import TextArtifact
from barreiras_docproc.tcm_ba_document_families import (
    TcmBaCatalogDocument,
    TcmBaDocumentFamilyPersistResult,
)


def document(suffix: str, category: str) -> TcmBaCatalogDocument:
    return TcmBaCatalogDocument(
        artifact=TextArtifact(
            raw_artifact_id=f"00000000-0000-0000-0000-0000000009{suffix}",
            sha256=suffix * 64,
            object_key=f"tcm-ba/monthly-documents/2021/01/{suffix}.pdf",
        ),
        source_record_key=f"tcm-ba:document:01/2021:{suffix}",
        official_category=category,
    )


class FakeRepository:
    def __init__(self, documents=()) -> None:
        self.documents = tuple(documents)
        self.failures = []

    def pending_documents(self, limit: int):
        self.limit = limit
        return self.documents

    def persist_failure(
        self,
        catalog_document,
        *,
        idempotency_key,
        error_code,
        error_detail,
    ) -> None:
        self.failures.append(
            (catalog_document, idempotency_key, error_code, error_detail)
        )


class FakeService:
    def __init__(self, *, fail_sha: str | None = None) -> None:
        self.fail_sha = fail_sha

    def process(self, catalog_document):
        if catalog_document.artifact.sha256 == self.fail_sha:
            raise RuntimeError("conteúdo sensível que não deve ir ao log")
        family = (
            "unknown"
            if "999" in catalog_document.official_category
            else "contracts_and_amendments"
        )
        return TcmBaDocumentFamilyPersistResult(True, 1, family)


class ProcessTcmBaDocumentFamiliesCommandTests(unittest.TestCase):
    def test_counts_classified_and_unknown_documents(self) -> None:
        repository = FakeRepository(
            (
                document("1", "PCMGE009 - Contratos e aditivos"),
                document("2", "PCMGE999 - Categoria futura"),
            )
        )

        summary = run_batch(
            repository=repository,
            service=FakeService(),
            limit=5,
        )

        self.assertEqual(summary.pending_found, 2)
        self.assertEqual(summary.processed, 2)
        self.assertEqual(summary.classified, 1)
        self.assertEqual(summary.unknown, 1)
        self.assertEqual(summary.failed, 0)
        self.assertEqual(batch_exit_code(summary), 0)

    def test_failure_is_sanitized_and_blocks_batch(self) -> None:
        failing = document("3", "PCMGE009 - Contratos e aditivos")
        repository = FakeRepository((failing,))

        summary = run_batch(
            repository=repository,
            service=FakeService(fail_sha=failing.artifact.sha256),
            limit=5,
        )

        self.assertEqual(summary.failed, 1)
        self.assertEqual(batch_exit_code(summary), 1)
        _document, _key, code, detail = repository.failures[0]
        self.assertEqual(code, "processing_error")
        self.assertEqual(detail, "RuntimeError: processing failure")
        self.assertNotIn("conteúdo sensível", detail)

    def test_empty_queue_is_not_a_failure(self) -> None:
        summary = run_batch(
            repository=FakeRepository(),
            service=FakeService(),
            limit=5,
        )

        self.assertEqual(summary.pending_found, 0)
        self.assertEqual(batch_exit_code(summary), 0)


if __name__ == "__main__":
    unittest.main()
