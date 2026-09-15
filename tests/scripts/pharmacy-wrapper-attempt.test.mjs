import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import test from 'node:test';

const windows = process.platform === 'win32';
const shell = join(process.env.SystemRoot || 'C:/Windows', 'System32/WindowsPowerShell/v1.0/powershell.exe');
const quote = value => `'${value.replaceAll("'", "''")}'`;

function fixture(t, { credentialFailure = false, lockTimeout = false, malformed = false, cleanupFailure = false, collectorStatus = 'complete', collectorExit = 0 } = {}) {
  const root = mkdtempSync(join(tmpdir(), 'pharmacy-attempt-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  mkdirSync(join(root, 'scripts/lib'), { recursive: true });
  mkdirSync(join(root, 'config/certificates'), { recursive: true });
  mkdirSync(join(root, 'data/pharmacy-refresh/2026'), { recursive: true });
  copyFileSync(resolve('scripts/run-pharmacy-refresh.ps1'), join(root, 'scripts/run.ps1'));
  // Stub only external dependencies: no production credentials, locks or network.
  writeFileSync(join(root, 'scripts/lib/collector-credential-store.ps1'), `
function Read-CollectorCredentialStore {
  param($Path,$ExpectedProjectRef)
  [IO.File]::WriteAllText(${quote(join(root, 'credentials-called'))},'called')
  ${credentialFailure ? "throw 'PRIVATE_CREDENTIAL_ERROR'" : "return @{DatabasePassword='fixture';WorkloadPassword='fixture'}"}
}
${cleanupFailure ? `
function New-TemporaryFile { New-Item -ItemType File -Path ${quote(join(root, 'fixture-ca.tmp'))} }
function Remove-Item {
  [CmdletBinding()]param($LiteralPath,[switch]$Force)
  if($LiteralPath -eq ${quote(join(root, 'fixture-ca.tmp'))}){throw 'PRIVATE_CLEANUP_ERROR'}
  Microsoft.PowerShell.Management\\Remove-Item @PSBoundParameters
}` : ''}`);
  writeFileSync(join(root, 'scripts/lib/collector-source-lock.ps1'), `
function Wait-CollectorSourceLock {
  param($Path,$TimeoutSeconds)
  ${lockTimeout ? 'return $null' : "return [IO.File]::Open($Path,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)"}
}`);
  writeFileSync(join(root, '.env.collector.local'), 'COLLECTOR_POOLER_HOST=invalid.example\nSUPABASE_PUBLISHABLE_KEY=fixture\nSUPABASE_WORKLOAD_EMAIL=fixture\n');
  writeFileSync(join(root, 'config/certificates/supabase-prod-ca-2021.crt'), 'fixture');
  const python = join(root, 'fake-python.cmd');
  writeFileSync(python, `@echo off\r\necho ${malformed ? 'invalid' : JSON.stringify({ event: 'pharmacy_refresh', status: collectorStatus, verified_documents: 17 })}\r\nexit /b ${collectorExit}\r\n`);
  const latest = join(root, 'data/pharmacy-refresh/2026/latest.json');
  writeFileSync(latest, '{"status":"complete","verified_documents":10}');
  // A Node child of PowerShell 7 otherwise passes its module path to PS 5.1.
  // Let Windows PowerShell rebuild its own standard-module search path.
  const env = Object.fromEntries(Object.entries(process.env).filter(([name]) => name.toLowerCase() !== 'psmodulepath'));
  const result = spawnSync(shell, ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', join(root, 'scripts/run.ps1'), '-Year', '2026', '-CredentialRoot', root, '-PythonPath', python], { encoding: 'utf8', windowsHide: true, timeout: 20000, env });
  return { root, result, latest, attempt: () => JSON.parse(readFileSync(join(root, 'data/pharmacy-refresh/2026/attempt.json'), 'utf8')) };
}

test('wrapper records pre-collector failure without replacing last completed report', { skip: !windows }, t => {
  const f = fixture(t, { credentialFailure: true });
  assert.equal(f.result.status, 1);
  assert.doesNotMatch(f.result.stdout + f.result.stderr, /PRIVATE_CREDENTIAL_ERROR/);
  assert.equal(f.attempt().status, 'failed');
  assert.equal(f.attempt().stage, 'credentials');
  assert.ok(f.attempt().started_at && f.attempt().finished_at);
  assert.equal(JSON.parse(readFileSync(f.latest, 'utf8')).verified_documents, 10);
});

test('source contention defers before credentials or checkpoint creation, never succeeds', { skip: !windows }, t => {
  const f = fixture(t, { lockTimeout: true });
  assert.equal(f.result.status, 75);
  assert.equal(f.attempt().status, 'deferred');
  assert.equal(f.attempt().reason, 'source_busy');
  assert.equal(f.attempt().stage, 'source_lock');
  assert.equal(existsSync(join(f.root, 'credentials-called')), false);
  assert.equal(existsSync(join(f.root, 'data/pharmacy-refresh/2026/active.txt')), false);
  assert.equal(JSON.parse(readFileSync(f.latest, 'utf8')).verified_documents, 10);
});

test('successful collector closes attempt and releases its completed checkpoint', { skip: !windows }, t => {
  const f = fixture(t);
  assert.equal(f.result.status, 0, f.result.stdout + f.result.stderr);
  assert.equal(f.attempt().status, 'complete');
  assert.ok(f.attempt().finished_at);
  assert.equal(JSON.parse(readFileSync(f.latest, 'utf8')).verified_documents, 17);
  assert.equal(existsSync(join(f.root, 'data/pharmacy-refresh/2026/active.txt')), false);
});

test('missing collector report stays failed with resumable checkpoint', { skip: !windows }, t => {
  const f = fixture(t, { malformed: true });
  assert.equal(f.result.status, 1);
  assert.equal(f.attempt().status, 'failed');
  assert.equal(f.attempt().stage, 'report');
  assert.equal(existsSync(join(f.root, 'data/pharmacy-refresh/2026/active.txt')), true);
});

for (const [collectorStatus, collectorExit] of [['complete', 1], ['partial', 0]]) {
  test(`inconsistent ${collectorStatus}/${collectorExit} never replaces verified report`, { skip: !windows }, t => {
    const f = fixture(t, { collectorStatus, collectorExit });
    assert.equal(f.result.status, 1);
    assert.equal(f.attempt().status, 'failed');
    assert.equal(f.attempt().stage, 'report');
    assert.equal(JSON.parse(readFileSync(f.latest, 'utf8')).verified_documents, 10);
    assert.equal(existsSync(join(f.root, 'data/pharmacy-refresh/2026/active.txt')), true);
  });
}

test('cleanup failure is recorded and sanitized after collector completion', { skip: !windows }, t => {
  const f = fixture(t, { cleanupFailure: true });
  assert.equal(f.result.status, 1);
  assert.equal(f.attempt().status, 'failed');
  assert.equal(f.attempt().stage, 'cleanup');
  assert.equal(f.attempt().reason, 'cleanup_failed');
  assert.doesNotMatch(f.result.stdout + f.result.stderr, /PRIVATE_CLEANUP_ERROR/);
  assert.equal(JSON.parse(readFileSync(f.latest, 'utf8')).verified_documents, 17);
});
