from __future__ import annotations

import unittest
from dataclasses import replace
from decimal import Decimal

from barreiras_normalization.bahia_state_execution import StateExecutionAggregate
from barreiras_normalization.bahia_state_execution_processing import (
    STATE_EXECUTION_JOB_TYPE,
    STATE_EXECUTION_PARSER_VERSION,
    STATE_EXECUTION_VALIDATOR_VERSION,
    StateExecutionArtifact,
    StateExecutionExtractionBatch,
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
        self.job_row = {"id": "00000000-0000-0000-0000-000000001003"}

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


def _batch() -> StateExecutionExtractionBatch:
    artifact = StateExecutionArtifact(
        raw_artifact_id="00000000-0000-0000-0000-000000001001",
        sha256="a" * 64,
        object_key="bahia/emendas-estaduais/archive/a.zip",
        source_url="https://dados.ba.gov.br/dataset/emendas-parlamentares",
        collected_at="2026-08-13T17:34:48+00:00",
    )
    aggregate = StateExecutionAggregate(
        fiscal_year=2026,
        agency_name="Secretaria da Educacao",
        agency_code="SEC",
        budget_unit_name="Assessoria de Planejamento e Gestao",
        budget_unit_code="APG",
        action_name="Apoio Financeiro para a Melhoria",
        action_code="3334",
        author_name="Antonio Henrique Junior",
        author_external_code="500069",
        execution_code="2026.3.11.11101.422.3334.500069.5",
        initial_budget_amount=Decimal("237000.00"),
        current_budget_amount=Decimal("237000.00"),
        committed_amount=Decimal("0.00"),
        liquidated_amount=Decimal("0.00"),
        paid_amount=Decimal("0.00"),
        territorial_scope="not_available_in_execution_archive",
        evidence_text="linha oficial",
        evidence_sha256="b" * 64,
    )
    return StateExecutionExtractionBatch(
        artifact=artifact,
        aggregates=(aggregate,),
        job_type=STATE_EXECUTION_JOB_TYPE,
        idempotency_key="c" * 64,
        extractor_version=STATE_EXECUTION_PARSER_VERSION,
        validator_version=STATE_EXECUTION_VALIDATOR_VERSION,
    )


class BahiaStateExecutionRepositoryTests(unittest.TestCase):
    def _repository(self, connection):
        try:
            from barreiras_normalization.bahia_state_execution_repository import (
                BahiaStateExecutionRepository,
            )
        except ImportError:
            self.fail("o repositorio de execucao estadual ainda nao existe")
        return BahiaStateExecutionRepository(lambda: connection)

    def test_selects_only_verified_state_archives_not_already_processed(self) -> None:
        connection = _Connection()
        connection.pending_rows = [
            {
                "artifact_id": "00000000-0000-0000-0000-000000001001",
                "sha256": "a" * 64,
                "object_key": "bahia/emendas-estaduais/archive/a.zip",
                "source_url": "https://dados.ba.gov.br/file.zip",
                "collected_at": "2026-08-13T17:34:48+00:00",
            }
        ]
        repository = self._repository(connection)

        artifacts = repository.pending_artifacts(5)

        self.assertEqual(artifacts[0].sha256, "a" * 64)
        query = connection.queries[0][0]
        self.assertIn("artifact.artifact_kind = 'archive'", query)
        self.assertIn("bahia_state_amendment_archive_member", query)
        self.assertIn("count(*) = 5", query)
        self.assertIn("result.extractor_version = %s", query)
        self.assertIn("result.validator_version = %s", query)
        self.assertIn("job.status = 'dead_lettered'", query)

    def test_persists_job_and_decimal_payloads_in_one_transaction(self) -> None:
        connection = _Connection()
        repository = self._repository(connection)

        result = repository.persist_extraction(_batch())

        self.assertTrue(result.job_created)
        self.assertEqual(result.results_inserted, 1)
        result_query, params = next(
            (query, params)
            for query, params in connection.queries
            if "insert into raw.extraction_results" in query
        )
        self.assertIn("'valid'", result_query)
        assert params is not None
        self.assertIn('"current_budget_amount":"237000.00"', params[4])
        self.assertIn(
            '"territorial_scope":"not_available_in_execution_archive"',
            params[4],
        )

    def test_batches_multiple_results_in_one_database_statement(self) -> None:
        connection = _Connection()
        repository = self._repository(connection)
        batch = _batch()
        first = batch.aggregates[0]
        second = replace(
            first,
            execution_code="2026.3.11.11101.422.3334.500069.6",
            evidence_text="segunda linha oficial",
            evidence_sha256="d" * 64,
        )

        result = repository.persist_extraction(
            replace(batch, aggregates=(first, second))
        )

        result_queries = [
            (query, params)
            for query, params in connection.queries
            if "insert into raw.extraction_results" in query
        ]
        self.assertEqual(result.results_inserted, 2)
        self.assertEqual(len(result_queries), 1)
        query, params = result_queries[0]
        self.assertIn("jsonb_array_elements", query)
        assert params is not None
        payload_param = next(
            value
            for value in params
            if isinstance(value, str) and value.startswith("[")
        )
        self.assertIn('"evidence_sha256":"' + "b" * 64 + '"', payload_param)
        self.assertIn('"evidence_sha256":"' + "d" * 64 + '"', payload_param)

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

    def test_failures_are_versioned_and_move_to_dead_letter(self) -> None:
        connection = _Connection()
        repository = self._repository(connection)

        repository.persist_failure(
            _batch().artifact,
            idempotency_key="c" * 64,
            error_code="parser_contract",
            error_detail="formato oficial mudou",
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
