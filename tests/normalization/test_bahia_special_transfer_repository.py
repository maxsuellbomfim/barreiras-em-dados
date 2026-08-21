from __future__ import annotations

import unittest

from barreiras_normalization.bahia_special_transfer_processing import (
    SPECIAL_TRANSFER_JOB_TYPE,
    SPECIAL_TRANSFER_VALIDATOR_VERSION,
    SpecialTransferArtifact,
    SpecialTransferExtractionBatch,
)
from barreiras_normalization.bahia_special_transfers import (
    SPECIAL_TRANSFER_PARSER_VERSION,
    parse_special_transfer_payment_candidates,
)

from tests.normalization.test_bahia_special_transfers import (
    _archive,
    _centralization,
    _expense,
    _payment,
)


class _Cursor:
    def __init__(self, *, rows=(), row=None) -> None:
        self.rows = list(rows)
        self.row = row

    def fetchone(self):
        if self.rows:
            return self.rows.pop(0)
        return self.row

    def fetchall(self):
        rows = list(self.rows)
        self.rows.clear()
        return rows


class _Transaction:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Connection:
    def __init__(self) -> None:
        self.queries: list[tuple[str, object]] = []
        self.pending_rows = []
        self.job_row = {"id": "00000000-0000-0000-0000-000000002003"}

    def execute(self, query, params=None):
        normalized = " ".join(query.split())
        self.queries.append((normalized, params))
        if "from raw.raw_artifacts as artifact" in normalized:
            return _Cursor(rows=self.pending_rows)
        if "insert into raw.extraction_jobs" in normalized:
            return _Cursor(row=self.job_row)
        return _Cursor()

    def transaction(self):
        return _Transaction()

    def close(self):
        return None


def _batch() -> SpecialTransferExtractionBatch:
    archive = _archive(
        centralization_rows=[_centralization()],
        expense_rows=[_expense()],
        payment_rows=[_payment()],
    )
    artifact = SpecialTransferArtifact(
        raw_artifact_id="00000000-0000-0000-0000-000000002001",
        sha256="a" * 64,
        object_key="bahia/transferencias-especiais/archive/sha256/aa/a.zip",
        source_url="https://dados.ba.gov.br/dataset/transferencias-especiais",
        collected_at="2026-08-21T04:32:47+00:00",
    )
    return SpecialTransferExtractionBatch(
        artifact=artifact,
        candidates=parse_special_transfer_payment_candidates(archive),
        job_type=SPECIAL_TRANSFER_JOB_TYPE,
        idempotency_key="c" * 64,
        extractor_version=SPECIAL_TRANSFER_PARSER_VERSION,
        validator_version=SPECIAL_TRANSFER_VALIDATOR_VERSION,
    )


class BahiaSpecialTransferRepositoryTests(unittest.TestCase):
    def _repository(self, connection):
        try:
            from barreiras_normalization.bahia_special_transfer_repository import (
                BahiaSpecialTransferRepository,
            )
        except ImportError:
            self.fail("o repositório de transferências especiais ainda não existe")
        return BahiaSpecialTransferRepository(lambda: connection)

    def test_selects_only_verified_archives_not_already_processed(self) -> None:
        connection = _Connection()
        connection.pending_rows = [
            {
                "artifact_id": "00000000-0000-0000-0000-000000002001",
                "sha256": "a" * 64,
                "object_key": (
                    "bahia/transferencias-especiais/archive/sha256/aa/a.zip"
                ),
                "source_url": "https://dados.ba.gov.br/file.zip",
                "collected_at": "2026-08-21T04:32:47+00:00",
            }
        ]
        repository = self._repository(connection)

        artifacts = repository.pending_artifacts(5)

        self.assertEqual(artifacts[0].sha256, "a" * 64)
        query = connection.queries[0][0]
        self.assertIn("bahia_special_transfer_archive_member", query)
        self.assertIn("count(*) = 5", query)
        self.assertIn("result.extractor_version = %s", query)
        self.assertIn("result.validator_version = %s", query)
        self.assertIn("job.status = 'dead_lettered'", query)

    def test_persists_safe_candidates_without_creditor_fields(self) -> None:
        connection = _Connection()
        repository = self._repository(connection)

        result = repository.persist_extraction(_batch())

        self.assertTrue(result.job_created)
        self.assertEqual(result.results_inserted, 1)
        _, params = next(
            (query, params)
            for query, params in connection.queries
            if "insert into raw.extraction_results" in query
            and params is not None
            and params[1] == "bahia_special_transfer_payment_candidate"
        )
        assert params is not None
        payloads = str(params[4])
        self.assertIn('"amendment_number":"40720003"', payloads)
        self.assertNotIn("98765432100", payloads)
        self.assertNotIn("CREDOR QUE NÃO DEVE SER PUBLICADO", payloads)
        self.assertNotIn("CNPJ_CPF_CREDOR_PAGAMENTO", payloads)

    def test_existing_successful_job_is_idempotent(self) -> None:
        connection = _Connection()
        connection.job_row = None
        repository = self._repository(connection)

        result = repository.persist_extraction(_batch())

        self.assertFalse(result.job_created)
        self.assertEqual(result.results_inserted, 0)
        self.assertFalse(
            any(
                "insert into raw.extraction_results" in query
                for query, _ in connection.queries
            )
        )

    def test_zero_candidates_records_versioned_scope_summary(self) -> None:
        connection = _Connection()
        repository = self._repository(connection)
        batch = _batch()
        empty = SpecialTransferExtractionBatch(
            artifact=batch.artifact,
            candidates=(),
            job_type=batch.job_type,
            idempotency_key=batch.idempotency_key,
            extractor_version=batch.extractor_version,
            validator_version=batch.validator_version,
        )

        result = repository.persist_extraction(empty)

        self.assertTrue(result.job_created)
        self.assertEqual(result.results_inserted, 0)
        result_queries = [
            (query, params)
            for query, params in connection.queries
            if "insert into raw.extraction_results" in query
        ]
        self.assertEqual(len(result_queries), 1)
        _, params = result_queries[0]
        assert params is not None
        self.assertEqual(params[1], "bahia_special_transfer_scope_summary")
        self.assertIn('"candidate_count":0', str(params[4]))
        self.assertIn(
            '"public_projection":"blocked_pending_author_reconciliation"',
            str(params[4]),
        )

    def test_failures_are_versioned_and_move_to_dead_letter(self) -> None:
        connection = _Connection()
        repository = self._repository(connection)

        repository.persist_failure(
            _batch().artifact,
            idempotency_key="c" * 64,
            error_code="parser_contract",
            error_detail="estrutura oficial mudou",
        )

        query = next(
            query
            for query, _ in connection.queries
            if "insert into raw.extraction_jobs" in query
        )
        self.assertIn("then 'dead_lettered'", query)
        self.assertIn("attempt_count + 1 >= raw.extraction_jobs.max_attempts", query)


if __name__ == "__main__":
    unittest.main()
