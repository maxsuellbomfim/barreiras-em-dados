import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migration = await readFile(
  new URL(
    "../../supabase/migrations/20260806200000_pncp_structured_filters.sql",
    import.meta.url,
  ),
  "utf8",
);
const client = await readFile(new URL("../../apps/web/lib/pncp-procurements.ts", import.meta.url), "utf8");
const page = await readFile(new URL("../../apps/web/app/licitacoes/page.tsx", import.meta.url), "utf8");

test("filtros PNCP restringem fornecedor, ano e texto sem recalcular valores", () => {
  assert.match(migration, /supplier_key_filter/);
  assert.match(migration, /fiscal_year_filter/);
  assert.match(migration, /query_filter/);
  assert.match(migration, /get_pncp_procurements_structured/);
  assert.match(migration, /modality_filter/);
  assert.match(migration, /status_filter/);
  assert.match(migration, /unit_filter/);
  assert.match(migration, /pncp-procurements\/1\.2\.0/);
});
test("pÃ¡gina oferece filtros GET e o cliente usa a RPC filtrÃ¡vel", () => {
  assert.match(page, /method="get"/);
  assert.match(page, /name="fornecedor"/);
  assert.match(page, /name="ano"/);
  assert.match(page, /name="q"/);
  assert.match(page, /name="modalidade"/);
  assert.match(page, /name="situacao"/);
  assert.match(page, /name="orgao"/);
  assert.match(client, /get_pncp_procurements_structured/);
});
