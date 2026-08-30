from __future__ import annotations

import unittest

from barreiras_docproc.commands.report_tcm_ba_commitments import (
    coverage_exit_code,
)
from barreiras_docproc.tcm_ba_commitments import TcmBaCommitmentCoverage


def coverage(**overrides: int) -> TcmBaCommitmentCoverage:
    values = {
        "eligible_artifacts": 10,
        "processed_artifacts": 10,
        "candidate_results": 2,
        "complete_candidates": 1,
        "incomplete_candidates": 1,
        "zero_candidate_artifacts": 8,
        "missing_artifacts": 0,
        "duplicate_results": 0,
        "invalid_results": 0,
        "open_failures": 0,
    }
    return TcmBaCommitmentCoverage(**(values | overrides))


class ReportTcmBaCommitmentsCommandTests(unittest.TestCase):
    def test_exit_code_follows_closed_coverage_gate(self) -> None:
        self.assertEqual(coverage_exit_code(coverage()), 0)
        self.assertEqual(
            coverage_exit_code(
                coverage(processed_artifacts=9, missing_artifacts=1)
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
