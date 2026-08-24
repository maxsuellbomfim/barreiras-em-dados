import assert from "node:assert/strict";
import fs from "node:fs";
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
  assert.match(script, /\[ValidateRange\(1, 120\)\]/);
  assert.match(script, /\[int\]\$RequestsPerMinute = 120/);
  assert.match(
    script,
    /barreiras_collectors\.commands\.collect_tcm_ba_monthly_catalog/,
  );
  assert.match(script, /collector_tcm_ba_month_completed/);
  assert.match(script, /--requests-per-minute \$RequestsPerMinute/);
  assert.match(script, /TCM_BA_REPLAY_APROVADO/);
});
