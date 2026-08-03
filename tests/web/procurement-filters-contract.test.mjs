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
const evidenceMigration = await readFile(
  new URL(
    "../../supabase/migrations/20260807020000_pncp_execution_evidence.sql",
    import.meta.url,
  ),
  "utf8",
);
const documentEvidenceMigration = await readFile(
  new URL(
    "../../supabase/migrations/20260807030000_pncp_document_evidence_links.sql",
    import.meta.url,
  ),
  "utf8",
);
const client = await readFile(new URL("../../apps/web/lib/pncp-procurements.ts", import.meta.url), "utf8");
const page = await readFile(new URL("../../apps/web/app/licitacoes/page.tsx", import.meta.url), "utf8");
const explorer = await readFile(
  new URL("../../apps/web/app/licitacoes/procurement-explorer.tsx", import.meta.url),
  "utf8",
);
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

test("licitacoes exibem um unico painel de filtros no servidor", () => {
  assert.match(page, /className="procurement-filter-form" method="get"/);
  assert.match(page, /procurement-filter-note/);
  assert.match(explorer, /carregados/);
  assert.doesNotMatch(explorer, /className="procurement-filters"/);
  assert.doesNotMatch(explorer, /useState|useMemo|onChange=|filter-clear/);
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

test("vinculos PNCP preservam metadados de evidencia sem dados sensiveis", () => {
  assert.match(evidenceMigration, /evidence_rows/);
  assert.match(evidenceMigration, /raw\.raw_records/);
  assert.match(evidenceMigration, /raw\.raw_artifacts/);
  assert.match(evidenceMigration, /source_url/);
  assert.match(evidenceMigration, /sha256/);
  assert.match(evidenceMigration, /collector_version/);
  assert.match(evidenceMigration, /parser_version/);
  assert.match(evidenceMigration, /limit 20/);
  assert.match(evidenceMigration, /pncp-execution-links\/1\.1\.0/);
  assert.match(client, /evidenceCount/);
  assert.match(client, /startsWith\("https:\/\/"\)/);
});

test("documento filho oficial aparece sem abrir o Storage bruto", () => {
  assert.match(documentEvidenceMigration, /get_pncp_execution_summary_base/);
  assert.match(documentEvidenceMigration, /artifact_kind = 'document'/);
  assert.match(documentEvidenceMigration, /document_source_url/);
  assert.match(documentEvidenceMigration, /document_sha256/);
  assert.match(documentEvidenceMigration, /document_preserved/);
  assert.match(documentEvidenceMigration, /Storage bruto permanece privado/);
  assert.match(client, /documentSourceUrl/);
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
