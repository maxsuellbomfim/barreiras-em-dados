import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migration = await readFile(
  new URL("../../supabase/migrations/20260806100000_monthly_finance_closure_and_inventory.sql", import.meta.url),
  "utf8",
);
const page = await readFile(
  new URL("../../apps/web/app/financas/page.tsx", import.meta.url),
  "utf8",
);

test("fechamento mensal mantém a receita no nível do relatório", () => {
  assert.match(migration, /get_public_monthly_finance_closures/);
  assert.match(migration, /max\(revenue\.report_total_period_amount\)/);
  assert.match(migration, /monthly-finance-closure\/1\.0\.0/);
  assert.match(migration, /Não é superávit fiscal/);
  assert.match(page, /Uma leitura única das contas/);
  assert.match(page, /Diferença operacional/);
});

test("fechamento não aparece como saldo quando falta uma das fontes", () => {
  assert.match(migration, /when revenue\.report_count is null or expense\.report_count is null/);
  assert.match(migration, /then 'needs_data'/);
  assert.match(page, /aguardando reconciliação/);
});
