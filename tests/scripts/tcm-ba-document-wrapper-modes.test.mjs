import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const wrapperPath = fileURLToPath(
  new URL("../../scripts/run-tcm-ba-document-pilot.ps1", import.meta.url),
);
const validationHelperPath = path.resolve(
  fileURLToPath(
    new URL("../../scripts/lib/tcm-ba-replay-validation.ps1", import.meta.url),
  ),
);

function runPowerShell(command) {
  const executable = process.platform === "win32" ? "powershell.exe" : "pwsh";
  return spawnSync(
    executable,
    [
      "-NoProfile",
      "-NonInteractive",
      "-ExecutionPolicy",
      "Bypass",
      "-Command",
      command,
    ],
    { encoding: "utf8" },
  );
}

function budgetGateCommand(events) {
  const helper = validationHelperPath.replaceAll("'", "''");
  const lines = events
    .map((event) => `'${JSON.stringify(event).replaceAll("'", "''")}'`)
    .join(",");
  return (
    `. '${helper}'; ` +
    `Read-TcmBaCommitmentBudgetBenchmarkEvent -Output @(${lines}) | Out-Null`
  );
}

function amountGateCommand(events) {
  const helper = validationHelperPath.replaceAll("'", "''");
  const lines = events
    .map((event) => `'${JSON.stringify(event).replaceAll("'", "''")}'`)
    .join(",");
  return (
    `. '${helper}'; ` +
    `Read-TcmBaCommitmentAmountBenchmarkEvent -Output @(${lines}) | Out-Null`
  );
}

test("benchmark de dotação é mutuamente exclusivo antes de ler credenciais", () => {
  const executable = process.platform === "win32" ? "powershell.exe" : "pwsh";
  const result = spawnSync(
    executable,
    [
      "-NoProfile",
      "-ExecutionPolicy",
      "Bypass",
      "-File",
      wrapperPath,
      "-CommitmentBudgetBenchmarkOnly",
      "-CommitmentIssueDateBenchmarkOnly",
    ],
    { encoding: "utf8" },
  );
  const output = `${result.stdout ?? ""}\n${result.stderr ?? ""}`;

  assert.notEqual(result.status, 0);
  assert.match(output, /outro modo/);
  assert.doesNotMatch(output, /\.env\.collector\.local/);
});

test("gate de dotação aceita somente um evento PASS", () => {
  const approved = runPowerShell(
    budgetGateCommand([
      { event: "tcm_ba_commitment_budget_layout_benchmark", gate: "PASS" },
    ]),
  );
  assert.equal(approved.status, 0, approved.stdout + approved.stderr);

  for (const events of [
    [{ event: "tcm_ba_commitment_budget_layout_benchmark", gate: "BLOCK" }],
    [
      { event: "tcm_ba_commitment_budget_layout_benchmark", gate: "PASS" },
      { event: "tcm_ba_commitment_budget_layout_benchmark", gate: "PASS" },
    ],
  ]) {
    const rejected = runPowerShell(budgetGateCommand(events));
    assert.notEqual(rejected.status, 0, rejected.stdout + rejected.stderr);
  }
});

test("benchmark de valor é mutuamente exclusivo antes de ler credenciais", () => {
  const executable = process.platform === "win32" ? "powershell.exe" : "pwsh";
  const result = spawnSync(
    executable,
    [
      "-NoProfile",
      "-ExecutionPolicy",
      "Bypass",
      "-File",
      wrapperPath,
      "-CommitmentAmountBenchmarkOnly",
      "-CommitmentIssueDateBenchmarkOnly",
    ],
    { encoding: "utf8" },
  );
  const output = `${result.stdout ?? ""}\n${result.stderr ?? ""}`;

  assert.notEqual(result.status, 0);
  assert.match(output, /outro modo/);
  assert.doesNotMatch(output, /\.env\.collector\.local/);
});

test("gate de valor aceita somente um evento PASS", () => {
  const approved = runPowerShell(
    amountGateCommand([
      { event: "tcm_ba_commitment_amount_layout_benchmark", gate: "PASS" },
    ]),
  );
  assert.equal(approved.status, 0, approved.stdout + approved.stderr);

  for (const events of [
    [{ event: "tcm_ba_commitment_amount_layout_benchmark", gate: "BLOCK" }],
    [
      { event: "tcm_ba_commitment_amount_layout_benchmark", gate: "PASS" },
      { event: "tcm_ba_commitment_amount_layout_benchmark", gate: "PASS" },
    ],
  ]) {
    const rejected = runPowerShell(amountGateCommand(events));
    assert.notEqual(rejected.status, 0, rejected.stdout + rejected.stderr);
  }
});
