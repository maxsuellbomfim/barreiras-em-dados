import assert from "node:assert/strict";
import test from "node:test";

import {
  getPublicExpenseCategorySummary,
  parseExpenseCategorySummaryRows,
} from "../../apps/web/lib/expense-category-summary.mjs";

const reportId = "00000000-0000-0000-0000-000000008013";

function row(overrides = {}) {
  return {
    expense_report_id: reportId,
    expense_code: "3.3.9.0.39.00.00",
    source_description: "Outros Servicos Terceiros Pessoa",
    source_description_count: 1,
    line_count: 7,
    committed_period_amount: "1200.00",
    liquidated_period_amount: "1100.00",
    paid_period_amount: "1000.00",
    report_total_paid_amount: "2000.00",
    aggregated_total_paid_amount: "2000.00",
    reconciliation_status: "matched",
    paid_share_percent: "50.00",
    methodology_version: "public-expense-category-summary/1.0.0",
    ...overrides,
  };
}

test("aceita somente resumo reconciliado e decimal", () => {
  assert.deepEqual(parseExpenseCategorySummaryRows([row()], reportId), {
    state: "available",
    categories: [{
      expenseReportId: reportId,
      expenseCode: "3.3.9.0.39.00.00",
      sourceDescription: "Outros Servicos Terceiros Pessoa",
      sourceDescriptionCount: 1,
      lineCount: 7,
      committedPeriodAmount: "1200.00",
      liquidatedPeriodAmount: "1100.00",
      paidPeriodAmount: "1000.00",
      reportTotalPaidAmount: "2000.00",
      aggregatedTotalPaidAmount: "2000.00",
      paidSharePercent: "50.00",
      methodologyVersion: "public-expense-category-summary/1.0.0",
    }],
  });
});

test("bloqueia percentuais quando as linhas divergem do total do relatório", () => {
  assert.deepEqual(parseExpenseCategorySummaryRows([
    row({
      aggregated_total_paid_amount: "1999.99",
      reconciliation_status: "mismatch",
      paid_share_percent: null,
    }),
  ], reportId), {
    state: "conflict",
    reportTotalPaidAmount: "2000.00",
    aggregatedTotalPaidAmount: "1999.99",
  });
});

test("rejeita payload parcial, relatório trocado e metodologia desconhecida", () => {
  assert.deepEqual(parseExpenseCategorySummaryRows([
    row({ expense_report_id: "00000000-0000-0000-0000-000000008099" }),
  ], reportId), { state: "unavailable" });
  assert.deepEqual(parseExpenseCategorySummaryRows([
    row({ paid_share_percent: null }),
  ], reportId), { state: "unavailable" });
  assert.deepEqual(parseExpenseCategorySummaryRows([
    row({ methodology_version: "unknown" }),
  ], reportId), { state: "unavailable" });
});

test("cliente envia somente o UUID do relatório à RPC agregada", async () => {
  const originalUrl = process.env.PUBLIC_DATA_SUPABASE_URL;
  const originalKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY;
  const originalFetch = global.fetch;
  process.env.PUBLIC_DATA_SUPABASE_URL = "https://example.supabase.co";
  process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY = "sb_publishable_fixture";
  let requestBody = null;
  global.fetch = async (_url, init) => {
    requestBody = JSON.parse(init.body);
    return { ok: true, json: async () => [row()] };
  };

  try {
    const result = await getPublicExpenseCategorySummary(reportId);
    assert.equal(result.state, "available");
    assert.deepEqual(requestBody, { report_filter: reportId });
  } finally {
    global.fetch = originalFetch;
    if (originalUrl === undefined) delete process.env.PUBLIC_DATA_SUPABASE_URL;
    else process.env.PUBLIC_DATA_SUPABASE_URL = originalUrl;
    if (originalKey === undefined) {
      delete process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY;
    } else {
      process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY = originalKey;
    }
  }
});
