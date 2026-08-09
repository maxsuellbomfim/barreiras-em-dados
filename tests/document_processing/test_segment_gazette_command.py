from __future__ import annotations

import hashlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from barreiras_docproc.commands.segment_gazette_editions import main, process_pending
from barreiras_docproc.gazette_repository import GazetteArtifact
from barreiras_docproc.processing import PageInput, integral_gazette_idempotency_key


def artifact(edition: int, artifact_id: str) -> GazetteArtifact:
    return GazetteArtifact(
        raw_artifact_id=artifact_id,
        sha256=hashlib.sha256(f"edition-{edition}".encode()).hexdigest(),
        edition=edition,
        edition_year=2026,
        edition_date="2026-08-08",
        created_at="2026-08-08T12:00:00+00:00",
    )


class InMemoryRepository:
    def __init__(self, artifacts: tuple[GazetteArtifact, ...]) -> None:
        self.artifacts = artifacts
        self.pages: dict[str, tuple[PageInput, ...]] = {}
        self.batches = []
        self.failures: list[tuple[str, str, str]] = []
        self.persisted_keys: set[str] = set()

    def pending_artifacts(self, limit: int) -> tuple[GazetteArtifact, ...]:
        del limit
        return self.artifacts

    def batch_exists(self, artifact_id: str, idempotency_key: str) -> bool:
        del artifact_id
        return idempotency_key in self.persisted_keys

    def page_inputs(self, artifact_id: str) -> tuple[PageInput, ...]:
        return self.pages[artifact_id]

    def persist_version(self, batch):
        if batch.idempotency_key in self.persisted_keys:
            return type("Result", (), {"created": False, "documents_inserted": 0})()
        self.persisted_keys.add(batch.idempotency_key)
        self.batches.append(batch)
        return type(
            "Result", (), {"created": True, "documents_inserted": len(batch.documents)}
        )()

    def record_failure(self, artifact_id: str, code: str, detail: str) -> None:
        self.failures.append((artifact_id, code, detail))


