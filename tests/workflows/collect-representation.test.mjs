import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workflow = await readFile(
  new URL("../../.github/workflows/collect-representation.yml", import.meta.url),
  "utf8",
);

test("fontes de perfis rodam em matriz sem cancelamento cruzado", () => {
  assert.match(workflow, /collect-profiles:/);
  assert.match(workflow, /fail-fast: false/);
  assert.match(workflow, /max-parallel: 1/);
  for (const source of ["federal", "municipal", "state", "executive"]) {
    assert.match(workflow, new RegExp(`source: ${source}`));
  }
  assert.match(workflow, /COLLECTOR_MODULE: \$\{\{ matrix\.module \}\}/);
  assert.match(workflow, /python -B -m "\$COLLECTOR_MODULE"/);
});

test("TSE tem job isolado e identidade depende somente dele", () => {
  assert.match(
    workflow,
    /collect-elections:[\s\S]*?barreiras_collectors\.commands\.collect_tse_votes/,
  );
  assert.match(
    workflow,
    /private-identities:[\s\S]*?needs: collect-elections/,
  );
  assert.doesNotMatch(workflow, /private-identities:[\s\S]*?needs: collect-profiles/);
});

test("consolidação recebe resultados por ambiente e não oculta falhas", () => {
  assert.match(workflow, /name: Consolidar saúde da representação/);
  assert.match(workflow, /if: \$\{\{ always\(\) \}\}/);
  assert.match(
    workflow,
    /PROFILES_RESULT: \$\{\{ needs\.collect-profiles\.result \}\}/,
  );
  assert.match(
    workflow,
    /ELECTIONS_RESULT: \$\{\{ needs\.collect-elections\.result \}\}/,
  );
  assert.match(
    workflow,
    /IDENTITIES_RESULT: \$\{\{ needs\.private-identities\.result \}\}/,
  );
  assert.match(workflow, /exit 1/);
});

test("credenciais de coleta ficam fora do resumo e da identidade privada", () => {
  const privateJob = workflow.match(
    /private-identities:([\s\S]*?)\n  summarize:/,
  )?.[1];
  const summaryJob = workflow.match(/summarize:([\s\S]*)$/)?.[1];
  assert.ok(privateJob);
  assert.ok(summaryJob);
  for (const restricted of [
    "QUERIDO_DIARIO_DATABASE_URL",
    "QUERIDO_DIARIO_SUPABASE_WORKLOAD_EMAIL",
    "QUERIDO_DIARIO_SUPABASE_WORKLOAD_PASSWORD",
  ]) {
    assert.doesNotMatch(privateJob, new RegExp(restricted));
    assert.doesNotMatch(summaryJob, new RegExp(restricted));
  }
});
