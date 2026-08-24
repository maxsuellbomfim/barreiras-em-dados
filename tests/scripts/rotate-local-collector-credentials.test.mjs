import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);
const scriptPath = path.join(
  repositoryRoot,
  "scripts",
  "rotate-local-collector-credentials.ps1",
);
const powershell =
  "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe";

test("plano de rotação limita a mudança ao banco compartilhado e ao workload municipal", () => {
  const output = execFileSync(
    powershell,
    [
      "-NoProfile",
      "-NonInteractive",
      "-ExecutionPolicy",
      "Bypass",
      "-File",
      scriptPath,
      "-DescribePlan",
    ],
    { encoding: "utf8" },
  ).trim();
  const plan = JSON.parse(output);

  assert.equal(plan.project_ref, "mpladsyzilmgiefejpkq");
  assert.equal(plan.database_role, "collector_querido_diario");
  assert.equal(
    plan.storage_user_id,
    "c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a",
  );
  assert.deepEqual(plan.github_secrets.sort(), [
    "MUNICIPAL_TRANSPARENCY_SUPABASE_WORKLOAD_PASSWORD",
    "QUERIDO_DIARIO_DATABASE_URL",
  ]);
  assert.equal(plan.local_protection, "Windows DPAPI CurrentUser");
  assert.equal(plan.plaintext_persisted, false);
  assert.doesNotMatch(output, /QUERIDO_DIARIO_SUPABASE_WORKLOAD_PASSWORD/);
});

test("comandos nativos de banco preservam stderr de progresso sem falso erro", () => {
  const script = fs.readFileSync(scriptPath, "utf8");

  assert.match(script, /db query --linked/);
  assert.match(script, /\$ErrorActionPreference = "Continue"/);
  assert.match(script, /\$nativeExitCode = \$LASTEXITCODE/);
  assert.match(script, /if \(\$nativeExitCode -ne 0\)/);
});
