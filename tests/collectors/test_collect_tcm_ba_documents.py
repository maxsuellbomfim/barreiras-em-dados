from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace

from barreiras_collectors.collection_control import CollectionControl
from barreiras_collectors.commands.collect_tcm_ba_documents import (
    execute_tcm_ba_document_batch,
)
from barreiras_collectors.persistence.models import (
    TcmBaDocumentReference,
    TcmBaDocumentSelection,
)


def reference(position=1):
    return TcmBaDocumentReference(
        competence="04/2023",
        expected_total_documents=3,
        document_position=position,
        source_record_key=f"tcm-ba:document:04/2023:key-{position}",
        parent_artifact_id=f"catalog-{position}",
        category="Relatório",
        name=f"documento-{position}.pdf",
        inserted_at="03/05/2023 10:00",
        page_number=1,
        download_form_id=f"form:{position}",
    )


class FakeRepository:
    def __init__(self, selection):
        self.selection = selection
        self.started = []
        self.completed = []
        self.failed = []
        self.selection_calls = []

    def start_controlled_run(self, **values):
        self.started.append(values)
        return "download-run-1"

    def complete_controlled_run(self, **values):
        self.completed.append(values)

    def fail_controlled_run(self, **values):
        self.failed.append(values)

    def tcm_ba_document_references(self, **values):
        self.selection_calls.append(values)
        return self.selection


class FakeClient:
    def __init__(self):
        self.calls = []

    def fetch_monthly_document(self, **values):
        self.calls.append(values)
        return SimpleNamespace(position=values["document_position"])


class FakeService:
    def __init__(self):
        self.calls = []

    def persist(self, download, *, reference, collection_run_id):
        self.calls.append((download, reference, collection_run_id))
        return SimpleNamespace(pdf_sha256=f"hash-{reference.document_position}")


def control(repository):
    return CollectionControl(
        repository=repository,
        source_code="tcm-ba",
        endpoint_code="prestacoes-contas-mensais",
        idempotency_key="tcm-documents:test:123456",
        collector_version="test/1.0",
        partition_key="documents:2023-04",
        period_start=date(2023, 4, 1),
        period_end=date(2023, 4, 30),
    )


class CollectTcmBaDocumentsTests(unittest.TestCase):
    def test_partial_batch_preserves_cumulative_progress(self) -> None:
        selection = TcmBaDocumentSelection(
            competence="04/2023",
            expected_total_documents=3,
            preserved_documents=1,
            pending_documents=2,
            references=(reference(2),),
        )
        repository = FakeRepository(selection)
        client = FakeClient()
        service = FakeService()

        summary = execute_tcm_ba_document_batch(
            competence="04/2023",
            max_documents=1,
            category_code="PCMGE015",
            repository=repository,
            service=service,
            client=client,
            control=control(repository),
        )

        self.assertEqual(summary.preserved_after, 2)
        self.assertEqual(summary.remaining_documents, 1)
        self.assertEqual(repository.completed[0]["outcome"], "partial")
        self.assertEqual(repository.completed[0]["observed_records"], 2)
        self.assertEqual(service.calls[0][2], "download-run-1")
        self.assertEqual(client.calls[0]["expected_total_documents"], 3)
        self.assertEqual(client.calls[0]["expected_document"].name, "documento-2.pdf")
        self.assertEqual(
            repository.selection_calls[0]["category_code"],
            "PCMGE015",
        )

    def test_final_batch_closes_month_only_after_last_pdf(self) -> None:
        final_reference = reference(3)
        selection = TcmBaDocumentSelection(
            competence="04/2023",
            expected_total_documents=3,
            preserved_documents=2,
            pending_documents=1,
            references=(final_reference,),
        )
        repository = FakeRepository(selection)

        summary = execute_tcm_ba_document_batch(
            competence="04/2023",
            max_documents=5,
            repository=repository,
            service=FakeService(),
            client=FakeClient(),
            control=control(repository),
        )

        self.assertEqual(summary.preserved_after, 3)
        self.assertEqual(summary.remaining_documents, 0)
        self.assertEqual(repository.completed[0]["outcome"], "complete")
        self.assertEqual(repository.completed[0]["observed_records"], 3)

    def test_operational_batch_accepts_ten_documents(self) -> None:
        selection = TcmBaDocumentSelection(
            competence="04/2023",
            expected_total_documents=10,
            preserved_documents=0,
            pending_documents=10,
            references=tuple(reference(position) for position in range(1, 11)),
        )
        repository = FakeRepository(selection)

        summary = execute_tcm_ba_document_batch(
            competence="04/2023",
            max_documents=10,
            repository=repository,
            service=FakeService(),
            client=FakeClient(),
            control=control(repository),
        )

        self.assertEqual(summary.downloaded_documents, 10)
        self.assertEqual(summary.preserved_after, 10)
        self.assertEqual(summary.remaining_documents, 0)
        self.assertEqual(repository.completed[0]["outcome"], "complete")

    def test_operational_batch_rejects_more_than_ten_documents(self) -> None:
        selection = TcmBaDocumentSelection(
            competence="04/2023",
            expected_total_documents=3,
            preserved_documents=3,
            pending_documents=0,
            references=(),
        )
        repository = FakeRepository(selection)

        with self.assertRaisesRegex(ValueError, "entre 1 e 10"):
            execute_tcm_ba_document_batch(
                competence="04/2023",
                max_documents=11,
                repository=repository,
                service=FakeService(),
                client=FakeClient(),
                control=control(repository),
            )

    def test_already_complete_month_makes_no_http_request(self) -> None:
        selection = TcmBaDocumentSelection(
            competence="04/2023",
            expected_total_documents=3,
            preserved_documents=3,
            pending_documents=0,
            references=(),
        )
        repository = FakeRepository(selection)
        client = FakeClient()

        summary = execute_tcm_ba_document_batch(
            competence="04/2023",
            max_documents=1,
            repository=repository,
            service=FakeService(),
            client=client,
            control=control(repository),
        )

        self.assertEqual(summary.downloaded_documents, 0)
        self.assertEqual(client.calls, [])
        self.assertEqual(repository.completed[0]["outcome"], "complete")


if __name__ == "__main__":
    unittest.main()
