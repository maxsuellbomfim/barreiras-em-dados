import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workflow = await readFile(
  new URL("../../.github/workflows/collect-municipal-commitments.yml", import.meta.url),
  "utf8",
);

test("empenhos: meses fechados, identidade do corredor municipal e sem publicação", () => {
  assert.match(workflow, /cron: "17 9 3,20 \* \*"/);
  assert.match(workflow, /barreiras_collectors\.commands\.collect_municipal_commitments/);
  assert.match(workflow, /MUNICIPAL_TRANSPARENCY_SUPABASE_WORKLOAD_PASSWORD/);
  // Entradas do dispatch só chegam ao shell por variável de ambiente.
  assert.doesNotMatch(workflow, /run: [^\n]*\$\{\{ inputs\./);
  assert.doesNotMatch(workflow, /^\s+python[^\n]*\$\{\{/m);
  assert.match(workflow, /options:\s*\n\s*- "1"\s*\n\s*- "3"\s*\n\s*- "6"/);
  assert.doesNotMatch(workflow, /publish_/);
  assert.match(workflow, /cancel-in-progress: false/);
  assert.match(workflow, /permissions:\s*\n\s*contents: read/);
});

test("migration registra a rota WebRun sem publicação automática", async () => {
  const migration = await readFile(
    new URL(
      "../../supabase/migrations/20260924001844_register_municipal_commitments_source.sql",
      import.meta.url,
    ),
    "utf8",
  );
  assert.match(migration, /'prefeitura-barreiras-despesas-webrun'/);
  assert.match(migration, /'webrun-empenhos', 'html'/);
  assert.match(migration, /'automatic_publication', false/);
  assert.match(migration, /'raw_visibility', 'private'/);
});
