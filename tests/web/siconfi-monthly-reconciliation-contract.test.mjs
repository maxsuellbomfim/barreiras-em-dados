import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  SICONFI_RECONCILIATION_METRICS,
  parseSiconfiMonthlyReconciliation,
} from "../../apps/web/lib/siconfi-monthly-reconciliation-parser.mjs";

function row(metricKey, overrides = {}) {
  return {
    fiscal_year: 2025,
    metric_key: metricKey,
    annual_amount: "100.00",
    monthly_sum_amount: "100.00",
    difference_amount: "0",
    observed_months: 12,
    missing_months: [],
    reconciliation_status: "matched_exact",
    reconciliation_note: "As fontes conferem.",
    methodology_version: "siconfi-monthly-reconciliation/1.0.0",
    ...overrides,
  };
}

test("accepts a complete three-stage reconciliation with exact decimal strings", () => {
  const result = parseSiconfiMonthlyReconciliation(
    SICONFI_RECONCILIATION_METRICS.map((metricKey) =>
      row(metricKey, { difference_amount: "0.00" }),
    ),
  );
  assert.equal(result.length, 1);
  assert.equal(result[0].metrics.length, 3);
  assert.equal(result[0].metrics[0].differenceAmount, "0.00");
});

test("accepts an incomplete year only without a partial comparison", () => {
  const result = parseSiconfiMonthlyReconciliation(
    SICONFI_RECONCILIATION_METRICS.map((metricKey) =>
      row(metricKey, {
        monthly_sum_amount: null,
        difference_amount: null,
        observed_months: 11,
        missing_months: [4],
        reconciliation_status: "incomplete_months",
      }),
    ),
  );
  assert.equal(result[0].metrics[0].monthlySumAmount, null);
  assert.deepEqual(result[0].metrics[0].missingMonths, [4]);
});

test("rejects partial, duplicate and semantically inconsistent projections", () => {
  const complete = SICONFI_RECONCILIATION_METRICS.map((metricKey) => row(metricKey));
  assert.equal(parseSiconfiMonthlyReconciliation(complete.slice(0, 2)), null);
  assert.equal(parseSiconfiMonthlyReconciliation([...complete, complete[0]]), null);
  assert.equal(
    parseSiconfiMonthlyReconciliation(
      complete.map((item, index) =>
        index === 0
          ? { ...item, observed_months: 11, missing_months: [4] }
          : item,
      ),
    ),
    null,
  );
  assert.equal(
    parseSiconfiMonthlyReconciliation(
      complete.map((item, index) =>
        index === 0
          ? {
              ...item,
              difference_amount: "10.00",
              reconciliation_status: "matched_exact",
            }
          : item,
      ),
    ),
    null,
  );
});

test("finance page explains reconciliation without accusing or comparing revenue", async () => {
  const component = await readFile(
    new URL(
      "../../apps/web/app/financas/finance-siconfi-annual-totals.tsx",
      import.meta.url,
    ),
    "utf8",
  );
  const page = await readFile(
    new URL("../../apps/web/app/financas/page.tsx", import.meta.url),
    "utf8",
  );
  assert.match(page, /getPublicSiconfiMonthlyReconciliation\(\)/);
  assert.match(page, /reconciliationYears=\{siconfiReconciliationYears\}/);
  assert.match(component, /Os 12 meses conferem com o ano/);
  assert.match(component, /Diferença entre fontes não é prova de irregularidade/);
  assert.match(component, /Receita não entra nesta comparação/);
  assert.match(component, /Ver a conferência dos anos anteriores/);
  assert.match(component, /"abril"/);
  assert.match(component, /Não comparado\. Meses ausentes/);
  assert.doesNotMatch(component, /corrupção|fraude/i);
});
