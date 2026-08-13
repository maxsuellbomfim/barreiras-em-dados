import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migration = await readFile(
  new URL(
    "../../supabase/migrations/20260813171732_register_bahia_state_loa_amendments.sql",
    import.meta.url,
  ),
  "utf8",
);
const workflow = await readFile(
  new URL("../../.github/workflows/collect-finance-documents.yml", import.meta.url),
  "utf8",
);
const methodology = await readFile(
  new URL("../../docs/PARLIAMENTARY_TRANSFERS_METHODOLOGY.md", import.meta.url),
  "utf8",
);
const dataSources = await readFile(
  new URL("../../docs/DATA_SOURCES.md", import.meta.url),
  "utf8",
);

test("fonte LOA territorial permanece privada e separada da execucao", () => {
  assert.match(migration, /'bahia-seplan-budget'/);
  assert.match(migration, /'state-loa-amendment-annexes'/);
  assert.match(migration, /'bahia\/loa-emendas-estaduais\/'/);
  assert.match(migration, /'budget_stage', 'authorized'/);
  assert.match(migration, /official_2021_annex_iii_link_points_to_2020_document/);
  assert.doesNotMatch(migration, /grant\s+(?:select|execute)[\s\S]+\bto\s+anon\b/i);
});

test("workflow preserva 2021 a 2026 sem publicar ranking", () => {
  const [, job] = workflow.split(/\n  bahia_state_loa_amendments:/);
  assert.match(workflow, /include_bahia_state_loa_amendments:/);
  assert.ok(job, "o job dos anexos LOA deve existir");
  assert.match(job, /collect_bahia_state_loa_amendments/);
  assert.match(job, /--year-from "2021"/);
  assert.match(job, /--year-to "2026"/);
  assert.doesNotMatch(job, /commands\.(?:publish|normalize)|ranking/i);
});

test("documentacao proibe confundir autorizacao com pagamento", () => {
  assert.match(methodology, /autorizad[ao]/i);
  assert.match(methodology, /n.o (?:significa|equivale) pagamento/i);
  assert.match(dataSources, /Anexo III/i);
  assert.match(dataSources, /2021[\s\S]{0,300}2020/i);
});
