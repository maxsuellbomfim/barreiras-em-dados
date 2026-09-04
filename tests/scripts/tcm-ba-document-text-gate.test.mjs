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

function familyCatchUpLimit(maxDocuments) {
  const helperPath = helper.replaceAll("'", "''");
  return spawnSync(
    process.env.PWSH_PATH ?? "pwsh",
    [
      "-NoProfile",
      "-NonInteractive",
      "-Command",
      `. '${helperPath}'; Get-TcmBaDocumentFamilyCatchUpLimit -MaxDocuments ${maxDocuments}`,
    ],
    { encoding: "utf8" },
  );
}

function commitmentCatchUpLimit(maxDocuments) {
  const helperPath = helper.replaceAll("'", "''");
  return spawnSync(
    process.env.PWSH_PATH ?? "pwsh",
    [
      "-NoProfile",
      "-NonInteractive",
      "-Command",
      `. '${helperPath}'; Get-TcmBaCommitmentCatchUpLimit -MaxDocuments ${maxDocuments}`,
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
    audit,
  );
  const textGate = wrapper.indexOf("Assert-TcmBaDocumentTextApproval", processor);
  const ocr = wrapper.indexOf("--source tcm-ba");
  const report = wrapper.lastIndexOf(
    "Invoke-TcmBaDocumentProcessingReport",
  );
  const commitments = wrapper.lastIndexOf(
    "Invoke-TcmBaCommitmentCandidateProcessing",
  );
  const commitmentCoverage = wrapper.lastIndexOf(
    "Invoke-TcmBaCommitmentCandidateCoverage",
  );
  const families = wrapper.lastIndexOf(
    "Invoke-TcmBaDocumentFamilyInventory",
  );
  const familyCoverage = wrapper.lastIndexOf(
    "Invoke-TcmBaDocumentFamilyCoverage",
  );
  const contractDocuments = wrapper.lastIndexOf(
    "Invoke-TcmBaContractDocumentProcessing",
  );
  const contractCoverage = wrapper.lastIndexOf(
    "Invoke-TcmBaContractDocumentCoverage",
  );
  const contractFields = wrapper.lastIndexOf(
    "Invoke-TcmBaContractFieldProcessing",
  );
  const contractFieldCoverage = wrapper.lastIndexOf(
    "Invoke-TcmBaContractFieldCoverage",
  );
  const approval = wrapper.indexOf("TCM_BA_DOCUMENT_PILOT_APPROVED");
  assert.ok(audit >= 0);
  assert.ok(processor > audit);
  assert.ok(textGate > processor);
  assert.ok(ocr > textGate);
  assert.ok(report > ocr);
  assert.ok(families > report);
  assert.ok(familyCoverage > families);
  assert.ok(contractDocuments > familyCoverage);
  assert.ok(contractCoverage > contractDocuments);
  assert.ok(contractFields > contractCoverage);
  assert.ok(contractFieldCoverage > contractFields);
  assert.ok(commitments > contractFieldCoverage);
  assert.ok(commitmentCoverage > commitments);
  assert.ok(approval > commitmentCoverage);
  assert.match(
    wrapper,
    /Invoke-TcmBaContractFieldCoverage[^\r\n]*[\s\S]*?Get-TcmBaCommitmentCatchUpLimit[\s\S]*?Invoke-TcmBaCommitmentCandidateProcessing/,
  );
  assert.match(
    wrapper,
    /Invoke-TcmBaCommitmentCandidateProcessing[\s\S]*Invoke-TcmBaCommitmentCandidateCoverage/,
  );
  assert.match(
    wrapper,
    /workers\/collectors\/src;workers\/document-processing\/src/,
  );
});

test("wrapper reserva uma segunda janela limitada para drenar famílias atrasadas", () => {
  const result = familyCatchUpLimit(5);
  assert.equal(result.status, 0, result.stdout + "\n" + result.stderr);
  assert.equal(result.stdout.trim(), "10");
  assert.match(wrapper, /Get-TcmBaDocumentFamilyCatchUpLimit/);
  assert.match(
    wrapper,
    /Invoke-TcmBaDocumentFamilyInventory[\s\S]*?-Limit \$familyCatchUpLimit/,
  );
});

test("wrapper drena até cinquenta empenhos atrasados sem ampliar a coleta", () => {
  const result = commitmentCatchUpLimit(5);
  assert.equal(result.status, 0, result.stdout + "\n" + result.stderr);
  assert.equal(result.stdout.trim(), "50");
  assert.match(wrapper, /Get-TcmBaCommitmentCatchUpLimit/);
  assert.match(
    wrapper,
    /Invoke-TcmBaCommitmentCandidateProcessing[\s\S]*?-Limit \$commitmentCatchUpLimit/,
  );
});

