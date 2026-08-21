from __future__ import annotations

import unittest

from barreiras_collectors.collection_control import CollectionOutcome
from barreiras_collectors.commands.collect_cgu_federal_amendment_documents import (
    CGUFederalAmendmentDocumentCollectionSummary,
    build_cgu_document_execution_key,
    execute_controlled_cgu_document_collection,
)


class FakeControl:
    def __init__(self) -> None:
        self.entered = False
        self.completed = None

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        del exc_type, exc_value, traceback
        return False

    def complete(self, **values):
        self.completed = values


class CGUFederalAmendmentDocumentCommandTests(unittest.TestCase):
    def test_execution_key_is_separate_for_each_archive_year(self) -> None:
        environment = {
            "GITHUB_RUN_ID": "31700119397",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_REPOSITORY": "maxsuellbomfim/barreiras-em-dados",
            "GITHUB_WORKFLOW": "Coletar documentos financeiros municipais",
        }
        first = build_cgu_document_execution_key(2024, environment=environment)
        second = build_cgu_document_execution_key(2025, environment=environment)
        self.assertNotEqual(first, second)
        self.assertRegex(
            first,
            r"^cgu-federal-amendment-documents-2024:execution:[0-9a-f]{64}$",
        )

    def test_control_records_complete_and_empty_per_year(self) -> None:
        for documents, expected in (
            (28, CollectionOutcome.COMPLETE),
            (0, CollectionOutcome.EMPTY),
        ):
            control = FakeControl()
            summary = CGUFederalAmendmentDocumentCollectionSummary(
                archive_year=2024,
                documents=documents,
                amendments=5 if documents else 0,
                authors=4 if documents else 0,
                payments=11 if documents else 0,
                archive_bytes=15_625_915,
                inserted_records=documents,
                existing_records=0,
                archive_sha256="a" * 64,
                source_etag='"etag"',
            )
            execute_controlled_cgu_document_collection(
                control=control,  # type: ignore[arg-type]
                operation=lambda result=summary: result,
            )
            self.assertEqual(control.completed["outcome"], expected)
            self.assertEqual(control.completed["observed_records"], documents)
            self.assertEqual(control.completed["checkpoint"]["archive_year"], 2024)


if __name__ == "__main__":
    unittest.main()
