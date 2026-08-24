from __future__ import annotations

import unittest
from dataclasses import replace

from barreiras_normalization.siconfi_annual_totals_repository import (
    SiconfiAnnualPersistResult,
)

from tests.normalization.test_siconfi_annual_totals_repository import _snapshot


class _Repository:
    def __init__(self, snapshots) -> None:
        self.snapshots = tuple(snapshots)
        self.failures = []

    def pending_snapshots(self, limit):
        return self.snapshots[:limit]

    def persist_totals(self, _snapshot_value, totals):
        return SiconfiAnnualPersistResult(True, len(totals), 0)

    def persist_failure(self, target, **kwargs):
        self.failures.append((target, kwargs))


class SiconfiAnnualTotalsCommandTests(unittest.TestCase):
    def test_invalid_year_does_not_block_valid_year(self) -> None:
        from barreiras_normalization.commands.process_siconfi_annual_totals import (
            run_batch,
        )

        valid = _snapshot()
        invalid = replace(valid, fiscal_year=2024, rows=valid.rows[:-1])
        repository = _Repository([invalid, valid])

        result = run_batch(repository=repository, limit=10)

        self.assertEqual(result.pending_found, 2)
        self.assertEqual(result.processed, 1)
        self.assertEqual(result.failed, 1)
        self.assertEqual(result.totals_inserted, 7)
        self.assertEqual(len(repository.failures), 1)
        self.assertEqual(repository.failures[0][1]["error_code"], "parser_contract")


if __name__ == "__main__":
    unittest.main()
