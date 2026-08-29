from __future__ import annotations

import unittest

from barreiras_docproc.commands.report_tcm_ba_contract_documents import (
    coverage_exit_code,
)
from barreiras_docproc.tcm_ba_contract_documents import (
    TcmBaContractDocumentCoverage,
)


class ReportTcmBaContractDocumentsCommandTests(unittest.TestCase):
    def test_exit_code_follows_closed_coverage_gate(self) -> None:
        passing = TcmBaContractDocumentCoverage(
            eligible_artifacts=34,
            processed_artifacts=34,
            identified_segments=700,
            unknown_segments=0,
            missing_artifacts=0,
            unknown_only_artifacts=0,
            duplicate_results=0,
            invalid_results=0,
            open_failures=0,
        )
        blocked = TcmBaContractDocumentCoverage(
            eligible_artifacts=34,
            processed_artifacts=33,
            identified_segments=699,
            unknown_segments=1,
            missing_artifacts=1,
            unknown_only_artifacts=1,
            duplicate_results=0,
            invalid_results=0,
            open_failures=0,
        )

        self.assertEqual(coverage_exit_code(passing), 0)
        self.assertEqual(coverage_exit_code(blocked), 1)


if __name__ == "__main__":
    unittest.main()