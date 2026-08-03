import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migration = await readFile(
  new URL(
    "../../supabase/migrations/20260806170000_finance_coverage_public_projection.sql",
    import.meta.url,
  ),
  "utf8",
);
const client = await readFile(new URL("../../apps/web/lib/finance-coverage.ts", import.meta.url), "utf8");

test("projeção de cobertura separa ausência de zero", () => {
  assert.match(migration, /get_public_finance_coverage/);
  assert.match(migration, /revenue_only/);
  assert.match(migration, /expense_only/);
  assert.match(migration, /'missing'/);
  assert.match(migration, /não significa receita ou despesa zero/);
  assert.match(migration, /finance-coverage\/1\.0\.0/);
});

test("cliente público valida a metodologia e estados", () => {
  assert.match(client, /finance-coverage\/1\.0\.0/);
  assert.match(client, /PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY/);
  assert.match(client, /coverageStatus/);
});
