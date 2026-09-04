import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const script = await readFile(
  new URL("../../scripts/install-tcm-ba-document-schedule.ps1", import.meta.url),
  "utf8",
);

test("tarefa local usa DPAPI, seleção automática e limites fechados", () => {
  assert.match(script, /Barreiras360-TCMBA-Documents/);
  assert.match(script, /\.collector-credentials\.local\.json/);
  assert.match(script, /-AutoCompetence/);
  assert.match(script, /-MaxDocuments 10/);
  assert.match(script, /\[ValidateRange\(15, 1440\)\]/);
  assert.match(script, /\[int\]\$IntervalMinutes = 15/);
  assert.match(
    script,
    /-RepetitionInterval \(New-TimeSpan -Minutes \$IntervalMinutes\)/,
  );
  assert.match(script, /-RequestsPerMinute 30/);
  assert.match(script, /-MultipleInstances IgnoreNew/);
  assert.match(script, /-StartWhenAvailable/);
  assert.match(script, /-WakeToRun/);
  assert.match(script, /-LogonType Interactive/);
  assert.match(script, /-RunLevel Limited/);
  assert.match(script, /-ExecutionTimeLimit \(New-TimeSpan -Minutes 30\)/);
  assert.doesNotMatch(script, /password|senha/i);
});

test("instalador só substitui a tarefa Barreiras 360 de nome exato", () => {
  assert.match(script, /Register-ScheduledTask -TaskName \$taskName -InputObject \$task -Force/);
  assert.doesNotMatch(script, /Unregister-ScheduledTask|schtasks.*\/Delete/i);
  assert.doesNotMatch(script, /RunLevel Highest/);
});
