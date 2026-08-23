import assert from "node:assert/strict";
import test from "node:test";

import {
  getPublicExpenseBudgetUnitSummary,
  parseExpenseBudgetUnitSummaryRows,
} from "../../apps/web/lib/expense-budget-unit-summary.mjs";

const reportId = "00000000-0000-0000-0000-000000008013";

function row(overrides = {}) {
  return {
    expense_report_id: reportId,
    budget_unit_code: "031101",
    budget_unit_name: "SECRETARIA MUNICIPAL DE SAÚDE",
    budget_unit_name_count: 1,
    line_count: 7,
    report_line_count: 10,
    allocated_line_count: 10,
    committed_period_amount: "1200.00",
    liquidated_period_amount: "1100.00",
    paid_period_amount: "1000.00",
    report_total_paid_amount: "2000.00",
    allocated_total_paid_amount: "2000.00",
    reconciliation_status: "matched",
    paid_share_percent: "50.00",
    methodology_version: "public-expense-budget-unit-summary/1.0.0",
    ...overrides,
  };
}

test("aceita somente atribuições integralmente reconciliadas", () => {
  assert.deepEqual(parseExpenseBudgetUnitSummaryRows([row()], reportId), {
    state: "available",
    budgetUnits: [{
      expenseReportId: reportId,
      budgetUnitCode: "031101",
      budgetUnitName: "SECRETARIA MUNICIPAL DE SAÚDE",
      budgetUnitNameCount: 1,
      lineCount: 7,
      reportLineCount: 10,
      allocatedLineCount: 10,
      committedPeriodAmount: "1200.00",
      liquidatedPeriodAmount: "1100.00",
      paidPeriodAmount: "1000.00",
      reportTotalPaidAmount: "2000.00",
      allocatedTotalPaidAmount: "2000.00",
      paidSharePercent: "50.00",
      methodologyVersion: "public-expense-budget-unit-summary/1.0.0",
    }],
  });
});

test("bloqueia cobertura parcial e conflito de nome sem publicar ranking", () => {
  assert.deepEqual(parseExpenseBudgetUnitSummaryRows([
    row({
      allocated_line_count: 9,
      reconciliation_status: "partial",
      paid_share_percent: null,
    }),
  ], reportId), {
    state: "conflict",
    reason: "partial",
    reportLineCount: 10,
    allocatedLineCount: 9,
  });
  assert.deepEqual(parseExpenseBudgetUnitSummaryRows([
    row({
      budget_unit_name_count: 2,
      reconciliation_status: "source_conflict",
      paid_share_percent: null,
    }),
  ], reportId), {
    state: "conflict",
    reason: "source_conflict",
    reportLineCount: 10,
    allocatedLineCount: 10,
  });
});

test("rejeita relatório trocado, decimal inválido e metodologia desconhecida", () => {
  assert.deepEqual(parseExpenseBudgetUnitSummaryRows([
    row({ expense_report_id: "00000000-0000-0000-0000-000000008099" }),
  ], reportId), { state: "unavailable" });
  assert.deepEqual(parseExpenseBudgetUnitSummaryRows([
    row({ paid_period_amount: "1e3" }),
  ], reportId), { state: "unavailable" });
  assert.deepEqual(parseExpenseBudgetUnitSummaryRows([
    row({ methodology_version: "unknown" }),
  ], reportId), { state: "unavailable" });
});

test("cliente envia somente o UUID à RPC agregada", async () => {
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
    const result = await getPublicExpenseBudgetUnitSummary(reportId);
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
