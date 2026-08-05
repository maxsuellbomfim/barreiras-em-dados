from __future__ import annotations

import unittest

from barreiras_docproc.postgres import PostgresExtractionRepository


class EmptyResult:
    def fetchone(self):
        return None


class RecordingConnection:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def execute(self, query, params=None):
        del params
        self.queries.append(" ".join(query.split()))
        return EmptyResult()

    def close(self):
        return None


class RecentDirectEditionPriorityTests(unittest.TestCase):
    def test_candidate_queue_prioritizes_recent_direct_editions(self) -> None:
        connection = RecordingConnection()
        repository = PostgresExtractionRepository(lambda: connection)  # type: ignore[arg-type]

        repository.pending_text_artifacts(30)

        query = connection.queries[0]
        self.assertIn(
            "case when artifact.metadata ->> 'schema_name' "
            "= 'gazette-direct-edition' then 0 else 1 end",
            query,
        )
        self.assertIn(
            "then (artifact.metadata ->> 'edition')::integer "
            "end desc nulls last",
            query,
        )

    def test_ocr_queue_prioritizes_recent_direct_editions(self) -> None:
        connection = RecordingConnection()
        repository = PostgresExtractionRepository(lambda: connection)  # type: ignore[arg-type]

        repository.pending_ocr_pages(30)

        query = connection.queries[0]
        self.assertIn(
            "case when artifact.metadata ->> 'schema_name' "
            "= 'gazette-direct-edition' then 0 else 1 end",
            query,
        )
        self.assertIn(
            "then (artifact.metadata ->> 'edition')::integer "
            "end desc nulls last",
            query,
        )


if __name__ == "__main__":
    unittest.main()
