import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);
const helperPath = path.join(
  repositoryRoot,
  "scripts",
  "lib",
  "collector-credential-store.ps1",
);
const powershell =
  "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe";

let dpapiAvailable;

function canUseDpapi() {
  if (dpapiAvailable !== undefined) {
    return dpapiAvailable;
  }
  if (process.platform !== "win32" || !fs.existsSync(powershell)) {
    dpapiAvailable = false;
    return dpapiAvailable;
  }
  const probe = spawnSync(
    powershell,
    [
      "-NoProfile",
      "-NonInteractive",
      "-Command",
      "Add-Type -AssemblyName System.Security; " +
        "$b=[Text.Encoding]::UTF8.GetBytes('probe'); " +
        "[void][Security.Cryptography.ProtectedData]::Protect(" +
        "$b,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)",
    ],
    { encoding: "utf8" },
  );
  dpapiAvailable = probe.status === 0;
  return dpapiAvailable;
}

function quotePowerShell(value) {
  return `'${value.replaceAll("'", "''")}'`;
}

test("cofre local cifra as duas credenciais e permite lê-las somente ao mesmo usuário", (t) => {
  if (!canUseDpapi()) {
    t.skip("DPAPI CurrentUser indisponível neste executor");
    return;
  }
  const temporaryDirectory = fs.mkdtempSync(
    path.join(os.tmpdir(), "barreiras-credential-store-"),
  );
  const storePath = path.join(temporaryDirectory, "credentials.json");
  const databasePassword = "db-test-password-with-32-characters";
  const workloadPassword = "storage-test-password-32-characters";

  try {
    const command = [
      "$ErrorActionPreference = 'Stop'",
      `. ${quotePowerShell(helperPath)}`,
      `Write-CollectorCredentialStore -Path ${quotePowerShell(storePath)} -ProjectRef 'testprojectref123456' -DatabasePassword ${quotePowerShell(databasePassword)} -WorkloadPassword ${quotePowerShell(workloadPassword)}`,
      `$store = Read-CollectorCredentialStore -Path ${quotePowerShell(storePath)} -ExpectedProjectRef 'testprojectref123456'`,
      "[pscustomobject]@{DatabaseLength=$store.DatabasePassword.Length;WorkloadLength=$store.WorkloadPassword.Length;Status=$store.Status} | ConvertTo-Json -Compress",
    ].join("; ");

    const output = execFileSync(
      powershell,
      [
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        command,
      ],
      { encoding: "utf8" },
    ).trim();
    const result = JSON.parse(output);
    const encryptedFile = fs.readFileSync(storePath, "utf8");

    assert.equal(result.DatabaseLength, databasePassword.length);
    assert.equal(result.WorkloadLength, workloadPassword.length);
    assert.equal(result.Status, "active");
    assert.doesNotMatch(encryptedFile, new RegExp(databasePassword));
    assert.doesNotMatch(encryptedFile, new RegExp(workloadPassword));
    assert.match(encryptedFile, /"protection_scope"\s*:\s*"CurrentUser"/);
  } finally {
    fs.rmSync(temporaryDirectory, { recursive: true, force: true });
  }
});

test("cofre local recusa credencial pertencente a outro projeto Supabase", (t) => {
  if (!canUseDpapi()) {
    t.skip("DPAPI CurrentUser indisponível neste executor");
    return;
  }
  const temporaryDirectory = fs.mkdtempSync(
    path.join(os.tmpdir(), "barreiras-credential-store-mismatch-"),
  );
  const storePath = path.join(temporaryDirectory, "credentials.json");

  try {
    const command = [
      "$ErrorActionPreference = 'Stop'",
      `. ${quotePowerShell(helperPath)}`,
      `Write-CollectorCredentialStore -Path ${quotePowerShell(storePath)} -ProjectRef 'testprojectref123456' -DatabasePassword 'db-test-password-with-32-characters' -WorkloadPassword 'storage-test-password-32-characters'`,
      `Read-CollectorCredentialStore -Path ${quotePowerShell(storePath)} -ExpectedProjectRef 'differentproject12345'`,
    ].join("; ");
    const result = spawnSync(
      powershell,
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

    assert.notEqual(result.status, 0);
    assert.match(
      `${result.stdout}\n${result.stderr}`,
      /projeto Supabase esperado/i,
    );
  } finally {
    fs.rmSync(temporaryDirectory, { recursive: true, force: true });
  }
});

test("cofre local recusa uma rotação ainda incompleta", (t) => {
  if (!canUseDpapi()) {
    t.skip("DPAPI CurrentUser indisponível neste executor");
    return;
  }
  const temporaryDirectory = fs.mkdtempSync(
    path.join(os.tmpdir(), "barreiras-credential-store-staged-"),
  );
  const storePath = path.join(temporaryDirectory, "credentials.json");

  try {
    const command = [
      "$ErrorActionPreference = 'Stop'",
      `. ${quotePowerShell(helperPath)}`,
      `Write-CollectorCredentialStore -Path ${quotePowerShell(storePath)} -ProjectRef 'testprojectref123456' -DatabasePassword 'db-test-password-with-32-characters' -WorkloadPassword 'storage-test-password-32-characters' -Status staged`,
      `Read-CollectorCredentialStore -Path ${quotePowerShell(storePath)} -ExpectedProjectRef 'testprojectref123456'`,
    ].join("; ");
    const result = spawnSync(
      powershell,
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

    assert.notEqual(result.status, 0);
    assert.match(
      `${result.stdout}\n${result.stderr}`,
      /rota.*incompleta/i,
    );
  } finally {
    fs.rmSync(temporaryDirectory, { recursive: true, force: true });
  }
});