class SegmentGazetteCommandTests(unittest.TestCase):
    def test_idempotency_binds_artifact_and_all_processing_versions(self) -> None:
        baseline = integral_gazette_idempotency_key(
            "a" * 64, ((1, "layout/1"),), "segmenter/1", "validator/1"
        )

        self.assertEqual(len(baseline), 64)
        self.assertNotEqual(
            baseline,
            integral_gazette_idempotency_key(
                "a" * 64, ((1, "layout/2"),), "segmenter/1", "validator/1"
            ),
        )
        self.assertNotEqual(
            baseline,
            integral_gazette_idempotency_key(
                "a" * 64,
                ((2, "layout/1"), (1, "layout/1")),
                "segmenter/1",
                "validator/1",
            ),
        )

    def test_processes_newest_complete_editions_first_and_is_idempotent(self) -> None:
        newest = artifact(4707, "00000000-0000-0000-0000-000000000707")
        older = artifact(4706, "00000000-0000-0000-0000-000000000706")
        repository = InMemoryRepository((older, newest))
        repository.pages = {
            newest.raw_artifact_id: (
                PageInput(1, "parser/1", "PORTARIA N 2\nTexto integral", None),
            ),
            older.raw_artifact_id: (
                PageInput(1, "parser/1", "PORTARIA N 1\nTexto integral", None),
            ),
        }

        first = process_pending(repository, limit=2)
        second = process_pending(repository, limit=2)

        self.assertEqual(first.processed, 2)
        self.assertEqual(second.processed, 0)
        self.assertEqual(
            [batch.artifact.edition for batch in repository.batches[:2]], [4707, 4706]
        )
        self.assertEqual(len(repository.batches), 2)
        self.assertEqual(
            repository.batches[0].segmenter_version,
            "gazette-structural-segmenter/1.0.0",
        )
        self.assertEqual(
            repository.batches[0].validator_version, "gazette-integrity/1.0.0"
        )

    def test_prioritizes_year_before_edition_number(self) -> None:
        prior_year = GazetteArtifact(
            "00000000-0000-0000-0000-000000000999",
            hashlib.sha256(b"prior-year").hexdigest(),
            999,
            2026,
            "2026-12-31",
            "2026-12-31T12:00:00+00:00",
        )
        current_year = GazetteArtifact(
            "00000000-0000-0000-0000-000000000001",
            hashlib.sha256(b"current-year").hexdigest(),
            1,
            2027,
            "2027-01-01",
            "2027-01-01T12:00:00+00:00",
        )
        repository = InMemoryRepository((prior_year, current_year))
        for item in repository.artifacts:
            repository.pages[item.raw_artifact_id] = (
                PageInput(1, "parser/1", f"PORTARIA N {item.edition}\nTexto", None),
            )

        result = process_pending(repository, limit=1)

        self.assertEqual(result.processed, 1)
        self.assertEqual(repository.batches[0].artifact.edition_year, 2027)

    def test_invalid_segmentation_persists_only_the_integral_fallback(self) -> None:
        current = artifact(4707, "00000000-0000-0000-0000-000000000707")
        repository = InMemoryRepository((current,))
        repository.pages[current.raw_artifact_id] = (
            PageInput(1, "parser/1", "PORTARIA N 2\nPrimeiro bloco", None),
            PageInput(2, "parser/1", "Continuação literal", None),
        )

        result = process_pending(
            repository,
            limit=1,
            boundary_proposer=lambda _blocks: (),
        )

        self.assertEqual(result.processed, 1)
        persisted = repository.batches[0].documents
        self.assertEqual(len(persisted), 1)
        self.assertEqual(persisted[0].status, "edition_fallback")
        self.assertIn("Continuação literal", persisted[0].full_text)

    def test_page_granularity_never_publishes_partial_segmentation(self) -> None:
        current = artifact(4707, "00000000-0000-0000-0000-000000000707")
        repository = InMemoryRepository((current,))
        repository.pages[current.raw_artifact_id] = (
            PageInput(1, "parser/1", "PORTARIA N 2\nPrimeiro ato", None),
            PageInput(2, "parser/1", "DECRETO N 3\nSegundo ato", None),
        )

        result = process_pending(repository, limit=1)

        self.assertEqual(result.processed, 1)
        persisted = repository.batches[0].documents
        self.assertEqual(len(persisted), 1)
        self.assertEqual(persisted[0].status, "edition_fallback")

    def test_failure_is_isolated_and_sanitized(self) -> None:
        broken = artifact(4708, "00000000-0000-0000-0000-000000000708")
        healthy = artifact(4707, "00000000-0000-0000-0000-000000000707")
        repository = InMemoryRepository((broken, healthy))
        repository.pages[broken.raw_artifact_id] = ()
        repository.pages[healthy.raw_artifact_id] = (
            PageInput(1, "parser/1", "PORTARIA N 2\nTexto integral", None),
        )

        result = process_pending(repository, limit=2)

        self.assertEqual(result.failed, 1)
        self.assertEqual(result.processed, 1)
        self.assertEqual(repository.failures[0][1], "segment_processing_error")
        self.assertNotIn(
            "00000000-0000-0000-0000-000000000708", repository.failures[0][2]
        )

    def test_skips_persisted_editions_and_continues_until_limit_new_batches(
        self,
    ) -> None:
        newest = artifact(4710, "00000000-0000-0000-0000-000000000710")
        skipped = artifact(4709, "00000000-0000-0000-0000-000000000709")
        pending = artifact(4708, "00000000-0000-0000-0000-000000000708")
        repository = InMemoryRepository((newest, skipped, pending))
        for item in repository.artifacts:
            repository.pages[item.raw_artifact_id] = (
                PageInput(1, "parser/1", f"PORTARIA N {item.edition}\nTexto", None),
            )
        repository.persisted_keys.update(
            {
                integral_gazette_idempotency_key(
                    newest.sha256,
                    ((1, "parser/1"),),
                    "gazette-structural-segmenter/1.0.0",
                    "gazette-integrity/1.0.0",
                ),
                integral_gazette_idempotency_key(
                    skipped.sha256,
                    ((1, "parser/1"),),
                    "gazette-structural-segmenter/1.0.0",
                    "gazette-integrity/1.0.0",
                ),
            }
        )

        result = process_pending(repository, limit=1)

        self.assertEqual(result.processed, 1)
        self.assertEqual(
            [batch.artifact.edition for batch in repository.batches], [4708]
        )

    def test_main_returns_nonzero_after_isolated_failures(self) -> None:
        repository = InMemoryRepository(
            (artifact(4708, "00000000-0000-0000-0000-000000000708"),)
        )
        repository.pages[repository.artifacts[0].raw_artifact_id] = ()
        persistence = SimpleNamespace(
            mode="postgres-supabase", database_url="postgres://example"
        )
        collector = SimpleNamespace(log_level="INFO")

        with (
            patch(
                "barreiras_docproc.commands.segment_gazette_editions."
                "CollectorSettings.from_env",
                return_value=collector,
            ),
            patch(
                "barreiras_docproc.commands.segment_gazette_editions."
                "PersistenceSettings.from_env",
                return_value=persistence,
            ),
            patch(
                "barreiras_docproc.commands.segment_gazette_editions."
                "GazetteDocumentRepository.from_dsn",
                return_value=repository,
            ),
        ):
            exit_code = main(["--limit", "1"])

        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
