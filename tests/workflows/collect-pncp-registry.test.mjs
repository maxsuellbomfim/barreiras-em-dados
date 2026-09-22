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

test("diagnóstico de rede é limitado ao replay isolado com falha", () => {
  const block = step("Diagnosticar rede PNCP sem persistir");
  const expression = block.match(/^        if: (.+)$/m)[1];
  for (const mode of ["discovery_only", "full", "replay_window"])
    for (const outcome of ["failure", "success", "skipped"])
      assert.equal(runInNewContext(expression, {
        github: { event_name: "workflow_dispatch" }, inputs: { mode },
        steps: { collect_replay: { outcome } },
      }), mode === "discovery_only" && outcome === "failure");
  assert.match(block, /--connect-timeout 10 --max-time 20/);
  assert.match(block, /--output \/dev\/null/);
  assert.match(block, /--proto '=https'/);
  assert.doesNotMatch(block, /--retry|--insecure|--verbose|secrets\./);
  assert.match(block, /codigoModalidadeContratacao=1/);
  assert.match(block, /não comprova cobertura/);
  const script = block.split(/\r?\n        run: \|\r?\n/)[1]
    .split(/\r?\n/).map(line => line.replace(/^          /, "")).join("\n");
  const bash = process.platform === "win32" ? "C:\\Program Files\\Git\\bin\\bash.exe" : "bash";
  for (const code of [0, 28]) {
    const result = spawnSync(bash, ["--noprofile", "--norc", "-c",
      `set -e; curl() { printf '%s\\n' "$@"; return ${code}; };\n${script}`], {
      encoding: "utf8", timeout: 5000, windowsHide: true,
      env: { PATH: process.env.PATH, SystemRoot: process.env.SystemRoot,
        PNCP_REPLAY_SINCE: "2024-03-15", PNCP_REPLAY_UNTIL: "2024-03-15" },
    });
    assert.equal(result.status, code);
    assert.match(result.stdout, /dataInicial=20240315&dataFinal=20240315/);
  }
  const invalid = spawnSync(bash, ["--noprofile", "--norc", "-c",
    `set -e; curl() { echo unexpected_request; };\n${script}`], {
    encoding: "utf8", timeout: 5000, windowsHide: true,
    env: { PATH: process.env.PATH, SystemRoot: process.env.SystemRoot,
      PNCP_REPLAY_SINCE: "2024-03-15&other=value", PNCP_REPLAY_UNTIL: "2024-03-15" },
  });
  assert.notEqual(invalid.status, 0);
  assert.doesNotMatch(invalid.stdout, /unexpected_request/);
});

test("replay de descoberta isolada não executa itens, contratos ou normalização", () => {
  assert.match(workflow, /^          - discovery_only$/m);
  assert.equal(enabled(replay, {mode:"discovery_only"}), true);
  for (const name of [registry, weekly, backfill, items, contracts, normalize])
    assert.equal(enabled(name, {mode:"discovery_only"}), false, name);
});

test("contratos convertem somente código 2 em aviso, sem ocultar falha técnica", () => {
  const script = step(contracts).split(/\r?\n        run: \|\r?\n/)[1]
    .split(/\r?\n/).map(line => line.replace(/^          /, "")).join("\n");
  const bash = process.platform === "win32" ? "C:\\Program Files\\Git\\bin\\bash.exe" : "bash";
  for (const code of [0, 1, 2, 124, 137]) {
    const result = spawnSync(bash, ["--noprofile", "--norc", "-c",
      `set -e; python() { return ${code}; }; export GITHUB_STEP_SUMMARY=/dev/null;\n${script}`], {encoding:"utf8"});
    assert.equal(result.status, code === 2 ? 0 : code);
    assert.equal(result.stdout.includes("::warning::"), code === 2);
  }
  assert.match(script,/cobertura completa nem inexistência/);
});