test("gate aceita páginas embutidas e páginas explicitamente pendentes de OCR", () => {
  const result = runGate([event()]);
  assert.equal(result.status, 0, result.stdout + "\n" + result.stderr);
});

test("gate de texto aceita lote operacional de dez documentos", () => {
  const result = runGate(
    [
      event({
        pending_found: 10,
        processed: 10,
        pages_total: 24,
        pages_with_embedded_text: 20,
        pages_awaiting_ocr: 4,
      }),
    ],
    10,
  );
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
test("wrapper oferece relatório somente leitura sem iniciar o coletor", () => {
  const reportOnly = wrapper.indexOf("if ($ReportOnly)");
  const reportCall = wrapper.indexOf(
    "Invoke-TcmBaDocumentProcessingReport",
    reportOnly,
  );
  const collector = wrapper.indexOf(
    "barreiras_collectors.commands.collect_tcm_ba_documents",
  );
  assert.match(wrapper, /\[switch\]\$ReportOnly/);
  assert.ok(reportOnly >= 0);
  assert.ok(reportCall > reportOnly);
  assert.ok(collector > reportCall);
});

test("wrapper oferece replay privado limitado sem iniciar o coletor", () => {
  const replayOnly = wrapper.indexOf("if ($CommitmentReplayOnly)");
  const processor = wrapper.indexOf(
    "barreiras_docproc.commands.process_tcm_ba_commitments --limit 50",
    replayOnly,
  );
  const coverage = wrapper.indexOf(
    "Invoke-TcmBaCommitmentCandidateCoverage",
    processor,
  );
  const collector = wrapper.indexOf(
    "barreiras_collectors.commands.collect_tcm_ba_documents",
  );
  assert.match(wrapper, /\[switch\]\$CommitmentReplayOnly/);
  assert.match(wrapper, /for \(\$batch = 1; \$batch -le 20; \$batch\+\+\)/);
  assert.ok(replayOnly >= 0);
  assert.ok(processor > replayOnly);
  assert.ok(coverage > processor);
  assert.ok(collector > coverage);
  assert.match(wrapper, /TCM_BA_COMMITMENT_REPLAY_APPROVED/);
});

test("wrapper oferece benchmark privado e agregado de credores", () => {
  const benchmarkOnly = wrapper.indexOf("if ($CommitmentCreditorBenchmarkOnly)");
  const benchmark = wrapper.indexOf(
    "barreiras_docproc.commands.benchmark_tcm_ba_commitment_creditors --limit 500",
    benchmarkOnly,
  );
  const collector = wrapper.indexOf(
    "barreiras_collectors.commands.collect_tcm_ba_documents",
  );
  assert.match(wrapper, /\[switch\]\$CommitmentCreditorBenchmarkOnly/);
  assert.ok(benchmarkOnly >= 0);
  assert.ok(benchmark > benchmarkOnly);
  assert.ok(collector > benchmark);
  assert.match(wrapper, /TCM_BA_COMMITMENT_CREDITOR_BENCHMARK_APPROVED/);
});

test("wrapper oferece benchmark privado e agregado de datas", () => {
  const benchmarkOnly = wrapper.indexOf("if ($CommitmentIssueDateBenchmarkOnly)");
  const benchmark = wrapper.indexOf(
    "barreiras_docproc.commands.benchmark_tcm_ba_commitment_dates --limit 500",
    benchmarkOnly,
  );
  const collector = wrapper.indexOf(
    "barreiras_collectors.commands.collect_tcm_ba_documents",
  );
  assert.match(wrapper, /\[switch\]\$CommitmentIssueDateBenchmarkOnly/);
  assert.ok(benchmarkOnly >= 0);
  assert.ok(benchmark > benchmarkOnly);
  assert.ok(collector > benchmark);
  assert.match(wrapper, /TCM_BA_COMMITMENT_ISSUE_DATE_BENCHMARK_APPROVED/);
});
test("wrapper oferece auditoria física somente leitura sem iniciar o coletor", () => {
  const auditOnly = wrapper.indexOf("if ($AuditOnly)");
  const auditCall = wrapper.indexOf(
    "barreiras_collectors.commands.audit_tcm_ba_document_batch",
    auditOnly,
  );
  const collector = wrapper.indexOf(
    "barreiras_collectors.commands.collect_tcm_ba_documents",
  );
  assert.match(wrapper, /\[switch\]\$AuditOnly/);
  assert.ok(auditOnly >= 0);
  assert.ok(auditCall > auditOnly);
  assert.ok(collector > auditCall);
  assert.match(wrapper, /TCM_BA_DOCUMENT_AUDIT_ONLY/);
});
