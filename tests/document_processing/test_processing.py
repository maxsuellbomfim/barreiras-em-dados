from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

from barreiras_docproc.candidates import RULESET_VERSION
from barreiras_docproc.processing import (
    ArtifactMismatchError,
    ExtractionBatch,
    ExtractionPersistResult,
    GazetteActExtractionService,
    TextArtifact,
    candidate_payload,
    job_idempotency_key,
)

ROOT = Path(__file__).parents[2]
FIXTURE_PATH = (
    ROOT / "fixtures" / "sources" / "querido_diario" / "gazette-text-sample.txt"
)


class FakeReader:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects

    def read(self, object_key: str) -> bytes:
        return self.objects[object_key]


class FakeRepository:
    def __init__(self) -> None:
        self.batches: list[ExtractionBatch] = []
        self.seen_jobs: set[str] = set()

    def persist_extraction(
        self,
        batch: ExtractionBatch,
    ) -> ExtractionPersistResult:
        self.batches.append(batch)
        if batch.job_idempotency_key in self.seen_jobs:
            return ExtractionPersistResult(
                job_created=False,
                results_inserted=0,
            )
        self.seen_jobs.add(batch.job_idempotency_key)
        return ExtractionPersistResult(
            job_created=True,
            results_inserted=len(batch.candidates),
        )


def make_artifact(body: bytes) -> TextArtifact:
    sha = hashlib.sha256(body).hexdigest()
    return TextArtifact(
        raw_artifact_id="00000000-0000-0000-0000-000000000501",
        sha256=sha,
        object_key=(
            f"querido-diario/gazettes/documents/sha256/{sha[:2]}/{sha}.txt"
        ),
    )


class GazetteActExtractionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.body = FIXTURE_PATH.read_bytes()
        self.artifact = make_artifact(self.body)
        self.repository = FakeRepository()
        self.service = GazetteActExtractionService(
            object_reader=FakeReader({self.artifact.object_key: self.body}),
            repository=self.repository,
        )

    def test_processes_fixture_into_two_review_candidates(self) -> None:
        result = self.service.process(self.artifact)

        self.assertTrue(result.job_created)
        self.assertEqual(result.results_inserted, 2)
        batch = self.repository.batches[0]
        self.assertEqual(batch.job_type, "gazette_act_candidates")
        self.assertEqual(batch.ruleset_version, RULESET_VERSION)
        self.assertEqual(
            batch.job_idempotency_key,
            job_idempotency_key(self.artifact.sha256, RULESET_VERSION),
        )

    def test_payload_links_candidate_to_canonical_text_and_artifact(
        self,
    ) -> None:
        self.service.process(self.artifact)

        batch = self.repository.batches[0]
        payload = candidate_payload(
            batch.candidates[0],
            batch.canonical,
            batch.artifact,
        )
        self.assertEqual(payload["schema_name"], "gazette-act-candidate")
        self.assertEqual(payload["act_type"], "nomeacao")
        fields = payload["fields"]
        assert isinstance(fields, dict)
        person = fields["person_name"]
        assert isinstance(person, dict)
        self.assertEqual(person["value"], "FULANO DE TAL EXEMPLO")
        self.assertEqual(
            payload["canonical_text_sha256"],
            batch.canonical.sha256,
        )
        self.assertEqual(
            payload["source_artifact_sha256"],
            self.artifact.sha256,
        )
        excerpt = payload["excerpt"]
        assert isinstance(excerpt, str)
        self.assertIn("NOMEAR", excerpt)

    def test_replay_does_not_recreate_job(self) -> None:
        first = self.service.process(self.artifact)
        second = self.service.process(self.artifact)

        self.assertTrue(first.job_created)
        self.assertFalse(second.job_created)
        self.assertEqual(second.results_inserted, 0)

    def test_rejects_restored_bytes_with_wrong_hash(self) -> None:
        tampered = GazetteActExtractionService(
            object_reader=FakeReader(
                {self.artifact.object_key: b"conteudo adulterado"}
            ),
            repository=self.repository,
        )

        with self.assertRaises(ArtifactMismatchError):
            tampered.process(self.artifact)

        self.assertEqual(self.repository.batches, [])


if __name__ == "__main__":
    unittest.main()
