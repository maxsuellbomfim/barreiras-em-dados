import assert from "node:assert/strict";
import test from "node:test";

import {
  getPublicExpenseReportSourceConflicts,
  parseExpenseReportSourceConflicts,
} from "../../apps/web/lib/expense-report-source-conflicts.mjs";

const row = {
  expense_report_id: "00000000-0000-0000-0000-000000007009",
  fiscal_year: 2024,
  period_start: "2024-12-01",
  period_end: "2024-12-31",
  field_name: "total_reductions_amount",
  declared_amount: "263599171.60",
  calculated_amount: "263599171.68",
  difference_amount: "0.08",
  document_source_url: "https://example.org/expense-2024-12.pdf",
  document_artifact_sha256: "3".repeat(64),
  methodology_version: "public-expense-source-conflicts/1.0.0",
};

test("traduz divergencia oficial sem alterar os valores", () => {
  assert.deepEqual(parseExpenseReportSourceConflicts([row]), {
    state: "available",
    conflicts: [{
      expenseReportId: row.expense_report_id,
      fiscalYear: 2024,
      periodStart: "2024-12-01",
      periodEnd: "2024-12-31",
      fieldName: "total_reductions_amount",
      fieldLabel: "anulações",
      declaredAmount: "263599171.60",
      calculatedAmount: "263599171.68",
      differenceAmount: "0.08",
      documentSourceUrl: row.document_source_url,
      documentArtifactSha256: row.document_artifact_sha256,
      methodologyVersion: "public-expense-source-conflicts/1.0.0",
    }],
  });
});

test("rejeita campo desconhecido, hash invalido e payload parcial", () => {
  assert.deepEqual(parseExpenseReportSourceConflicts([
    { ...row, field_name: "invented_total" },
  ]), { state: "unavailable" });
  assert.deepEqual(parseExpenseReportSourceConflicts([
    { ...row, document_artifact_sha256: "invalid" },
  ]), { state: "unavailable" });
  assert.deepEqual(parseExpenseReportSourceConflicts({}), { state: "unavailable" });
});

test("cliente consulta somente o ano fiscal validado", async () => {
  const originalUrl = process.env.PUBLIC_DATA_SUPABASE_URL;
  const originalKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY;
  const originalFetch = global.fetch;
  process.env.PUBLIC_DATA_SUPABASE_URL = "https://example.supabase.co";
  process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY = "sb_publishable_fixture";
  let requestBody = null;
  global.fetch = async (_url, init) => {
    requestBody = JSON.parse(init.body);
    return { ok: true, json: async () => [row] };
  };
  try {
    const result = await getPublicExpenseReportSourceConflicts(2024);
    assert.equal(result.state, "available");
    assert.deepEqual(requestBody, { page_size: 100, fiscal_year_filter: 2024 });
  } finally {
    global.fetch = originalFetch;
    if (originalUrl === undefined) delete process.env.PUBLIC_DATA_SUPABASE_URL;
    else process.env.PUBLIC_DATA_SUPABASE_URL = originalUrl;
    if (originalKey === undefined) delete process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY;
    else process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY = originalKey;
  }
});
