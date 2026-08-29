import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const wrapperPath = fileURLToPath(
  new URL("../../scripts/run-tcm-ba-document-pilot.ps1", import.meta.url),
);
const wrapper = fs.readFileSync(wrapperPath, "utf8");
const helper = path.resolve(
  fileURLToPath(
    new URL("../../scripts/lib/tcm-ba-replay-validation.ps1", import.meta.url),
  ),
);

function runGate(events, maxDocuments = 5) {
  const helperPath = helper.replaceAll("'", "''");
  const payload = JSON.stringify(events).replaceAll("'", "''");
  return spawnSync(
    process.env.PWSH_PATH ?? "pwsh",
    [
      "-NoProfile",
      "-NonInteractive",
      "-Command",
      `. '${helperPath}'; $events = ConvertFrom-Json '${payload}'; ` +
        `Assert-TcmBaDocumentTextApproval -Events @($events) -MaxDocuments ${maxDocuments}`,
    ],
    { encoding: "utf8" },
  );
}

function event(overrides = {}) {
  return {
    event: "tcm_ba_document_text_batch_completed",
    pending_found: 5,
    processed: 5,
    failed: 0,
    pages_total: 12,
    pages_with_embedded_text: 9,
    pages_awaiting_ocr: 3,
    ...overrides,
  };
}

test("wrapper processa texto somente depois da auditoria física", () => {
  const audit = wrapper.indexOf("Assert-TcmBaDocumentAuditApproval");
  const processor = wrapper.indexOf(
    "barreiras_docproc.commands.process_tcm_ba_documents",
  );
  const textGate = wrapper.indexOf("Assert-TcmBaDocumentTextApproval");
  const ocr = wrapper.indexOf("--source tcm-ba");
  const approval = wrapper.indexOf("TCM_BA_DOCUMENT_PILOT_APPROVED");
  assert.ok(audit >= 0);
  assert.ok(processor > audit);
  assert.ok(textGate > processor);
  assert.ok(ocr > textGate);
  assert.ok(approval > ocr);
  assert.match(
    wrapper,
    /workers\/collectors\/src;workers\/document-processing\/src/,
  );
});

test("gate aceita páginas embutidas e páginas explicitamente pendentes de OCR", () => {
  const result = runGate([event()]);
  assert.equal(result.status, 0, result.stdout + "\n" + result.stderr);
});

test("gate rejeita falha, lote vazio e contadores de páginas divergentes", () => {
  for (const invalid of [
    event({ failed: 1, processed: 4 }),
    event({ pending_found: 0, processed: 0, pages_total: 0, pages_with_embedded_text: 0, pages_awaiting_ocr: 0 }),
    event({ pages_awaiting_ocr: 4 }),
  ]) {
    const result = runGate([invalid]);
    assert.notEqual(result.status, 0, result.stdout + "\n" + result.stderr);
  }
});

test("gate rejeita evento duplicado e lote acima do máximo", () => {
  const duplicate = runGate([event(), event()]);
  assert.notEqual(duplicate.status, 0);
  const aboveLimit = runGate([event({ pending_found: 5, processed: 5 })], 4);
  assert.notEqual(aboveLimit.status, 0);
});
