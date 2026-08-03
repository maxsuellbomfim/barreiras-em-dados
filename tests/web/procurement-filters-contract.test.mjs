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
const normalizedMigration = await readFile(
  new URL(
    "../../supabase/migrations/20260806230000_pncp_normalized_filtering.sql",
    import.meta.url,
  ),
  "utf8",
);
const executionMigration = await readFile(
  new URL(
    "../../supabase/migrations/20260807010000_pncp_execution_links.sql",
    import.meta.url,
  ),
  "utf8",
);
const client = await readFile(new URL("../../apps/web/lib/pncp-procurements.ts", import.meta.url), "utf8");
const page = await readFile(new URL("../../apps/web/app/licitacoes/page.tsx", import.meta.url), "utf8");
const optionsMigration = await readFile(
  new URL(
    "../../supabase/migrations/20260806220000_pncp_normalized_filter_options.sql",
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
  assert.match(client, /get_pncp_procurements_normalized/);
});

test("filtros estruturados usam a mesma chave normalizada do catálogo", () => {
  assert.match(normalizedMigration, /pncp_label_key/);
  assert.match(normalizedMigration, /set search_path = ''/);
  assert.match(normalizedMigration, /get_pncp_procurements_normalized/);
  assert.match(normalizedMigration, /pncp-procurements\/1\.3\.0/);
  assert.match(normalizedMigration, /modality_filter/);
  assert.match(normalizedMigration, /status_filter/);
  assert.match(normalizedMigration, /unit_filter/);
  assert.match(client, /get_pncp_procurements_normalized/);
});

test("execucao financeira do PNCP so e ligada por identificador oficial", () => {
  assert.match(executionMigration, /get_pncp_execution_summary/);
  assert.match(executionMigration, /p\.external_id = nullif\(trim\(control_number_filter\)/);
  assert.match(executionMigration, /current_contracts/);
  assert.match(executionMigration, /current_commitments/);
  assert.match(executionMigration, /current_liquidations/);
  assert.match(executionMigration, /current_payments/);
  assert.match(executionMigration, /pncp-execution-links\/1\.0\.0/);
  assert.match(executionMigration, /execution_summary jsonb/);
  assert.match(executionMigration, /pncp-procurements\/1\.4\.0/);
  assert.match(client, /executionSummary/);
});

test("sugestões de filtros vêm de opções PNCP preservadas", () => {
  assert.match(optionsMigration, /get_pncp_procurement_filter_options_normalized/);
  assert.match(optionsMigration, /modalidade/);
  assert.match(optionsMigration, /situacao/);
  assert.match(optionsMigration, /orgao/);
  assert.match(optionsMigration, /normalized_key/);
  assert.match(optionsMigration, /variants/);
  assert.match(client, /getPncpProcurementFilterOptions/);
  assert.match(client, /get_pncp_procurement_filter_options_normalized/);
  assert.match(page, /pncp-modalidades/);
  assert.match(page, /pncp-situacoes/);
  assert.match(page, /pncp-orgaos/);
});
