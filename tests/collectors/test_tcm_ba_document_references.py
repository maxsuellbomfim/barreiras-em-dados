from __future__ import annotations

import unittest

from barreiras_collectors.persistence.models import PersistenceContractError
from barreiras_collectors.persistence.postgres import PostgresCollectionRepository


class QueryResult:
    def __init__(self, *, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class SequenceConnection:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []
        self.closed = False

    def execute(self, query, params=None):
        self.calls.append((query, params))
        return self.results.pop(0)

    def close(self):
        self.closed = True


def complete_catalog(*, documents=11):
    return QueryResult(
        row={
            "source_endpoint_id": "endpoint-1",
            "observed_records": documents,
            "started_at": "2026-08-28T10:00:00Z",
            "completed_at": "2026-08-28T11:00:00Z",
        }
    )


def consistent_count(*, documents=11, preserved=0):
    return QueryResult(
        row={
            "documents": documents,
            "unique_keys": documents,
            "unique_positions": documents,
            "first_position": 1,
            "last_position": documents,
            "preserved_documents": preserved,
        }
    )


class TcmBaDocumentReferenceTests(unittest.TestCase):
    def test_returns_exact_pending_reference_from_complete_catalog(self) -> None:
        connection = SequenceConnection(
            [
                complete_catalog(),
                consistent_count(),
                QueryResult(
                    rows=[
                        {
                            "source_record_key": "tcm-ba:document:04/2023:abc",
                            "parent_artifact_id": "catalog-artifact-1",
                            "record_index": 0,
                            "payload": {
                                "category": "Relatório",
                                "name": "documento.pdf",
                                "inserted_at": "03/05/2023 10:00",
                                "page_number": 1,
                                "download_form_id": "form:download",
                            },
                        }
                    ]
                ),
            ]
        )

        selection = PostgresCollectionRepository(
            lambda: connection
        ).tcm_ba_document_references(competence="04/2023", limit=1)

        self.assertEqual(selection.expected_total_documents, 11)
        self.assertEqual(selection.preserved_documents, 0)
        self.assertEqual(selection.pending_documents, 11)
        self.assertEqual(len(selection.references), 1)
        self.assertEqual(selection.references[0].document_position, 1)
        self.assertEqual(selection.references[0].expected_total_documents, 11)
        self.assertEqual(connection.calls[0][1], ("competence:2023-04",))
        self.assertEqual(
            connection.calls[2][1],
            (
                "endpoint-1",
                "2026-08-28T10:00:00Z",
                "2026-08-28T11:00:00Z",
                "04/2023",
                1,
            ),
        )
        self.assertIn("ranked_artifacts", connection.calls[2][0].lower())
        self.assertIn("child_run.started_at", connection.calls[2][0].lower())
        self.assertNotIn(
            "artifact.collection_run_id = %s",
            connection.calls[2][0].lower(),
        )
        self.assertIn("not exists", connection.calls[2][0].lower())
        self.assertIn("tcm-ba-monthly-document", connection.calls[2][0])
        self.assertTrue(connection.closed)

    def test_refuses_month_without_complete_coverage(self) -> None:
        connection = SequenceConnection([QueryResult(row=None)])

        with self.assertRaisesRegex(PersistenceContractError, "cobertura completa"):
            PostgresCollectionRepository(lambda: connection).tcm_ba_document_references(
                competence="04/2023", limit=1
            )

        self.assertEqual(len(connection.calls), 1)
        self.assertTrue(connection.closed)

    def test_refuses_catalog_with_missing_or_duplicate_positions(self) -> None:
        connection = SequenceConnection(
            [complete_catalog(), consistent_count(documents=10)]
        )

        with self.assertRaisesRegex(PersistenceContractError, "divergem"):
            PostgresCollectionRepository(lambda: connection).tcm_ba_document_references(
                competence="04/2023", limit=1
            )

        self.assertEqual(len(connection.calls), 2)
        self.assertTrue(connection.closed)

    def test_refuses_invalid_period_and_unsafe_batch_size(self) -> None:
        repository = PostgresCollectionRepository(
            lambda: self.fail("não deve abrir conexão")
        )

        with self.assertRaises(ValueError):
            repository.tcm_ba_document_references(competence="2023-04", limit=1)
        with self.assertRaises(ValueError):
            repository.tcm_ba_document_references(competence="04/2023", limit=6)


if __name__ == "__main__":
    unittest.main()
