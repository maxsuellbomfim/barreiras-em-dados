from __future__ import annotations

import unittest
from dataclasses import replace
from decimal import Decimal

from barreiras_docproc.bahia_state_loa import (
    AuthorizedLoaAmendment,
    Loa2026ScopeRow,
)
from barreiras_docproc.bahia_state_loa_processing import (
    LOA_BARREIRAS_PARSER_VERSION,
    LOA_EXTRACTION_JOB_TYPE,
    LOA_VALIDATOR_VERSION,
    BahiaStateLoaArtifact,
    BahiaStateLoaExtractionBatch,
    LoaProcessingError,
)
from barreiras_docproc.bahia_state_loa_repository import (
    BahiaStateLoaExtractionRepository,
)
from barreiras_docproc.processing import PageInput


class Cursor:
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


class Transaction:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class RecordingConnection:
    def __init__(self) -> None:
        self.queries: list[tuple[str, object]] = []
        self.pending_rows = []
        self.job_row = {"id": "00000000-0000-0000-0000-000000000903"}
        self.page_row = {"id": "00000000-0000-0000-0000-000000000904"}
        self.existing_page_row = None

    def execute(self, query, params=None):
        normalized = " ".join(query.split())
        self.queries.append((normalized, params))
        if "from raw.raw_artifacts as artifact" in normalized:
            return Cursor(rows=self.pending_rows)
        if "insert into raw.document_pages" in normalized:
            return Cursor(row=self.page_row)
        if "from raw.document_pages" in normalized:
            return Cursor(row=self.existing_page_row)
        if "insert into raw.extraction_jobs" in normalized:
            return Cursor(row=self.job_row)
        if "refresh_bahia_state_loa_execution_group_snapshot" in normalized:
            return Cursor(row={"refreshed_rows": 4})
        if "refresh_bahia_state_loa_execution_reconciliation_snapshot" in normalized:
            return Cursor(row={"refreshed_rows": 5})
        return Cursor()

    def transaction(self):
        return Transaction()

    def close(self):
        return None


def batch() -> BahiaStateLoaExtractionBatch:
    artifact = BahiaStateLoaArtifact(
        raw_artifact_id="00000000-0000-0000-0000-000000000901",
        raw_record_id="00000000-0000-0000-0000-000000000902",
        sha256="a" * 64,
        object_key="bahia/loa-emendas-estaduais/2025/a.pdf",
        fiscal_year=2025,
        annex_code="III",
        source_url="https://www.ba.gov.br/seplan/loa-2025.pdf",
    )
    amendment = AuthorizedLoaAmendment(
        fiscal_year=2025,
        annex_code="III",
        amendment_number="860",
        author_name="Jose de Arimateia",
        author_external_code=None,
        agency_code="SETUR",
        budget_unit_code="APG",
        action_code=None,
        official_description="Apoio a evento cultural",
        municipality="Barreiras",
        authorized_amount=Decimal("100000"),
        page_number=17,
        evidence_text="Barreiras 860 Jose de Arimateia ... 100.000",
        evidence_sha256="b" * 64,
    )
    return BahiaStateLoaExtractionBatch(
        artifact=artifact,
        pages=(PageInput(17, "pypdf/1", "texto", "c" * 64),),
        amendments=(amendment,),
        job_type=LOA_EXTRACTION_JOB_TYPE,
        idempotency_key="d" * 64,
        extractor_version=LOA_BARREIRAS_PARSER_VERSION,
        validator_version=LOA_VALIDATOR_VERSION,
    )


def batch_with_scope() -> BahiaStateLoaExtractionBatch:
    scope_row = Loa2026ScopeRow(
        fiscal_year=2026,
        annex_code="I",
        amendment_number="3030",
        author_name="Autor Teste",
        author_external_code="500069",
        agency_code="SESAB",
        budget_unit_code="FESBA",
        action_code="5607",
        author_page_number=21,
        author_evidence_text="Autor Teste - 500069 10.324.979",
        author_evidence_sha256="e" * 64,
        page_number=22,
        evidence_text="3030 SESAB FESBA 5607 Aparelhamento",
        evidence_sha256="f" * 64,
    )
    return replace(batch(), scope_rows=(scope_row,))


class BahiaStateLoaRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = RecordingConnection()
        self.repository = BahiaStateLoaExtractionRepository(
            lambda: self.connection  # type: ignore[arg-type]
        )

    def test_pending_artifacts_are_exact_manifests_not_arbitrary_pdfs(self) -> None:
        self.connection.pending_rows = [
            {
                "artifact_id": "00000000-0000-0000-0000-000000000901",
                "record_id": "00000000-0000-0000-0000-000000000902",
                "sha256": "a" * 64,
                "object_key": "bahia/loa-emendas-estaduais/2025/a.pdf",
                "fiscal_year": 2025,
                "annex_code": "III",
                "source_url": "https://www.ba.gov.br/seplan/loa-2025.pdf",
            }
        ]

        artifacts = self.repository.pending_artifacts(5)

        self.assertEqual(artifacts[0].fiscal_year, 2025)
        query = self.connection.queries[0][0]
        self.assertIn(
            "record.record_type = 'bahia_state_loa_amendment_annex'", query
        )
        self.assertIn("record.payload ->> 'content_sha256' = artifact.sha256", query)
        self.assertIn("result.extractor_version = %s", query)
        self.assertIn("result.candidate_type = 'bahia_state_loa_2026_scope_row'", query)
        self.assertIn(
            "result.candidate_type = 'bahia_state_loa_authorized_amendment'",
            query,
        )
        self.assertIn("(record.payload ->> 'fiscal_year')::integer = 2026", query)
        self.assertEqual(
            self.connection.queries[0][1][1],
            "bahia-state-loa-scope/1.0.0",
        )
        self.assertIn("job.status = 'dead_lettered'", query)
        self.assertIn("order by candidate.fiscal_year desc", query)

    def test_persists_pages_job_and_valid_results_in_one_transaction(self) -> None:
        result = self.repository.persist_extraction(batch())

        self.assertTrue(result.job_created)
        self.assertEqual(result.results_inserted, 1)
        queries = [query for query, _params in self.connection.queries]
        self.assertTrue(
            any("insert into raw.document_pages" in query for query in queries)
        )
        job_query = next(
            query for query in queries if "insert into raw.extraction_jobs" in query
        )
        self.assertIn("status = 'succeeded'", job_query)
        result_query = next(
            query for query in queries if "insert into raw.extraction_results" in query
        )
        self.assertIn("'valid'", result_query)
        payload_params = next(
            params
            for query, params in self.connection.queries
            if "insert into raw.extraction_results" in query
        )
        assert payload_params is not None
        self.assertIn('"authorized_amount":"100000"', payload_params[4])
        self.assertIn('"financial_stage":"authorized"', payload_params[4])
        self.assertNotIn("paid", payload_params[4])

    def test_persists_statewide_scope_as_a_separate_private_candidate(self) -> None:
        result = self.repository.persist_extraction(batch_with_scope())

        self.assertEqual(result.results_inserted, 1)
        self.assertEqual(result.scope_rows_inserted, 1)
        scope_params = next(
            params
            for query, params in self.connection.queries
            if "insert into raw.extraction_results" in query
            and params is not None
            and "bahia_state_loa_2026_scope_row" in query
        )
        self.assertIn('"visibility":"private_reconciliation_scope"', scope_params[2])
        self.assertIn('"author_external_code":"500069"', scope_params[2])
        self.assertIn(
            '"extractor_version":"bahia-state-loa-scope/1.0.0"',
            scope_params[2],
        )
        self.assertNotIn('"municipality"', scope_params[2])

    def test_existing_succeeded_job_is_idempotent(self) -> None:
        self.connection.job_row = None

        result = self.repository.persist_extraction(batch())

        self.assertFalse(result.job_created)
        self.assertEqual(result.results_inserted, 0)
        self.assertFalse(
            any(
                "insert into raw.extraction_results" in query
                for query, _params in self.connection.queries
            )
        )

    def test_failures_move_to_dead_letter_after_the_attempt_limit(self) -> None:
        self.repository.persist_failure(
            batch().artifact,
            idempotency_key="d" * 64,
            error_code="parser_contract",
            error_detail="formato oficial mudou",
        )

        query = next(
            query
            for query, _params in self.connection.queries
            if "insert into raw.extraction_jobs" in query
        )
        self.assertIn("then 'dead_lettered'", query)
        self.assertIn("attempt_count + 1 >= raw.extraction_jobs.max_attempts", query)

    def test_existing_page_with_different_text_hash_is_rejected(self) -> None:
        self.connection.page_row = None
        self.connection.existing_page_row = {"text_sha256": "e" * 64}

        with self.assertRaisesRegex(LoaProcessingError, "pagina"):
            self.repository.persist_extraction(batch())

    def test_refreshes_the_public_execution_snapshot_with_bounded_timeout(self) -> None:
        refreshed_rows = self.repository.refresh_execution_snapshot()

        self.assertEqual(refreshed_rows, 5)
        queries = [query for query, _params in self.connection.queries]
        self.assertIn("set local statement_timeout = '120s'", queries)
        self.assertTrue(
            any(
                "refresh_bahia_state_loa_execution_reconciliation_snapshot" in query
                for query in queries
            )
        )
        self.assertTrue(
            any(
                "refresh_bahia_state_loa_execution_group_snapshot" in query
                for query in queries
            )
        )


if __name__ == "__main__":
    unittest.main()
