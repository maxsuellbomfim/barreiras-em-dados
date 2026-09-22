import unittest
from dataclasses import replace

from barreiras_collectors.commands.collect_pncp_contratos import (
    PncpContratosCollectionSummary,
)


class ContractExitStatusTests(unittest.TestCase):
    def test_only_verified_current_batch_is_a_coverage_warning(self):
        summary = PncpContratosCollectionSummary(
            1, 0, 0, 0, False, (), None, None,
            retry_controls=("purchase", "inherited"),
            selected_query_controls=("purchase",),
            control_observations=({
                "control": "purchase", "state": "awaiting_source_publication",
                "response_evidence": {"raw_artifact_id": "preserved"},
            },),
        )
        self.assertEqual(summary.exit_status, 2)
        for change in (
            {"control_observations": ()},
            {"selected_query_controls": ("purchase", "missing")},
            {"control_observations": ({"control": "purchase", "state": "partial"},)},
            {"contract_pages_truncated_controls": ("purchase",)},
        ):
            self.assertEqual(replace(summary, **change).exit_status, 1)
        self.assertEqual(replace(summary, retry_controls=()).exit_status, 0)
