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
const optionsMigration = await readFile(
  new URL(
    "../../supabase/migrations/20260806210000_pncp_filter_options.sql",
    import.meta.url,
  ),
  "utf8",
);

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

test("sugestões de filtros vêm de opções PNCP preservadas", () => {
  assert.match(optionsMigration, /get_pncp_procurement_filter_options/);
  assert.match(optionsMigration, /modalidade/);
  assert.match(optionsMigration, /situacao/);
  assert.match(optionsMigration, /orgao/);
  assert.match(client, /getPncpProcurementFilterOptions/);
  assert.match(page, /pncp-modalidades/);
  assert.match(page, /pncp-situacoes/);
  assert.match(page, /pncp-orgaos/);
});
