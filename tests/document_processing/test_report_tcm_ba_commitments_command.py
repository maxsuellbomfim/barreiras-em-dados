from __future__ import annotations

import unittest

from barreiras_docproc.commands.report_tcm_ba_commitments import (
    coverage_exit_code,
    field_breakdown_matches_coverage,
    field_breakdown_payload,
)
from barreiras_docproc.tcm_ba_commitments import (
    TcmBaCommitmentCoverage,
    TcmBaCommitmentFieldBreakdown,
    TcmBaCommitmentMissingFieldGroup,
)


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
            coverage_exit_code(coverage(processed_artifacts=9, missing_artifacts=1)),
            1,
        )

    def test_breakdown_must_reconcile_candidate_and_complete_totals(self) -> None:
        valid = TcmBaCommitmentFieldBreakdown(
            total_candidates=2,
            complete_candidates=1,
            spatial_budget_allocations=1,
            spatial_issue_dates=0,
            spatial_amounts=1,
            spatial_creditor_names=1,
            invalid_spatial_evidence=0,
            missing_issue_date=0,
            missing_creditor_name=0,
            missing_amount_text=0,
            missing_budget_allocation=1,
            groups=(
                TcmBaCommitmentMissingFieldGroup((), 1),
                TcmBaCommitmentMissingFieldGroup(("budget_allocation",), 1),
            ),
        )

        self.assertTrue(field_breakdown_matches_coverage(coverage(), valid))
        self.assertFalse(
            field_breakdown_matches_coverage(
                coverage(),
                TcmBaCommitmentFieldBreakdown(
                    **(valid.__dict__ | {"total_candidates": 1}),
                ),
            )
        )
        self.assertFalse(
            field_breakdown_matches_coverage(
                coverage(),
                TcmBaCommitmentFieldBreakdown(
                    **(valid.__dict__ | {"complete_candidates": 0}),
                ),
            )
        )
        self.assertFalse(
            field_breakdown_matches_coverage(
                coverage(),
                TcmBaCommitmentFieldBreakdown(
                    **(valid.__dict__ | {"invalid_spatial_evidence": 1}),
                ),
            )
        )

    def test_field_breakdown_payload_contains_only_aggregate_counts(self) -> None:
        breakdown = TcmBaCommitmentFieldBreakdown(
            total_candidates=98,
            complete_candidates=4,
            spatial_budget_allocations=13,
            spatial_issue_dates=0,
            spatial_amounts=37,
            spatial_creditor_names=47,
            invalid_spatial_evidence=0,
            missing_issue_date=5,
            missing_creditor_name=9,
            missing_amount_text=9,
            missing_budget_allocation=80,
            groups=(
                TcmBaCommitmentMissingFieldGroup(
                    missing_fields=("budget_allocation",),
                    candidates=80,
                ),
                TcmBaCommitmentMissingFieldGroup(
                    missing_fields=(),
                    candidates=4,
                ),
            ),
        )

        payload = field_breakdown_payload(breakdown)

        self.assertEqual(payload["total_candidates"], 98)
        self.assertEqual(payload["spatial_budget_allocations"], 13)
        self.assertEqual(payload["invalid_spatial_evidence"], 0)
        self.assertEqual(
            payload["spatial_field_counts"],
            {
                "issue_date": 0,
                "creditor_name": 47,
                "amount_text": 37,
                "budget_allocation": 13,
            },
        )
        self.assertEqual(
            payload["missing_field_counts"],
            {
                "issue_date": 5,
                "creditor_name": 9,
                "amount_text": 9,
                "budget_allocation": 80,
            },
        )
        self.assertEqual(
            payload["missing_combinations"][0],
            {"missing_fields": ["budget_allocation"], "candidates": 80},
        )


if __name__ == "__main__":
    unittest.main()
