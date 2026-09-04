import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { readFileSync } from "node:fs";

const wrapperPath = fileURLToPath(
  new URL("../../scripts/run-tcm-ba-document-pilot.ps1", import.meta.url),
);
const validationHelperPath = path.resolve(
  fileURLToPath(
    new URL("../../scripts/lib/tcm-ba-replay-validation.ps1", import.meta.url),
  ),
);
const wrapper = readFileSync(wrapperPath, "utf8");

test("wrapper declara origem controlada e a encaminha ao coletor", () => {
  assert.match(
    wrapper,
    /\[ValidateSet\("manual", "github_actions", "windows_scheduler"\)\]/,
  );
  assert.match(wrapper, /\[string\]\$ExecutionOrigin = "manual"/);
  assert.match(
    wrapper,
    /"--execution-origin"\s+\$ExecutionOrigin/,
  );
});

test("consulta de linhagem exige hash e chama somente o relatório exato", () => {
  assert.match(wrapper, /\[switch\]\$DocumentLineageOnly/);
  assert.match(wrapper, /\[string\]\$ArtifactSha256/);
  assert.match(
    wrapper,
    /report_tcm_ba_document_lineage --sha256 \$ArtifactSha256/,
  );
  assert.match(wrapper, /TCM_BA_DOCUMENT_LINEAGE_ONLY/);
});

test("processamento local de texto pode atingir somente um SHA preservado", () => {
  assert.match(wrapper, /\[switch\]\$DocumentTextOnly/);
  assert.match(
    wrapper,
    /process_tcm_ba_documents --limit 1 --artifact-sha256 \$ArtifactSha256/,
  );
  assert.match(wrapper, /TCM_BA_DOCUMENT_TEXT_ONLY_APPROVED/);
});

