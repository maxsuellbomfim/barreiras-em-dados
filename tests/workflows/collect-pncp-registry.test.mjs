import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { runInNewContext } from "node:vm";

const workflow = await readFile(
  new URL("../../.github/workflows/collect-pncp-registry.yml", import.meta.url),
  "utf8",
);

const stepBlocks = workflow.split(/\r?\n      - name: /).slice(1);
function step(name) {
  const found = stepBlocks.find((block) => block.split(/\r?\n/, 1)[0] === name);
  assert.ok(found, `etapa ausente: ${name}`);
  return found;
}

function enabled(name, {
  mode = "full", event = "workflow_dispatch", schedule = "", priorSucceeded = true,
} = {}) {
  const expression = step(name).match(/^        if: (.+)$/m)?.[1]?.trim();
  return priorSucceeded && (expression ? runInNewContext(expression, {
    github: { event_name: event, event: { schedule } }, inputs: { mode },
  }) : true);
}

const registry = "Preservar cadastro";
const weekly = "Preservar contratações da última semana";
const backfill = "Backfill retroativo de contratações";
const replay = "Reprocessar janela PNCP";
const items = "Preservar itens e resultados das contratações";
const contracts = "Preservar contratos e empenhos das contratações";
const normalize = "Normalizar contratos PNCP";

test("evidencia municipal executa apenas o par privado e nunca normaliza", () => {
  const evidence = "Preservar vínculo municipal privado";
  for (const name of [registry, weekly, backfill, replay, items, contracts, normalize])
    assert.equal(enabled(name, { mode: "municipal_link_evidence" }), false, name);
  assert.equal(enabled(evidence, { mode: "municipal_link_evidence" }), true);
  for (const mode of ["full", "backfill", "contracts_only", "registry_only"])
    assert.equal(enabled(evidence, { mode }), false);
  assert.equal(enabled(evidence, { event: "schedule" }), false);
  assert.equal(enabled(evidence, { mode: "municipal_link_evidence", priorSucceeded: false }), false);
  assert.doesNotMatch(step(evidence), /continue-on-error/);
  assert.match(step(evidence), /collect_pncp_municipal_link_evidence/);
});

test("falha cadastral permite os passos independentes sem ocultar o resultado", () => {
  const registryStep = step(registry);
  assert.match(registryStep, /^        id: collect_registry$/m);
  assert.match(registryStep, /^        continue-on-error: true$/m);
  const registryFailureConclusionIsSuccess =
    /^        continue-on-error: true$/m.test(registryStep);
  for (const name of [weekly, backfill, items, contracts, normalize]) {
    assert.equal(
      enabled(name, { priorSucceeded: registryFailureConclusionIsSuccess }),
      true,
      name,
    );
  }
  const gate = step("Sinalizar falha parcial da coleta");
  assert.match(gate, /^        if: always\(\)$/m);
  assert.match(
    gate,
    /PNCP_REGISTRY_OUTCOME: \$\{\{ steps\.collect_registry\.outcome \}\}/,
  );
  assert.match(
    gate,
    /PNCP_CONTRACTS_OUTCOME: \$\{\{ steps\.collect_contracts\.outcome \}\}/,
  );
  assert.doesNotMatch(gate, /^        continue-on-error:/m);
});

test("modo somente cadastro exclui todas as consultas e normalizacoes de compras", () => {
  assert.match(workflow, /^          - registry_only$/m);
  assert.equal(enabled(registry, { mode: "registry_only" }), true);
  for (const name of [weekly, backfill, replay, items, contracts, normalize]) {
    assert.equal(enabled(name, { mode: "registry_only" }), false, name);
  }
});

test("escopos existentes preservam o mesmo conjunto de etapas", () => {
  const names = [registry, weekly, backfill, replay, items, contracts, normalize];
  const scenarios = [
    [{ mode: "full" }, [registry, weekly, backfill, items, contracts, normalize]],
    [{ mode: "backfill" }, [backfill, items, contracts, normalize]],
    [{ mode: "contracts_only" }, [contracts, normalize]],
    [{ mode: "replay_window" }, [replay, items, contracts, normalize]],
    [
      { event: "schedule", schedule: "13 9 * * 1" },
      [registry, weekly, items, contracts, normalize],
    ],
    [
      { event: "schedule", schedule: "43 5 * * *" },
      [backfill, items, contracts, normalize],
    ],
  ];
  for (const [context, expected] of scenarios) {
    assert.deepEqual(names.filter((name) => enabled(name, context)), expected);
    for (const name of names) {
      assert.equal(enabled(name, { ...context, priorSucceeded: false }), false);
    }
  }
});

