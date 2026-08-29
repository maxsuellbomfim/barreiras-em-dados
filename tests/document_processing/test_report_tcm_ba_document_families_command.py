from __future__ import annotations

import unittest

from barreiras_docproc.commands.report_tcm_ba_document_families import (
    coverage_exit_code,
)
from barreiras_docproc.tcm_ba_document_families import (
    TcmBaDocumentFamilyCoverage,
)


def coverage(**overrides: int) -> TcmBaDocumentFamilyCoverage:
    values = {
        "preserved_documents": 68,
        "classified_documents": 68,
        "unknown_documents": 0,
        "missing_documents": 0,
        "duplicate_results": 0,
        "invalid_results": 0,
        "open_failures": 0,
    }
    values.update(overrides)
    return TcmBaDocumentFamilyCoverage(**values)


class ReportTcmBaDocumentFamiliesCommandTests(unittest.TestCase):
    def test_complete_non_empty_coverage_passes(self) -> None:
        self.assertEqual(coverage_exit_code(coverage()), 0)

    def test_unknown_is_explicit_but_does_not_break_lineage_coverage(self) -> None:
        self.assertEqual(
            coverage_exit_code(
                coverage(classified_documents=67, unknown_documents=1)
            ),
            0,
        )

    def test_empty_missing_duplicate_invalid_or_failed_coverage_blocks(self) -> None:
        invalid = (
            coverage(preserved_documents=0, classified_documents=0),
            coverage(classified_documents=67, missing_documents=1),
            coverage(duplicate_results=1),
            coverage(invalid_results=1),
            coverage(open_failures=1),
        )

        for snapshot in invalid:
            with self.subTest(snapshot=snapshot):
                self.assertEqual(coverage_exit_code(snapshot), 1)


if __name__ == "__main__":
    unittest.main()