test("coleta local dirigida encaminha código oficial somente com competência", () => {
  assert.match(wrapper, /\[string\]\$CategoryCode = ""/);
  assert.match(wrapper, /CategoryCode exige -Competence explícita/);
  assert.match(wrapper, /\^PCMGE\\d\{3\}\$/);
  assert.match(
    wrapper,
    /\$collectorArguments = @\([\s\S]*"--competence"[\s\S]*"--requests-per-minute"/,
  );
  assert.match(
    wrapper,
    /if \(-not \[string\]::IsNullOrWhiteSpace\(\$CategoryCode\)\) \{[\s\S]*\$collectorArguments \+= @\("--category-code", \$CategoryCode\)/,
  );
  assert.match(wrapper, /& \$python @collectorArguments/);
  assert.doesNotMatch(
    wrapper,
    /collect_tcm_ba_documents[^\n]*--category-code \$CategoryCode/,
  );
  assert.match(wrapper, /\$targetArtifactSha256 = \$collectorEvent\.pdf_hashes\[0\]/);
  assert.match(
    wrapper,
    /process_tcm_ba_documents --limit 1 --artifact-sha256 \$targetArtifactSha256/,
  );
  assert.match(
    wrapper,
    /process_tcm_ba_document_families --limit 1 --artifact-sha256 \$targetArtifactSha256/,
  );
  assert.match(wrapper, /TCM_BA_DOCUMENT_CATEGORY_RECOVERY_APPROVED/);
});

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

function expensePublicationGateCommand(events, sha256 = "6".repeat(64)) {
  const helper = validationHelperPath.replaceAll("'", "''");
  const payload = JSON.stringify(events).replaceAll("'", "''");
  return (
    `. '${helper}'; ` +
    `$events = ConvertFrom-Json '${payload}'; ` +
    `Assert-TcmBaExpensePublicationApproval ` +
    `-Events @($events) -ArtifactSha256 '${sha256}' | Out-Null`
  );
}

function expensePublicationEvent(overrides = {}) {
  return {
    event: "expense_publication_completed",
    artifact_sha256: "6".repeat(64),
    artifacts: 1,
    reports_published: 1,
    published_lines: 0,
    already_published: 0,
    needs_review: 0,
    ...overrides,
  };
}

function revenuePublicationGateCommand(events, sha256 = "8".repeat(64)) {
  const helper = validationHelperPath.replaceAll("'", "''");
  const payload = JSON.stringify(events).replaceAll("'", "''");
  return (
    `. '${helper}'; ` +
    `$events = ConvertFrom-Json '${payload}'; ` +
    `Assert-TcmBaRevenuePublicationApproval ` +
    `-Events @($events) -ArtifactSha256 '${sha256}' | Out-Null`
  );
}

function revenuePublicationEvent(overrides = {}) {
  return {
    event: "revenue_publication_completed",
    artifact_sha256: "8".repeat(64),
    artifacts: 1,
    published_rows: 248,
    already_published: 0,
    needs_review: 0,
    ...overrides,
  };
}

test("publica um resumo TCM-BA somente pelo SHA exato", () => {
  assert.match(wrapper, /\[switch\]\$ExpenseSummaryOnly/);
  assert.match(
    wrapper,
    /publish_expense_reports --limit 1 --artifact-sha256 \$ArtifactSha256/,
  );
  assert.match(wrapper, /Assert-TcmBaExpensePublicationApproval/);
  assert.match(wrapper, /TCM_BA_EXPENSE_SUMMARY_APPROVED/);
  assert.match(
    wrapper,
    /workers\/collectors\/src;workers\/document-processing\/src;workers\/normalization\/src/,
  );
});

test("modo de resumo rejeita SHA ausente antes de ler credenciais", () => {
  const executable = process.platform === "win32" ? "powershell.exe" : "pwsh";
  const result = spawnSync(
    executable,
    [
      "-NoProfile",
      "-NonInteractive",
      "-ExecutionPolicy",
      "Bypass",
      "-File",
      wrapperPath,
      "-ExpenseSummaryOnly",
    ],
    { encoding: "utf8" },
  );
  const output = `${result.stdout ?? ""}\n${result.stderr ?? ""}`;

  assert.notEqual(result.status, 0);
  assert.match(output, /exige -ArtifactSha256/);
  assert.doesNotMatch(output, /\.env\.collector\.local/);
});

test("gate aceita resumo sem linhas e replay idempotente", () => {
  for (const event of [
    expensePublicationEvent(),
    expensePublicationEvent({
      reports_published: 0,
      already_published: 1,
    }),
  ]) {
    const result = runPowerShell(expensePublicationGateCommand([event]));
    assert.equal(result.status, 0, result.stdout + result.stderr);
  }
});

test("gate rejeita lote vazio, SHA divergente, falha ou evento duplicado", () => {
  for (const events of [
    [expensePublicationEvent({ artifacts: 0, reports_published: 0 })],
    [expensePublicationEvent({ artifact_sha256: "7".repeat(64) })],
    [expensePublicationEvent({ reports_published: 0, needs_review: 1 })],
    [expensePublicationEvent(), expensePublicationEvent()],
  ]) {
    const result = runPowerShell(expensePublicationGateCommand(events));
    assert.notEqual(result.status, 0, result.stdout + result.stderr);
  }
});

test("publica o relatório de receita TCM-BA somente pelo SHA exato", () => {
  assert.match(wrapper, /\[switch\]\$RevenueReportOnly/);
  assert.match(
    wrapper,
    /publish_revenue_reports --limit 1 --artifact-sha256 \$ArtifactSha256/,
  );
  assert.match(wrapper, /Assert-TcmBaRevenuePublicationApproval/);
  assert.match(wrapper, /TCM_BA_REVENUE_REPORT_APPROVED/);
});

test("gate de receita aceita publicação e replay, nunca lote vazio", () => {
  for (const event of [
    revenuePublicationEvent(),
    revenuePublicationEvent({ published_rows: 0, already_published: 1 }),
  ]) {
    const result = runPowerShell(revenuePublicationGateCommand([event]));
    assert.equal(result.status, 0, result.stdout + result.stderr);
  }

  for (const events of [
    [revenuePublicationEvent({ artifacts: 0, published_rows: 0 })],
    [revenuePublicationEvent({ artifact_sha256: "9".repeat(64) })],
    [revenuePublicationEvent({ published_rows: 0, needs_review: 1 })],
    [revenuePublicationEvent({ published_rows: 0, already_published: 0 })],
    [revenuePublicationEvent(), revenuePublicationEvent()],
  ]) {
    const result = runPowerShell(revenuePublicationGateCommand(events));
    assert.notEqual(result.status, 0, result.stdout + result.stderr);
  }
});

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
