import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { setTimeout as delay } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';

const helperPath = fileURLToPath(new URL('../../scripts/lib/collector-source-lock.ps1', import.meta.url));
const powershell = 'C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe';
const windowsOnly = { skip: process.platform !== 'win32' };
const processesByTest = new WeakMap();

function quotePowerShell(value) {
  return `'${value.replaceAll("'", "''")}'`;
}

function temporaryLock(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'barreiras-source-lock-'));
  const processes = [];
  processesByTest.set(t, processes);
  t.after(async () => {
    for (const process of processes) {
      if (!process.result.exited) process.child.kill();
    }
    await Promise.all(processes.map(process => process.done));
    fs.rmSync(directory, { recursive: true, force: true });
  });
  return path.join(directory, 'source.lock');
}

function runPowerShell(t, script) {
  const command = `$ErrorActionPreference = 'Stop'; . ${quotePowerShell(helperPath)}; ${script}`;
  const child = spawn(powershell, [
    '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
    '-EncodedCommand', Buffer.from(command, 'utf16le').toString('base64'),
  ], { windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
  const result = { stdout: '', stderr: '', exited: false };
  child.stdout.setEncoding('utf8');
  child.stderr.setEncoding('utf8');
  child.stdout.on('data', chunk => { result.stdout += chunk; });
  child.stderr.on('data', chunk => { result.stderr += chunk; });
  child.on('error', error => { result.error = error; });
  const done = new Promise(resolve => child.on('close', code => {
    clearTimeout(timer);
    result.exited = true;
    result.code = code;
    resolve(result);
  }));
  const timer = setTimeout(() => child.kill(), 15_000);
  const process = { child, result, done };
  processesByTest.get(t).push(process);
  return process;
}

async function readResult(process) {
  const result = await process.done;
  assert.ifError(result.error);
  assert.equal(result.code, 0, result.stderr || result.stdout);
  return JSON.parse(result.stdout.trim().split(/\r?\n/).at(-1));
}

async function waitForLine(process, line) {
  const deadline = Date.now() + 10_000;
  while (!process.result.stdout.split(/\r?\n/).includes(line)) {
    assert.equal(process.result.exited, false, process.result.stderr);
    assert.ok(Date.now() < deadline, `PowerShell did not emit ${line}`);
    await delay(20);
  }
}

test('helper de trava possui espera limitada sem remover o arquivo compartilhado', () => {
  const script = fs.readFileSync(helperPath, 'utf8');
  assert.match(script, /function Wait-CollectorSourceLock/);
  assert.match(script, /\[ValidateRange\(0,\s*900\)\]/);
  assert.match(script, /\$TimeoutSeconds\s*=\s*900/);
  assert.match(script, /\[ValidateRange\(50,\s*5000\)\]/);
  assert.match(script, /\$PollMilliseconds\s*=\s*500/);
  assert.doesNotMatch(script, /Remove-Item|\[IO\.File\]::Delete|FileMode\]::Create\b/);
});

test('timeout zero tenta adquirir, mantém exclusividade e permite readquirir após Dispose', windowsOnly, async t => {
  const lockPath = temporaryLock(t);
  fs.writeFileSync(lockPath, 'preserved lock marker');
  const result = await readResult(runPowerShell(t, `
    $first = Wait-CollectorSourceLock -Path ${quotePowerShell(lockPath)} -TimeoutSeconds 0;
    try {
      $second = Wait-CollectorSourceLock -Path ${quotePowerShell(lockPath)} -TimeoutSeconds 0;
      $type = $first.GetType().FullName;
      $exclusive = $null -eq $second;
      if ($null -ne $second) { $second.Dispose() };
    } finally { if ($null -ne $first) { $first.Dispose() } };
    $third = Wait-CollectorSourceLock -Path ${quotePowerShell(lockPath)} -TimeoutSeconds 0;
    try {
      [pscustomobject]@{ Type = $type; Exclusive = $exclusive; Reacquired = $null -ne $third } | ConvertTo-Json -Compress;
    } finally { if ($null -ne $third) { $third.Dispose() } };
  `));
  assert.deepEqual(result, { Type: 'System.IO.FileStream', Exclusive: true, Reacquired: true });
  assert.equal(fs.readFileSync(lockPath, 'utf8'), 'preserved lock marker');
});

test('contenção esgota o prazo sem liberar a trava alheia nem dormir além do restante', windowsOnly, async t => {
  const lockPath = temporaryLock(t);
  const result = await readResult(runPowerShell(t, `
    $holder = Wait-CollectorSourceLock -Path ${quotePowerShell(lockPath)} -TimeoutSeconds 0;
    try {
      $watch = [Diagnostics.Stopwatch]::StartNew();
      $waiter = Wait-CollectorSourceLock -Path ${quotePowerShell(lockPath)} -TimeoutSeconds 1 -PollMilliseconds 5000;
      $elapsed = $watch.ElapsedMilliseconds;
      $stillHeld = Wait-CollectorSourceLock -Path ${quotePowerShell(lockPath)} -TimeoutSeconds 0;
      [pscustomobject]@{ TimedOut = $null -eq $waiter; StillHeld = $null -eq $stillHeld; OwnerUsable = $holder.CanWrite; Elapsed = $elapsed } | ConvertTo-Json -Compress;
      if ($null -ne $waiter) { $waiter.Dispose() };
      if ($null -ne $stillHeld) { $stillHeld.Dispose() };
    } finally { if ($null -ne $holder) { $holder.Dispose() } };
  `));
  assert.equal(result.TimedOut, true);
  assert.equal(result.StillHeld, true);
  assert.equal(result.OwnerUsable, true);
  assert.ok(result.Elapsed >= 900, `returned too early: ${result.Elapsed} ms`);
  assert.ok(result.Elapsed < 2500, `exceeded bounded timeout: ${result.Elapsed} ms`);
  assert.equal(fs.existsSync(lockPath), true);
});

test('aguarda a liberação por outro processo e adquire a mesma trava', windowsOnly, async t => {
  const lockPath = temporaryLock(t);
  const holder = runPowerShell(t, `
    $lock = Wait-CollectorSourceLock -Path ${quotePowerShell(lockPath)} -TimeoutSeconds 0;
    try {
      if ($null -eq $lock) { throw 'Holder did not acquire lock' };
      [Console]::Out.WriteLine('LOCKED');
      [Console]::Out.Flush();
      [void][Console]::ReadLine();
    } finally { if ($null -ne $lock) { $lock.Dispose() } };
    [pscustomobject]@{ Released = $true } | ConvertTo-Json -Compress;
  `);
  await waitForLine(holder, 'LOCKED');
  const waiter = runPowerShell(t, `
    [Console]::Out.WriteLine('WAITING');
    [Console]::Out.Flush();
    $watch = [Diagnostics.Stopwatch]::StartNew();
    $lock = Wait-CollectorSourceLock -Path ${quotePowerShell(lockPath)} -TimeoutSeconds 5 -PollMilliseconds 50;
    try {
      [pscustomobject]@{ Acquired = $null -ne $lock; Elapsed = $watch.ElapsedMilliseconds } | ConvertTo-Json -Compress;
    } finally { if ($null -ne $lock) { $lock.Dispose() } };
  `);
  await waitForLine(waiter, 'WAITING');
  await delay(300);
  assert.equal(waiter.result.exited, false, 'waiter must not finish while the other process owns the lock');
  holder.child.stdin.end('release\n');
  assert.deepEqual(await readResult(holder), { Released: true });
  const result = await readResult(waiter);
  assert.equal(result.Acquired, true);
  assert.ok(result.Elapsed >= 250, `did not wait for release: ${result.Elapsed} ms`);
  assert.ok(result.Elapsed < 5000, `did not acquire before deadline: ${result.Elapsed} ms`);
});

for (const invalidKind of ['missing parent', 'directory']) {
  test(`erro não transitório (${invalidKind}) propaga imediatamente`, windowsOnly, async t => {
    const lockPath = temporaryLock(t);
    const invalidPath = invalidKind === 'directory' ? path.dirname(lockPath) : path.join(lockPath, 'missing', 'source.lock');
    const result = await readResult(runPowerShell(t, `
      $watch = [Diagnostics.Stopwatch]::StartNew();
      $caught = $false;
      try { $lock = Wait-CollectorSourceLock -Path ${quotePowerShell(invalidPath)} -TimeoutSeconds 5 } catch { $caught = $true };
      if ($null -ne $lock) { $lock.Dispose() };
      [pscustomobject]@{ Threw = $caught; Elapsed = $watch.ElapsedMilliseconds } | ConvertTo-Json -Compress;
    `));
    assert.equal(result.Threw, true);
    assert.ok(result.Elapsed < 1500, `non-contention error retried: ${result.Elapsed} ms`);
  });
}

test('parâmetros fora dos limites são recusados antes de abrir a trava', windowsOnly, async t => {
  const lockPath = temporaryLock(t);
  const result = await readResult(runPowerShell(t, `
    $rejected = 0;
    foreach ($parameters in @(@{ TimeoutSeconds = -1 }, @{ TimeoutSeconds = 901 }, @{ PollMilliseconds = 49 }, @{ PollMilliseconds = 5001 })) {
      try {
        $lock = Wait-CollectorSourceLock -Path ${quotePowerShell(lockPath)} @parameters;
        if ($null -ne $lock) { $lock.Dispose() };
      } catch { $rejected++ };
    };
    [pscustomobject]@{ Rejected = $rejected } | ConvertTo-Json -Compress;
  `));
  assert.equal(result.Rejected, 4);
  assert.equal(fs.existsSync(lockPath), false);
});
