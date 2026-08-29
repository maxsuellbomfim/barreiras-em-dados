from __future__ import annotations

import unittest

from barreiras_docproc.postgres import PostgresExtractionRepository
from barreiras_docproc.tcm_ba_document_text import (
    TcmBaDocumentProcessingReport,
)


class SingleRowResult:
    def __init__(self, row) -> None:
        self.row = row

    def fetchone(self):
        row, self.row = self.row, None
        return row


class ReportConnection:
    def __init__(self, row) -> None:
        self.row = row
        self.query = ""
        self.params = None

    def execute(self, query, params=None):
        self.query = " ".join(query.split())
        self.params = params
        return SingleRowResult(self.row)

    def close(self):
        return None


def valid_row() -> dict[str, int]:
    return {
        "total_pdfs": 53,
        "pdfs_with_pages": 5,
        "pages_total": 12,
        "pages_embedded": 7,
        "pages_ocr": 4,
        "pages_awaiting_ocr": 1,
        "failed_jobs": 0,
    }


class TcmBaDocumentProcessingReportTests(unittest.TestCase):
    def test_repository_reports_current_parser_and_tcm_ocr_only(self) -> None:
        connection = ReportConnection(valid_row())
        repository = PostgresExtractionRepository(
            lambda: connection  # type: ignore[arg-type]
        )

        report = repository.tcm_ba_document_processing_report()

        self.assertTrue(report.approved)
        self.assertEqual(report.total_pdfs, 53)
        self.assertIn("tcm-ba-monthly-document", connection.query)
        self.assertIn("tcm_ba_document_text", connection.query)
        self.assertEqual(len(connection.params), 2)

    def test_approval_rejects_missing_pages_divergence_and_failed_jobs(self) -> None:
        changes_list = (
            {
                "pdfs_with_pages": 0,
                "pages_total": 0,
                "pages_embedded": 0,
                "pages_ocr": 0,
                "pages_awaiting_ocr": 0,
            },
            {"pages_awaiting_ocr": 2},
            {"failed_jobs": 1},
        )
        for changes in changes_list:
            report = TcmBaDocumentProcessingReport(**(valid_row() | changes))
            self.assertFalse(report.approved)


if __name__ == "__main__":
    unittest.main()
