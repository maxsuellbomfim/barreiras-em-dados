import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const script = fs.readFileSync(
  new URL("../../scripts/run-tcm-ba-monthly-catalog.ps1", import.meta.url),
  "utf8",
);

test("replay local do TCM-BA pede segredos ocultos e sempre limpa o ambiente", () => {
  assert.match(script, /collector-credential-store\.ps1/);
  assert.match(script, /Read-CollectorCredentialStore/);
  assert.match(script, /Read-Host[^\n]+-AsSecureString/);
  assert.match(script, /SUPABASE_WORKLOAD_PASSWORD/);
  assert.match(script, /COLLECTOR_DATABASE_PASSWORD/);
  assert.match(script, /finally\s*\{/);
  assert.match(script, /Remove-Item "Env:\$name"/);
  assert.doesNotMatch(script, /Write-Host[^\n]*(databasePassword|workloadPassword)/i);
  assert.doesNotMatch(script, /Set-Content|Add-Content|Out-File/);
});

test("replay exige intervalo mensal e pode validar a contagem piloto", () => {
  assert.match(script, /\[string\]\$MonthFrom = "2023-04"/);
  assert.match(script, /\[string\]\$MonthTo = "2023-04"/);
  assert.match(script, /\[int\]\$ExpectedDocuments = 1824/);
  assert.match(script, /\[object\]\$RequestsPerMinute = 30/);
  assert.match(
    script,
    /barreiras_collectors\.commands\.collect_tcm_ba_monthly_catalog/,
  );
  assert.match(script, /collector_tcm_ba_month_completed/);
  assert.match(script, /--requests-per-minute \$RequestsPerMinute/);
  assert.match(script, /TCM_BA_REPLAY_APROVADO/);
});

const helper = path.resolve(
  fileURLToPath(
    new URL("../../scripts/lib/tcm-ba-replay-validation.ps1", import.meta.url),
  ),
);

function runPowerShell(command) {
  return spawnSync(
    process.env.PWSH_PATH ?? "pwsh",
    ["-NoProfile", "-NonInteractive", "-Command", command],
    { encoding: "utf8" },
  );
}

function validationCommand(body) {
  const helperPath = helper.replaceAll("'", "''");
  return `. '${helperPath}'; ${body}`;
}

function assertApproved(events, expectedDocuments) {
  const result = runPowerShell(
    validationCommand(
      `$events = ConvertFrom-Json '${JSON.stringify(events).replaceAll("'", "''")}'; ` +
        `Assert-TcmBaReplayApproval -Events @($events) -ExpectedDocuments ${expectedDocuments}`,
    ),
  );
  assert.equal(result.status, 0, result.stderr);
}

function assertRejected(events, expectedDocuments, expectedMessage) {
  const result = runPowerShell(
    validationCommand(
      `$events = ConvertFrom-Json '${JSON.stringify(events).replaceAll("'", "''")}'; ` +
        `Assert-TcmBaReplayApproval -Events @($events) -ExpectedDocuments ${expectedDocuments}`,
    ),
  );
  const output = `${result.stdout}\n${result.stderr}`;
  assert.notEqual(result.status, 0, output);
  assert.match(output, expectedMessage);
}

test("validação aprova somente um evento completo e não vazio", () => {
  assertApproved(
    [
      {
        event: "collector_tcm_ba_month_completed",
        coverage_status: "complete",
        documents: 3,
      },
    ],
    3,
  );
});

test("validação aprova ExpectedDocuments=0 quando o evento completo não é vazio", () => {
  assertApproved(
    [
      {
        event: "collector_tcm_ba_month_completed",
        coverage_status: "complete",
        documents: 3,
      },
    ],
    0,
  );
});

test("validação rejeita evento vazio mesmo sem contagem esperada", () => {
  assertRejected(
    [
      {
        event: "collector_tcm_ba_month_completed",
        coverage_status: "complete",
        documents: 0,
      },
    ],
    0,
    /documents maior que zero/,
  );
});

test("validação rejeita duplicidade, cobertura incompleta e contagem divergente", () => {
  const complete = {
    event: "collector_tcm_ba_month_completed",
    coverage_status: "complete",
    documents: 3,
  };
  assertRejected([complete, complete], 0, /exatamente um evento/);
  assertRejected([{ ...complete, coverage_status: "partial" }], 0, /coverage_status complete/);
  assertRejected([complete], 4, /contagem esperada/);
});

test("limite local aceita 30, usa 30 por padrão e rejeita fora de 1..30", () => {
  const defaultResult = runPowerShell(
    validationCommand("Assert-TcmBaRequestsPerMinute"),
  );
  assert.equal(defaultResult.status, 0, defaultResult.stderr);
  assert.match(defaultResult.stdout, /30/);

  for (const value of [1, 30]) {
    const result = runPowerShell(
      validationCommand(`Assert-TcmBaRequestsPerMinute -RequestsPerMinute ${value}`),
    );
    assert.equal(result.status, 0, result.stderr);
  }
  for (const value of [0, 31, 120]) {
    const result = runPowerShell(
      validationCommand(`Assert-TcmBaRequestsPerMinute -RequestsPerMinute ${value}`),
    );
    assert.notEqual(result.status, 0, `valor aceito indevidamente: ${value}`);
  }
});

test("validação rejeita documents booleano, fracionário e strings", () => {
  const base = {
    event: "collector_tcm_ba_month_completed",
    coverage_status: "complete",
  };
  for (const documents of [true, 1.5, "3", "3.5", "abc"]) {
    assertRejected(
      [{ ...base, documents }],
      0,
      /documents deve ser um inteiro numérico positivo/,
    );
  }
});

test("script principal rejeita 31 no binding antes de acessar configuração", () => {
  const scriptPath = fileURLToPath(
    new URL("../../scripts/run-tcm-ba-monthly-catalog.ps1", import.meta.url),
  );
  const result = spawnSync(
    process.env.PWSH_PATH ?? "pwsh",
    ["-NoProfile", "-NonInteractive", "-File", scriptPath, "-RequestsPerMinute", "31"],
    { encoding: "utf8" },
  );
  const output = `${result.stdout}\n${result.stderr}`;
  assert.notEqual(result.status, 0, output);
  assert.match(output, /RequestsPerMinute deve ser um inteiro numérico entre 1 e 30/);
  assert.doesNotMatch(output, /Crie \.env\.collector\.local|Senha PostgreSQL|Python não foi localizado/);
});

function assertRateRejected(expression, expectedMessage) {
  const result = runPowerShell(
    validationCommand(
      `Assert-TcmBaRequestsPerMinute -RequestsPerMinute ${expression}`,
    ),
  );
  const output = `${result.stdout}\n${result.stderr}`;
  assert.notEqual(result.status, 0, output);
  assert.match(output, expectedMessage);
}

test("limite local rejeita RPM fracionário, booleano e string malformada", () => {
  for (const expression of ["30.5", "$true", "'30.5'", "'trinta'"]) {
    assertRateRejected(
      expression,
      /RequestsPerMinute deve ser um inteiro numérico entre 1 e 30/,
    );
  }
});

test("script principal rejeita RPM fracionário e booleano antes de acessar configuração", () => {
  const scriptPath = fileURLToPath(
    new URL("../../scripts/run-tcm-ba-monthly-catalog.ps1", import.meta.url),
  );
  const escapedScriptPath = scriptPath.replaceAll("'", "''");
  for (const expression of ["30.5", "$true"]) {
    const result = spawnSync(
      process.env.PWSH_PATH ?? "pwsh",
      [
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        `& '${escapedScriptPath}' -RequestsPerMinute ${expression}`,
      ],
      { encoding: "utf8" },
    );
    const output = `${result.stdout}\n${result.stderr}`;
    assert.notEqual(result.status, 0, output);
    assert.match(output, /RequestsPerMinute deve ser um inteiro numérico entre 1 e 30/);
    assert.doesNotMatch(output, /Crie \.env\.collector\.local|Senha PostgreSQL|Python não foi localizado/);
  }
});
const documentScriptPath = fileURLToPath(
  new URL("../../scripts/run-tcm-ba-document-pilot.ps1", import.meta.url),
);
const documentScript = fs.readFileSync(documentScriptPath, "utf8");
const documentCommand = fs.readFileSync(
  new URL(
    "../../workers/collectors/src/barreiras_collectors/commands/collect_tcm_ba_documents.py",
    import.meta.url,
  ),
  "utf8",
);

function documentEvent(overrides = {}) {
  return {
    event: "collector_tcm_ba_documents_completed",
    competence: "01/2021",
    expected_documents: 1441,
    downloaded_documents: 5,
    preserved_documents: 6,
    remaining_documents: 1435,
    coverage_status: "partial",
    ...overrides,
  };
}

function assertDocumentApproved(events, maxDocuments = 5) {
  const payload = JSON.stringify(events).replaceAll("'", "''");
  const command =
    "$events = ConvertFrom-Json '" +
    payload +
    "'; Assert-TcmBaDocumentBatchApproval -Events @($events) " +
    "-ExpectedCompetence '01/2021' -MaxDocuments " +
    maxDocuments;
  const result = runPowerShell(validationCommand(command));
  assert.equal(result.status, 0, result.stdout + "\n" + result.stderr);
}

function assertDocumentRejected(events, expectedMessage, maxDocuments = 5) {
  const payload = JSON.stringify(events).replaceAll("'", "''");
  const command =
    "$events = ConvertFrom-Json '" +
    payload +
    "'; Assert-TcmBaDocumentBatchApproval -Events @($events) " +
    "-ExpectedCompetence '01/2021' -MaxDocuments " +
    maxDocuments;
  const result = runPowerShell(validationCommand(command));
  const output = result.stdout + "\n" + result.stderr;
  assert.notEqual(result.status, 0, output);
  assert.match(output, expectedMessage);
}

test("wrapper documental limita lote, RPM e não expõe credenciais", () => {
  assert.match(documentScript, /\[ValidateRange\(1, 5\)\]/);
  assert.match(documentScript, /Assert-TcmBaRequestsPerMinute/);
  assert.match(documentScript, /collect_tcm_ba_documents/);
  assert.match(documentScript, /--max-documents \$MaxDocuments/);
  assert.match(documentScript, /--requests-per-minute \$RequestsPerMinute/);
  assert.match(documentScript, /Assert-TcmBaDocumentBatchApproval/);
  assert.match(documentScript, /TCM_BA_DOCUMENT_PILOT_APPROVED/);
  assert.match(documentScript, /collector-credential-store\.ps1/);
  assert.match(documentScript, /finally\s*\{/);
  assert.doesNotMatch(
    documentScript,
    /Write-Host[^\n]*(databasePassword|workloadPassword)/i,
  );
  assert.doesNotMatch(documentScript, /Set-Content|Add-Content|Out-File/);
  assert.match(
    documentCommand,
    /expected_documents=summary\.expected_documents/,
  );
});

test("gate documental aprova lote parcial coerente e avanço positivo", () => {
  assertDocumentApproved([documentEvent()]);
});

test("gate documental aprova lote que fecha integralmente a competência", () => {
  assertDocumentApproved([
    documentEvent({
      expected_documents: 6,
      preserved_documents: 6,
      remaining_documents: 0,
      coverage_status: "complete",
    }),
  ]);
});

test("gate documental rejeita execução vazia, duplicada ou acima do limite", () => {
  assertDocumentRejected(
    [documentEvent({ downloaded_documents: 0 })],
    /entre 1 e MaxDocuments/,
  );
  assertDocumentRejected(
    [documentEvent(), documentEvent()],
    /exatamente um evento/,
  );
  assertDocumentRejected(
    [documentEvent({ downloaded_documents: 5 })],
    /entre 1 e MaxDocuments/,
    4,
  );
});

test("gate documental rejeita competência, total e cobertura divergentes", () => {
  assertDocumentRejected(
    [documentEvent({ competence: "02/2021" })],
    /competência do evento/,
  );
  assertDocumentRejected(
    [documentEvent({ expected_documents: 1442 })],
    /não recompõem o total esperado/,
  );
  assertDocumentRejected(
    [documentEvent({ coverage_status: "complete" })],
    /coverage_status diverge/,
  );
});

test("gate documental rejeita contadores booleanos, fracionários e textuais", () => {
  for (const value of [true, 1.5, "5", -1]) {
    assertDocumentRejected(
      [documentEvent({ expected_documents: value })],
      /expected_documents deve ser/,
    );
  }
});

test("wrapper documental rejeita RPM 31 antes de acessar credenciais", () => {
  const result = spawnSync(
    process.env.PWSH_PATH ?? "pwsh",
    [
      "-NoProfile",
      "-NonInteractive",
      "-File",
      documentScriptPath,
      "-RequestsPerMinute",
      "31",
    ],
    { encoding: "utf8" },
  );
  const output = result.stdout + "\n" + result.stderr;
  assert.notEqual(result.status, 0, output);
  assert.match(
    output,
    /RequestsPerMinute deve ser um inteiro numérico entre 1 e 30/,
  );
  assert.doesNotMatch(output, /Crie \.env\.collector\.local|Senha PostgreSQL/);
});
