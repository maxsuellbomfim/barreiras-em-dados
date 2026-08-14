import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

const script = fileURLToPath(
  new URL("../../.github/scripts/resolve-representation-plan.mjs", import.meta.url),
);

function resolvePlan(scope) {
  const result = spawnSync(process.execPath, [script, scope], {
    encoding: "utf8",
  });

  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

test("retry estadual executa somente a ALBA e preserva as demais fontes", () => {
  const plan = resolvePlan("state");

  assert.deepEqual(plan.profiles, [
    {
      source: "state",
      label: "deputados estaduais da Bahia",
      module: "barreiras_collectors.commands.collect_alba_deputies",
    },
  ]);
  assert.equal(plan.collectElections, false);
  assert.equal(plan.collectPrivateIdentities, false);
});

test("retry eleitoral não repete perfis parlamentares independentes", () => {
  const plan = resolvePlan("elections");

  assert.deepEqual(plan.profiles, []);
  assert.equal(plan.collectElections, true);
  assert.equal(plan.collectPrivateIdentities, true);
});

test("execução completa mantém as quatro fontes de perfil e o TSE", () => {
  const plan = resolvePlan("all");

  assert.deepEqual(
    plan.profiles.map(({ source }) => source),
    ["federal", "municipal", "state", "executive"],
  );
  assert.equal(plan.collectElections, true);
  assert.equal(plan.collectPrivateIdentities, true);
});

test("escopo desconhecido falha sem executar coletor", () => {
  const result = spawnSync(process.execPath, [script, "desconhecido"], {
    encoding: "utf8",
  });

  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /Escopo de representação inválido/);
  assert.equal(result.stdout, "");
});
