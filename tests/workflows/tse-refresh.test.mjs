import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

test('TSE local refresh uses current election, bounded native download and preserved-year gate', () => {
  const text = readFileSync('scripts/run-tse-votes.ps1', 'utf8');
  assert.match(text, /\$Anos = @\(2026\)/);
  assert.match(text, /--transport curl/);
  assert.match(text, /\$summary\.preserved -ne \$Anos\.Count/);
});

test('TSE daily schedule is hidden, noninteractive and cannot overlap itself', () => {
  const text = readFileSync('scripts/install-tse-refresh-schedule.ps1', 'utf8');
  assert.match(text, /New-HiddenPowerShellTaskAction/);
  assert.match(text, /-NonInteractive -WindowStyle Hidden/);
  assert.match(text, /-MultipleInstances IgnoreNew/);
  assert.match(text, /-Daily/);
  assert.match(text, /-Anos 2026/);
});