test("gate shell reprova cadastro, itens ou contratos e aceita cadastro nao solicitado", () => {
  const gate = step("Sinalizar falha parcial da coleta");
  const shellBody = gate.split(/\r?\n        run: \|\r?\n/)[1];
  assert.ok(shellBody, "gate shell ausente");
  const script = shellBody
    .split(/\r?\n/).map((line) => line.replace(/^          /, "")).join("\n");
  const bash = process.platform === "win32"
    ? "C:\\Program Files\\Git\\bin\\bash.exe"
    : "bash";
  for (const [registryOutcome, itemsOutcome, contractsOutcome, expectedStatus] of [
    ["success", "success", "success", 0],
    ["failure", "success", "success", 1],
    ["failure", "skipped", "success", 1],
    ["success", "failure", "success", 1],
    ["success", "success", "failure", 1],
    ["failure", "failure", "failure", 1],
    ["skipped", "success", "skipped", 0],
    ["skipped", "skipped", "skipped", 0],
    ["success", "skipped", "skipped", 0],
  ]) {
    const result = spawnSync(bash, ["--noprofile", "--norc", "-c", script], {
      encoding: "utf8", timeout: 5000, windowsHide: true,
      env: {
        PATH: process.env.PATH,
        SystemRoot: process.env.SystemRoot,
        PNCP_REGISTRY_OUTCOME: registryOutcome,
        PNCP_ITEMS_OUTCOME: itemsOutcome,
        PNCP_CONTRACTS_OUTCOME: contractsOutcome,
      },
    });
    assert.ifError(result.error);
    assert.equal(
      result.status,
      expectedStatus,
      `${registryOutcome}/${itemsOutcome}: ${result.stderr}`,
    );
  }
});

test("workflow PNCP preserva contratos/empenhos depois de itens e resultados", () => {
  assert.match(step(items), /collect_pncp_itens/);
  assert.match(step(contracts), /collect_pncp_contratos/);
  assert.match(step(normalize), /normalize_pncp_contracts/);
  assert.ok(stepBlocks.indexOf(step(items)) < stepBlocks.indexOf(step(contracts)));
  assert.ok(stepBlocks.indexOf(step(contracts)) < stepBlocks.indexOf(step(normalize)));
  assert.match(workflow, /PERSISTENCE_MODE: postgres-supabase/);
  assert.match(workflow, /SUPABASE_RAW_ARTIFACTS_BUCKET: raw-artifacts/);
});

test("falha em itens nao impede contratos e permanece visivel no resultado", () => {
  assert.match(
    step(items),
    /id: collect_items[\s\S]*?continue-on-error: true[\s\S]*?collect_pncp_itens/,
  );
  assert.match(
    step(contracts),
    /id: collect_contracts[\s\S]*?collect_pncp_contratos/,
  );
  assert.match(
    step("Sinalizar falha parcial da coleta"),
    /PNCP_ITEMS_OUTCOME: \$\{\{ steps\.collect_items\.outcome \}\}/,
  );
  assert.match(workflow, /if \[ "\$PNCP_ITEMS_OUTCOME" = "failure" \]/);
  assert.match(step("Sinalizar falha parcial da coleta"), /exit /);
});

test("falha em contratos nao impede normalizacao e permanece visivel no resultado", () => {
  assert.match(
    step(contracts),
    /id: collect_contracts[\s\S]*?continue-on-error: true[\s\S]*?collect_pncp_contratos/,
  );
  assert.match(
    step(normalize),
    /if: github\.event_name != 'workflow_dispatch' \|\| \(inputs\.mode != 'registry_only' && inputs\.mode != 'municipal_link_evidence'\)[\s\S]*?normalize_pncp_contracts/,
  );
  assert.match(
    step("Sinalizar falha parcial da coleta"),
    /PNCP_CONTRACTS_OUTCOME: \$\{\{ steps\.collect_contracts\.outcome \}\}/,
  );
  assert.match(workflow, /if \[ "\$PNCP_CONTRACTS_OUTCOME" = "failure" \]/);
});

test("workflow manual oferece execucao apenas de contratos", () => {
  assert.match(step(items), /inputs\.mode != 'contracts_only'/);
});

test("workflow manual permite replay explícito de uma janela falha", () => {
  assert.match(workflow, /replay_window/);
  assert.match(workflow, /replay_since/);
  assert.match(workflow, /replay_until/);
  assert.match(step(replay), /PNCP_REPLAY_SINCE/);
  assert.match(step(replay), /PNCP_REPLAY_UNTIL/);
  assert.match(step(replay), /--since "\$PNCP_REPLAY_SINCE"/);
  assert.match(step(replay), /--until "\$PNCP_REPLAY_UNTIL"/);
});
