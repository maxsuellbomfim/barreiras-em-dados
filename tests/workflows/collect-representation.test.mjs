import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workflow = await readFile(
  new URL("../../.github/workflows/collect-representation.yml", import.meta.url),
  "utf8",
);

test("execução manual aceita uma única fonte sem repetir as independentes", () => {
  assert.match(workflow, /source:[\s\S]*?type: choice/);
  for (const scope of [
    "all",
    "federal",
    "municipal",
    "state",
    "executive",
    "elections",
  ]) {
    assert.match(workflow, new RegExp(`- ${scope}`));
  }
  assert.match(
    workflow,
    /node \.github\/scripts\/resolve-representation-plan\.mjs "\$REQUESTED_SOURCE"/,
  );
  assert.match(workflow, /profile_matrix: \$\{\{ steps\.plan\.outputs\.profile_matrix \}\}/);
  assert.match(workflow, /include: \$\{\{ fromJSON\(needs\.plan\.outputs\.profile_matrix\) \}\}/);
});

test("fontes de perfis rodam em matriz sem cancelamento cruzado", () => {
  assert.match(workflow, /collect-profiles:/);
  assert.match(workflow, /fail-fast: false/);
  assert.match(workflow, /max-parallel: 1/);
  assert.match(
    workflow,
    /include: \$\{\{ fromJSON\(needs\.plan\.outputs\.profile_matrix\) \}\}/,
  );
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
  assert.match(
    workflow,
    /collect-elections:[\s\S]*?if: needs\.plan\.outputs\.collect_elections == 'true'/,
  );
  assert.match(
    workflow,
    /private-identities:[\s\S]*?if: needs\.collect-elections\.result == 'success'/,
  );
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
  assert.match(
    workflow,
    /PROFILES_REQUIRED: \$\{\{ needs\.plan\.outputs\.collect_profiles \}\}/,
  );
  assert.match(
    workflow,
    /ELECTIONS_REQUIRED: \$\{\{ needs\.plan\.outputs\.collect_elections \}\}/,
  );
  assert.match(workflow, /esperado=skipped/);
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
