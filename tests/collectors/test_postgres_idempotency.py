from __future__ import annotations

import unittest

from barreiras_collectors.persistence.postgres import _compatible_existing_record


class PostgresIdempotencyTests(unittest.TestCase):
    def test_same_content_is_replay_even_with_different_internal_uuid(self) -> None:
        prior = {
            "artifact_sha256": "a" * 64,
            "source_record_key": "barreiras-diario:publication:4705:2026-08-03",
            "record_type": "barreiras_diario_publication",
            "payload_sha256": "b" * 64,
            "parser_version": "barreiras-diario-catalog/1.0.0",
        }

        self.assertTrue(
            _compatible_existing_record(
                prior,
                artifact_sha256="a" * 64,
                source_record_key="barreiras-diario:publication:4705:2026-08-03",
                record_type="barreiras_diario_publication",
                payload_sha256="b" * 64,
                parser_version="barreiras-diario-catalog/1.0.0",
            )
        )

    def test_changed_content_remains_a_conflict(self) -> None:
        prior = {
            "artifact_sha256": "a" * 64,
            "source_record_key": "barreiras-diario:publication:4705:2026-08-03",
            "record_type": "barreiras_diario_publication",
            "payload_sha256": "b" * 64,
            "parser_version": "barreiras-diario-catalog/1.0.0",
        }

        self.assertFalse(
            _compatible_existing_record(
                prior,
                artifact_sha256="a" * 64,
                source_record_key="barreiras-diario:publication:4705:2026-08-03",
                record_type="barreiras_diario_publication",
                payload_sha256="c" * 64,
                parser_version="barreiras-diario-catalog/1.0.0",
            )
        )


if __name__ == "__main__":
    unittest.main()
