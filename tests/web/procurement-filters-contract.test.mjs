import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migration = await readFile(
  new URL(
    "../../supabase/migrations/20260806193000_public_procurement_filters.sql",
    import.meta.url,
  ),
  "utf8",
);
const page = await readFile(new URL("../../apps/web/app/licitacoes/page.tsx", import.meta.url), "utf8");
const client = await readFile(new URL("../../apps/web/lib/pncp-procurements.ts", import.meta.url), "utf8");

test("filtros PNCP restringem fornecedor, ano e texto sem recalcular valores", () => {
  assert.match(migration, /get_pncp_procurements_filtered/);
  assert.match(migration, /supplier_key_filter/);
  assert.match(migration, /fiscal_year_filter/);
  assert.match(migration, /query_filter/);
  assert.match(migration, /pncp-procurements\/1\.1\.0/);
});

test("página oferece filtros GET e o cliente usa a RPC filtrável", () => {
  assert.match(page, /method="get"/);
  assert.match(page, /name="fornecedor"/);
  assert.match(page, /name="ano"/);
  assert.match(page, /name="q"/);
  assert.match(client, /get_pncp_procurements_filtered/);
});
