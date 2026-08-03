import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migration = await readFile(
  new URL("../../supabase/migrations/20260806100000_monthly_finance_closure_and_inventory.sql", import.meta.url),
  "utf8",
);
const page = await readFile(
  new URL("../../apps/admin/app/page.tsx", import.meta.url),
  "utf8",
);

test("inventário financeiro é restrito a revisores e mostra o último erro", () => {
  assert.match(migration, /get_finance_ingestion_inventory/);
  assert.match(migration, /api\.is_active_reviewer\(\)/);
  assert.match(migration, /latest_error_detail/);
  assert.match(page, /Documentos financeiros/);
  assert.match(page, /Preservado — ainda não processado/);
  assert.match(page, /latest_error_detail/);
});
