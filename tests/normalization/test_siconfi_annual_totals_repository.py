from __future__ import annotations

import unittest
from decimal import Decimal

from barreiras_normalization.siconfi_annual_totals import (
    BARREIRAS_IBGE_CODE,
    BARREIRAS_INSTITUTION,
    METRIC_SELECTORS,
    SiconfiAnnualRawLine,
    SiconfiAnnualSnapshot,
    normalize_siconfi_annual_snapshot,
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
        self.job_row = {"id": "00000000-0000-0000-0000-000000008001"}
        self.insert_counter = 0

    def execute(self, query, params=None):
        normalized = " ".join(query.split())
        self.queries.append((normalized, params))
        if "with latest_artifacts as materialized" in normalized:
            return _Cursor(rows=self.pending_rows)
        if "insert into raw.extraction_jobs" in normalized:
            return _Cursor(row=self.job_row)
        if "from org.public_bodies" in normalized:
            return _Cursor(row={"id": "00000000-0000-0000-0000-000000008002"})
        if "from finance.siconfi_annual_totals as current" in normalized:
            return _Cursor(row=None)
        if "insert into finance.siconfi_annual_totals" in normalized:
            self.insert_counter += 1
            return _Cursor(
                row={"id": f"00000000-0000-0000-0000-{self.insert_counter:012d}"}
            )
        return _Cursor()

    def transaction(self):
        return _Transaction()

    def close(self):
        return None


def _snapshot() -> SiconfiAnnualSnapshot:
    rows = tuple(
        SiconfiAnnualRawLine(
            raw_record_id=f"00000000-0000-0000-0000-{index:012d}",
            payload={
                "exercicio": 2025,
                "cod_ibge": BARREIRAS_IBGE_CODE,
                "instituicao": BARREIRAS_INSTITUTION,
                "anexo": selector.annex,
                "rotulo": selector.label,
                "coluna": selector.column_label,
                "cod_conta": selector.account_code,
                "conta": selector.account_label,
                "valor": "-12.50" if index == 2 else f"{index}.00",
            },
        )
        for index, selector in enumerate(METRIC_SELECTORS, start=1)
    )
    return SiconfiAnnualSnapshot(
        fiscal_year=2025,
        raw_artifact_id="00000000-0000-0000-0000-000000008003",
        artifact_sha256="a" * 64,
        source_url="https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca",
        retrieved_at="2026-08-24T12:00:00+00:00",
        rows=rows,
    )


class SiconfiAnnualTotalsRepositoryTests(unittest.TestCase):
    def _repository(self, connection):
        from barreiras_normalization.siconfi_annual_totals_repository import (
            SiconfiAnnualTotalsRepository,
        )

        return SiconfiAnnualTotalsRepository(lambda: connection)

    def test_selects_latest_unprocessed_artifact_per_year(self) -> None:
        connection = _Connection()
        source = _snapshot()
        connection.pending_rows = [
            {
                "artifact_id": source.raw_artifact_id,
                "sha256": source.artifact_sha256,
                "source_url": source.source_url,
                "retrieved_at": source.retrieved_at,
                "fiscal_year": source.fiscal_year,
                "raw_record_id": row.raw_record_id,
                "payload": row.payload,
            }
            for row in source.rows
        ]

        snapshots = self._repository(connection).pending_snapshots(10)

        self.assertEqual(len(snapshots), 1)
        self.assertEqual(len(snapshots[0].rows), 7)
        query = connection.queries[0][0]
        self.assertIn("distinct on ((record.payload ->> 'exercicio')::smallint)", query)
        self.assertIn("job.status in ('succeeded', 'dead_lettered')", query)
        self.assertIn("record.record_type = 'siconfi_dca_line'", query)

    def test_persists_seven_versions_evidence_and_extraction_results(self) -> None:
        connection = _Connection()
        source = _snapshot()
        totals = normalize_siconfi_annual_snapshot(source)

        result = self._repository(connection).persist_totals(source, totals)

        self.assertTrue(result.job_created)
        self.assertEqual(result.totals_inserted, 7)
        self.assertEqual(result.totals_existing, 0)
        total_params = [
            params
            for query, params in connection.queries
            if "insert into finance.siconfi_annual_totals" in query
        ]
        self.assertEqual(len(total_params), 7)
        self.assertEqual(total_params[1][7], Decimal("-12.50"))
        self.assertEqual(
            sum(
                "insert into evidence.evidence_items" in query
                for query, _ in connection.queries
            ),
            7,
        )
        self.assertEqual(
            sum(
                "insert into raw.extraction_results" in query
                for query, _ in connection.queries
            ),
            7,
        )

    def test_existing_successful_job_is_idempotent(self) -> None:
        connection = _Connection()
        connection.job_row = None
        source = _snapshot()

        result = self._repository(connection).persist_totals(
            source, normalize_siconfi_annual_snapshot(source)
        )

        self.assertFalse(result.job_created)
        self.assertEqual(result.totals_existing, 7)
        self.assertFalse(
            any(
                "insert into finance.siconfi_annual_totals" in query
                for query, _ in connection.queries
            )
        )


if __name__ == "__main__":
    unittest.main()