test("consulta por publicação fica isolada e transmite inputs somente pelo ambiente", () => {
  const evidence = "Preservar página privada por publicação";
  assert.match(workflow, /^          - publication_evidence$/m);
  for (const name of [registry, weekly, backfill, replay, items, contracts, normalize,
    "Preservar vínculo municipal privado", "Publicar par revisado do Fundo Social"])
    assert.equal(enabled(name, { mode: "publication_evidence" }), false, name);
  assert.equal(enabled(evidence, { mode: "publication_evidence" }), true);
  assert.equal(enabled(evidence, { mode: "publication_evidence", priorSucceeded: false }), false);
  for (const mode of ["full", "items_only", "contracts_only", "registry_only", "backfill", "replay_window", "municipal_link_evidence"])
    assert.equal(enabled(evidence, { mode }), false);
  assert.equal(enabled(evidence, { event: "schedule" }), false);
  const block = step(evidence);
  assert.doesNotMatch(block, /continue-on-error/);
  assert.match(block, /PNCP_PUBLICATION_PAGE: \$\{\{ inputs.publication_page \}\}/);
  assert.match(block, /--since "\$PNCP_REPLAY_SINCE"/);
  assert.match(block, /--until "\$PNCP_REPLAY_UNTIL"/);
  assert.match(block, /--page "\$PNCP_PUBLICATION_PAGE"/);
  assert.doesNotMatch(block.split('run: |')[1], /\$\{\{/);
});

test("falhas de descoberta não bloqueiam etapas independentes e reprovam o gate", () => {
  const gate = step("Sinalizar falha parcial da coleta");
  const script = gate.split(/\r?\n        run: \|\r?\n/)[1]
    .split(/\r?\n/).map(line => line.replace(/^          /, "")).join("\n");
  for (const [name, id, envName] of [
    [weekly, "collect_weekly", "PNCP_WEEKLY_OUTCOME"],
    [backfill, "collect_backfill", "PNCP_BACKFILL_OUTCOME"],
    [replay, "collect_replay", "PNCP_REPLAY_OUTCOME"],
  ]) {
    assert.match(step(name), new RegExp(`^        id: ${id}$`, "m"));
    assert.match(step(name), /^        continue-on-error: true$/m);
    assert.ok(gate.includes(`${envName}: $` + `{{ steps.${id}.outcome }}`));
    for (const downstream of [items, contracts, normalize])
      assert.equal(enabled(downstream, { priorSucceeded: true }), true);
    const result = spawnSync(process.platform === "win32" ? "C:\\Program Files\\Git\\bin\\bash.exe" : "bash",
      ["--noprofile", "--norc", "-c", script], {
        encoding: "utf8", timeout: 5000, windowsHide: true,
        env: { PATH: process.env.PATH, SystemRoot: process.env.SystemRoot, [envName]: "failure" },
      });
    assert.equal(result.status, 1, `${envName}: ${result.stderr}`);
  }
});

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

test("retomada de itens não consulta cadastro, descoberta ou contratos", () => {
  assert.match(workflow, /^          - items_only$/m);
  for (const name of [registry, weekly, backfill, replay, contracts,
    "Preservar vínculo municipal privado", "Publicar par revisado do Fundo Social"])
    assert.equal(enabled(name, { mode: "items_only" }), false, name);
  for (const name of [items, normalize]) {
    assert.equal(enabled(name, { mode: "items_only" }), true, name);
    assert.equal(enabled(name, { mode: "items_only", priorSucceeded: false }), false);
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
    ["skipped", "failure", "skipped", 1],
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
    /if: github\.event_name != 'workflow_dispatch' \|\| \(inputs\.mode != 'registry_only' && inputs\.mode != 'municipal_link_evidence' && inputs\.mode != 'publication_evidence' && inputs\.mode != 'discovery_only'\)[\s\S]*?normalize_pncp_contracts/,
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
test('publicação do Fundo exige opção manual explícita após preservação', () => {
  const publish = step('Publicar par revisado do Fundo Social');
  assert.match(publish, /github.event_name == 'workflow_dispatch' && inputs.mode == 'municipal_link_evidence' && inputs.publish_social_fund/);
  assert.match(publish, /commands.publish_pncp_social_fund/);
  assert.doesNotMatch(publish, /continue-on-error: true/);
  assert.match(workflow, /publish_social_fund:[\s\S]*?default: false\s+type: boolean/);
  assert.ok(workflow.indexOf('commands.collect_pncp_municipal_link_evidence') < workflow.indexOf('commands.publish_pncp_social_fund'));
});
