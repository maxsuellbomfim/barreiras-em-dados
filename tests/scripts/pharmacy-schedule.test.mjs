import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('atualização local é silenciosa, limitada e não sobreposta', async () => {
  const script = await readFile(new URL('../../scripts/install-pharmacy-refresh-schedule.ps1', import.meta.url), 'utf8');
  for (const text of ['-WindowStyle Hidden', '-NonInteractive', '-MultipleInstances IgnoreNew', '-StartWhenAvailable', '-LogonType Interactive', '-RunLevel Limited', '-Daily', 'Barreiras360-PharmacyRefresh']) assert.ok(script.includes(text), text);
  assert.ok(!script.includes('$PSHOME'), 'o host embarcado não contém powershell.exe');
  assert.ok(script.includes('System32/WindowsPowerShell/v1.0/powershell.exe'));
});

test('wrapper usa cofre existente e retoma aquisição incompleta antes de criar outra', async () => {
  const script = await readFile(new URL('../../scripts/run-pharmacy-refresh.ps1', import.meta.url), 'utf8');
  for (const text of ['Read-CollectorCredentialStore', 'finally', 'refresh_fns_pharmacy', '--max-requests 20', 'active.txt', '$resultCode -eq 0', 'FileShare]::None', 'SUPABASE_WORKLOAD_PASSWORD']) assert.ok(script.includes(text), text);
  assert.ok(!script.includes('Read-Host'));
  assert.ok(!script.includes('Start-Process'));
});

test('histórico usa tarefa e ano fixos sem substituir o ano corrente', async () => {
  const script = await readFile(new URL('../../scripts/install-pharmacy-refresh-schedule.ps1', import.meta.url), 'utf8');
  for (const text of ['HistoricalYear', '-Weekly', '-WeeksInterval 1', '-DaysOfWeek', '-Year $HistoricalYear', '$taskName += "-History-$HistoricalYear"']) assert.ok(script.includes(text), text);
});

test('anos compartilham trava da fonte e reintentam colisões no agendador', async () => {
  const wrapper = await readFile(new URL('../../scripts/run-pharmacy-refresh.ps1', import.meta.url), 'utf8');
  const installer = await readFile(new URL('../../scripts/install-pharmacy-refresh-schedule.ps1', import.meta.url), 'utf8');
  assert.ok(wrapper.includes("'data/pharmacy-refresh/source.lock'"));
  assert.ok(installer.includes('-RestartCount 3'));
  assert.ok(installer.includes('-RestartInterval (New-TimeSpan -Minutes 15)'));
});
