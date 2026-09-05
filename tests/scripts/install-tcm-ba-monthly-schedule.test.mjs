import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const script = await readFile(
  new URL("../../scripts/install-tcm-ba-monthly-schedule.ps1", import.meta.url),
  "utf8",
);

test("tarefa mensal local usa DPAPI e verifica diariamente o mês fechado", () => {
  assert.match(script, /Barreiras360-TCMBA-MonthlyCatalog/);
  assert.match(script, /\.collector-credentials\.local\.json/);
  assert.match(script, /run-tcm-ba-monthly-catalog\.ps1/);
  assert.match(script, /-AutomaticClosedMonth/);
  assert.match(script, /"-WindowStyle Hidden"/);
  assert.match(script, /-RequestsPerMinute 30/);
  assert.match(script, /New-ScheduledTaskTrigger[\s\S]*-Daily/);
  assert.match(script, /-MultipleInstances IgnoreNew/);
  assert.match(script, /-StartWhenAvailable/);
  assert.match(script, /-WakeToRun/);
  assert.match(script, /-LogonType Interactive/);
  assert.match(script, /-RunLevel Limited/);
  assert.match(script, /Register-ScheduledTask -TaskName \$taskName -InputObject \$task -Force/);
  assert.doesNotMatch(script, /Unregister-ScheduledTask|schtasks.*\/Delete/i);
});
