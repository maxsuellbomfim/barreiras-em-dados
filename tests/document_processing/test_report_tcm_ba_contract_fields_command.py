from __future__ import annotations

import unittest

from barreiras_docproc.commands.report_tcm_ba_contract_fields import (
    coverage_exit_code,
)
from barreiras_docproc.tcm_ba_contract_fields import TcmBaContractFieldCoverage


class ReportTcmBaContractFieldsCommandTests(unittest.TestCase):
    def test_exit_code_follows_closed_segment_reconciliation(self) -> None:
        passing = TcmBaContractFieldCoverage(
            eligible_artifacts=34,
            processed_artifacts=34,
            eligible_segments=449,
            processed_segments=449,
            observed_fields=1200,
            no_fields_observed=3,
            missing_segments=0,
            duplicate_results=0,
            invalid_results=0,
            open_failures=0,
        )
        blocked = TcmBaContractFieldCoverage(
            eligible_artifacts=34,
            processed_artifacts=34,
            eligible_segments=449,
            processed_segments=448,
            observed_fields=1200,
            no_fields_observed=3,
            missing_segments=1,
            duplicate_results=0,
            invalid_results=0,
            open_failures=0,
        )

        self.assertEqual(coverage_exit_code(passing), 0)
        self.assertEqual(coverage_exit_code(blocked), 1)


if __name__ == "__main__":
    unittest.main()
