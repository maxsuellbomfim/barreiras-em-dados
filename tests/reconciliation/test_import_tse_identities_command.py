from __future__ import annotations

import unittest
from datetime import UTC, datetime

from barreiras_reconciliation.commands.import_tse_identities import (
    import_identity_year,
)
from barreiras_reconciliation.identity_import import IdentityImportSummary
from barreiras_reconciliation.identity_repository import IdentityTarget


def _target(candidate_id: str = "123") -> IdentityTarget:
    return IdentityTarget(
        source_kind="municipal",
        source_external_id=f"cm:{candidate_id}",
        election_year=2024,
        office="Vereador",
        candidate_id=candidate_id,
        origin_raw_record_id="00000000-0000-4000-8000-000000000001",
        source_collected_at=datetime(2026, 8, 18, tzinfo=UTC),
        votes_in_barreiras=321,
    )


class StubRepository:
    def __init__(self, evidenced: frozenset[str]) -> None:
        self.evidenced = evidenced

    def eligible_targets(self, election_year: int) -> tuple[IdentityTarget, ...]:
        return (_target(),)

    def evidenced_candidate_ids(self, election_year: int) -> frozenset[str]:
        return self.evidenced


class StubService:
    def __init__(self) -> None:
        self.calls: list[tuple[int, bytes, tuple[IdentityTarget, ...]]] = []

    def import_package_for_targets(
        self,
        *,
        year: int,
        package: bytes,
        targets: tuple[IdentityTarget, ...] | None = None,
    ) -> IdentityImportSummary:
        assert targets is not None
        self.calls.append((year, package, targets))
        return IdentityImportSummary(
            election_year=year,
            selected=len(targets),
            inserted=0,
            unchanged=len(targets),
            conflicted=0,
            unavailable=0,
        )


class ImportTseIdentitiesCommandTests(unittest.TestCase):
    def test_skips_download_when_every_eligible_candidate_has_evidence(self) -> None:
        service = StubService()
        fetch_calls: list[int] = []

        event = import_identity_year(
            year=2024,
            repository=StubRepository(frozenset({"123"})),
            service=service,
            fetcher=lambda year: fetch_calls.append(year) or b"unused",
        )

        self.assertEqual(fetch_calls, [])
        self.assertEqual(service.calls, [])
        self.assertEqual(event["event"], "private_identity_import_skipped")
        self.assertEqual(event["reason"], "all_eligible_candidates_evidenced")
        self.assertTrue(event["evidence_coverage_complete"])
        self.assertNotIn("coverage_complete", event)

    def test_downloads_when_an_eligible_candidate_has_no_evidence(self) -> None:
        service = StubService()
        fetch_calls: list[int] = []

        event = import_identity_year(
            year=2024,
            repository=StubRepository(frozenset()),
            service=service,
            fetcher=lambda year: fetch_calls.append(year) or b"official zip",
        )

        self.assertEqual(fetch_calls, [2024])
        self.assertEqual(len(service.calls), 1)
        self.assertEqual(event["event"], "private_identity_import")
        self.assertEqual(event["selected"], 1)

    def test_refresh_forces_official_download_for_covered_year(self) -> None:
        service = StubService()
        fetch_calls: list[int] = []

        import_identity_year(
            year=2024,
            repository=StubRepository(frozenset({"123"})),
            service=service,
            fetcher=lambda year: fetch_calls.append(year) or b"official zip",
            refresh=True,
        )

        self.assertEqual(fetch_calls, [2024])
        self.assertEqual(len(service.calls), 1)


if __name__ == "__main__":
    unittest.main()
