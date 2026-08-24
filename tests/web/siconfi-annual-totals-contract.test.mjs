import assert from "node:assert/strict";
import test from "node:test";

import {
  SICONFI_ANNUAL_METRICS,
  parseSiconfiAnnualRows,
} from "../../apps/web/lib/siconfi-annual-totals-parser.mjs";

function row(metricKey, index, overrides = {}) {
  return {
    total_id: `00000000-0000-0000-0000-${String(index).padStart(12, "0")}`,
    fiscal_year: 2025,
    metric_key: metricKey,
    amount: metricKey === "fundeb_deductions" ? "-125.40" : `${index}.00`,
    currency: "BRL",
    official_annex: "DCA-Anexo I-C",
    official_label: "Padrão",
    official_column_label: metricKey,
    official_account_code: "TotalReceitas",
    official_account_label: "TOTAL DAS RECEITAS (III) = (I + II)",
    source_url: "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca",
    source_artifact_sha256: "a".repeat(64),
    source_retrieved_at: "2026-08-24T12:00:00+00:00",
    methodology_version: "siconfi-annual-totals/1.0.0",
    ...overrides,
  };
}

test("accepts only a complete seven-metric year and preserves negative values", () => {
  const result = parseSiconfiAnnualRows(
    SICONFI_ANNUAL_METRICS.map((metric, index) => row(metric, index + 1)),
  );

  assert.equal(result.length, 1);
  assert.equal(result[0].metrics.length, 7);
  assert.equal(result[0].metrics[1].amount, "-125.40");
});

test("rejects partial, duplicate or mixed-artifact annual projections", () => {
  const complete = SICONFI_ANNUAL_METRICS.map((metric, index) =>
    row(metric, index + 1),
  );
  assert.equal(parseSiconfiAnnualRows(complete.slice(0, 6)), null);
  assert.equal(parseSiconfiAnnualRows([...complete, complete[0]]), null);
  assert.equal(
    parseSiconfiAnnualRows([
      ...complete.slice(0, 6),
      { ...complete[6], source_artifact_sha256: "b".repeat(64) },
    ]),
    null,
  );
});
