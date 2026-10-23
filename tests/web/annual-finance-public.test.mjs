import assert from "node:assert/strict";
import test from "node:test";
import { getPublicAnnualFinanceSummary } from "../../apps/web/lib/annual-finance-public.mjs";

const row = {
  fiscal_year: 2024, comparable_month_count: 12,
  first_period_start: "2024-01-01", last_period_start: "2024-12-01",
  revenue_amount: "9007199254740993.01", paid_amount: "10.02",
  operational_difference_amount: "9007199254740982.99", is_full_calendar_year: true,
};

test("consulta anual independente mantém centavos e falha sem publicar totais parciais", async (t) => {
  for (const [key, value] of Object.entries({
    PUBLIC_DATA_SUPABASE_URL: "https://example.supabase.co",
    PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_test",
  })) {
    const previous = process.env[key];
    process.env[key] = value;
    t.after(() => { if (previous === undefined) delete process.env[key]; else process.env[key] = previous; });
  }
  let payload = [row];
  let ok = true;
  t.mock.method(globalThis, "fetch", async (url, request) => {
    assert.match(url, /\/rpc\/get_public_annual_finance_summary$/);
    assert.deepEqual(JSON.parse(request.body), {});
    return { ok, json: async () => payload };
  });
  const result = await getPublicAnnualFinanceSummary();
  assert.equal(result.state, "available");
  assert.equal(result.summaries[0].revenueAmount, row.revenue_amount);
  assert.equal(result.summaries[0].comparableMonthCount, 12);
  for (const change of [
    { revenue_amount: 9007199254740993 },
    { operational_difference_amount: "0.00" },
    { comparable_month_count: 3 },
    { first_period_start: "2023-01-01" },
    { last_period_start: "2024-13-01" },
    { is_full_calendar_year: false },
  ]) {
    payload = [{ ...row, ...change }];
    assert.deepEqual(await getPublicAnnualFinanceSummary(), { state: "unavailable" });
  }
  payload = [row, row];
  assert.deepEqual(await getPublicAnnualFinanceSummary(), { state: "unavailable" });
  payload = [];
  assert.deepEqual(await getPublicAnnualFinanceSummary(), { state: "available", summaries: [] });
  ok = false;
  assert.deepEqual(await getPublicAnnualFinanceSummary(), { state: "unavailable" });
});
