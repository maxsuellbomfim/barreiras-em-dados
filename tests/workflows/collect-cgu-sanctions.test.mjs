import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workflow = await readFile(
  new URL(
    "../../.github/workflows/collect-cgu-sanctions.yml",
    import.meta.url,
  ),
  "utf8",
);

test("sanções usam a chave via secret e nunca em texto no workflow", () => {
  assert.match(
    workflow,
    /TRANSPARENCIA_API_KEY: \$\{\{ secrets\.TRANSPARENCIA_API_KEY \}\}/,
  );
  assert.doesNotMatch(
    workflow,
    /chave-api-dados|TRANSPARENCIA_API_KEY:\s*["']?[0-9a-f]{8}/,
    "nenhum valor literal de chave pode aparecer no arquivo",
  );
});

test("a coleta roda diariamente em lote retomável com identidade municipal", () => {
  assert.match(workflow, /cron: "40 5 \* \* \*"/);
  assert.match(workflow, /workflow_dispatch/);
  assert.match(
    workflow,
    /barreiras_collectors\.commands\.collect_cgu_sanctions\s+--limit 100/,
  );
  assert.match(
    workflow,
    /MUNICIPAL_TRANSPARENCY_SUPABASE_WORKLOAD_EMAIL/,
  );
  assert.match(workflow, /timeout-minutes: 45/);
});
