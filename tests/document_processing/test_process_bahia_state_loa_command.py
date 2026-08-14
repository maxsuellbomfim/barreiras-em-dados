from __future__ import annotations

import unittest

from barreiras_docproc.bahia_state_loa_processing import (
    BahiaStateLoaArtifact,
    BahiaStateLoaPersistResult,
    LoaIncompleteTextError,
)
from barreiras_docproc.commands.process_bahia_state_loa import run_batch


def artifact(year: int) -> BahiaStateLoaArtifact:
    return BahiaStateLoaArtifact(
        raw_artifact_id=f"00000000-0000-0000-0000-{year:012d}",
        raw_record_id=f"00000000-0000-0000-0001-{year:012d}",
        sha256=str(year).zfill(64),
        object_key=f"bahia/loa-emendas-estaduais/{year}/document.pdf",
        fiscal_year=year,
        annex_code="I" if year == 2026 else "III",
        source_url=f"https://www.ba.gov.br/seplan/loa-{year}.pdf",
    )


class FakeRepository:
    def __init__(self, artifacts) -> None:
        self.artifacts = tuple(artifacts)
        self.failures = []

    def pending_artifacts(self, limit: int):
        return self.artifacts[:limit]

    def persist_failure(self, target, **kwargs) -> None:
        self.failures.append((target, kwargs))


class FakeService:
    def process(self, target):
        if target.fiscal_year == 2024:
            raise LoaIncompleteTextError("formato mudou")
        return BahiaStateLoaPersistResult(
            True,
            target.fiscal_year - 2020,
            2,
        )


class ProcessBahiaStateLoaCommandTests(unittest.TestCase):
    def test_one_invalid_year_is_audited_without_losing_other_years(self) -> None:
        repository = FakeRepository([artifact(2024), artifact(2025)])

        summary = run_batch(
            repository=repository,  # type: ignore[arg-type]
            service=FakeService(),  # type: ignore[arg-type]
            limit=5,
        )

        self.assertEqual(summary.pending_found, 2)
        self.assertEqual(summary.processed, 1)
        self.assertEqual(summary.failed, 1)
        self.assertEqual(summary.results_inserted, 5)
        self.assertEqual(summary.scope_rows_inserted, 2)
        self.assertEqual(len(repository.failures), 1)
        self.assertEqual(repository.failures[0][1]["error_code"], "incomplete_text")
        self.assertNotIn("document.pdf", repository.failures[0][1]["error_detail"])


if __name__ == "__main__":
    unittest.main()
