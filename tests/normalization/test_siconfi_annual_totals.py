from __future__ import annotations

import unittest
from dataclasses import replace
from decimal import Decimal

from barreiras_normalization.siconfi_annual_totals import (
    BARREIRAS_IBGE_CODE,
    BARREIRAS_INSTITUTION,
    METRIC_SELECTORS,
    SiconfiAnnualRawLine,
    SiconfiAnnualSnapshot,
    SiconfiAnnualTotalsError,
    normalize_siconfi_annual_snapshot,
)


def snapshot(*, amount_override: dict[str, str] | None = None):
    overrides = amount_override or {}
    rows = []
    for index, selector in enumerate(METRIC_SELECTORS, start=1):
        rows.append(
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
                    "valor": overrides.get(selector.metric_key, f"{index}.00"),
                },
            )
        )
    return SiconfiAnnualSnapshot(
        fiscal_year=2025,
        raw_artifact_id="00000000-0000-0000-0000-000000000100",
        artifact_sha256="a" * 64,
        source_url="https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca",
        retrieved_at="2026-08-24T12:00:00+00:00",
        rows=tuple(rows),
    )


class SiconfiAnnualTotalsTests(unittest.TestCase):
    def test_extracts_seven_literal_metrics_without_calculating(self) -> None:
        totals = normalize_siconfi_annual_snapshot(snapshot())

        self.assertEqual(len(totals), 7)
        self.assertEqual(totals[0].metric_key, "gross_revenue_realized")
        self.assertEqual(totals[0].amount, Decimal("1.00"))
        self.assertIn('"coluna":"Receitas Brutas Realizadas"', totals[0].evidence_text)

    def test_preserves_legitimate_negative_value(self) -> None:
        totals = normalize_siconfi_annual_snapshot(
            snapshot(amount_override={"fundeb_deductions": "-125.40"})
        )

        self.assertEqual(totals[1].amount, Decimal("-125.40"))

    def test_fails_closed_when_one_required_metric_is_missing(self) -> None:
        source = snapshot()
        incomplete = replace(source, rows=source.rows[:-1])

        with self.assertRaisesRegex(
            SiconfiAnnualTotalsError, "processed_payables_registered"
        ):
            normalize_siconfi_annual_snapshot(incomplete)

    def test_fails_closed_when_source_repeats_a_metric(self) -> None:
        source = snapshot()
        duplicate = replace(source, rows=(*source.rows, source.rows[0]))

        with self.assertRaisesRegex(SiconfiAnnualTotalsError, "repetiu"):
            normalize_siconfi_annual_snapshot(duplicate)

    def test_fails_closed_for_other_municipality(self) -> None:
        source = snapshot()
        first = replace(
            source.rows[0], payload={**source.rows[0].payload, "cod_ibge": 2927408}
        )

        with self.assertRaisesRegex(SiconfiAnnualTotalsError, "Barreiras"):
            normalize_siconfi_annual_snapshot(
                replace(source, rows=(first, *source.rows[1:]))
            )

    def test_fails_closed_for_unofficial_source_url(self) -> None:
        with self.assertRaisesRegex(SiconfiAnnualTotalsError, "API oficial"):
            normalize_siconfi_annual_snapshot(
                replace(snapshot(), source_url="https://example.org/dca")
            )


if __name__ == "__main__":
    unittest.main()
