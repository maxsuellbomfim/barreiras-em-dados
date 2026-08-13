import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workflow = await readFile(
  new URL("../../.github/workflows/collect-finance-documents.yml", import.meta.url),
  "utf8",
);

test("coleta financeira respeita o orçamento de conexões", () => {
  assert.match(workflow, /max-parallel: \$\{\{ \(inputs\.resource == 'all' \|\| inputs\.resource == ''\) && 1 \|\| 8 \}\}/);
  assert.match(workflow, /QUERIDO_DIARIO_DATABASE_URL/);
  assert.match(workflow, /--download-documents/);
});

test("coleta financeira permite backfill por recurso e documentos grandes", () => {
  assert.match(workflow, /resource:/);
  assert.match(workflow, /pdc-resumo-execucao-da-despesa/);
  assert.match(workflow, /max_pages:[\s\S]*- \"50\"/);
  assert.match(workflow, /max-parallel: \$\{\{ \(inputs\.resource == 'all' \|\| inputs\.resource == ''\) && 1 \|\| 8 \}\}/);
  assert.match(workflow, /resource: >-[\s\S]*fromJSON\(/);
  assert.match(workflow, /format\('\[\"\{0\}\"\]'/);
  assert.doesNotMatch(workflow, /\n\s{4}if: \$\{\{[^\n]*matrix\.resource/);
  assert.match(workflow, /MUNICIPAL_TRANSPARENCY_MAX_DOCUMENT_BYTES: \"268435456\"/);
});

test("coleta financeira preserva fontes oficiais de dividas e obrigacoes", () => {
  const collectionStep = workflow.slice(
    workflow.indexOf("- name: Preservar documento financeiro"),
    workflow.indexOf("- name: Drenar documentos financeiros"),
  );
  const collectionRun = collectionStep.slice(collectionStep.indexOf("run: >-"));

  assert.match(workflow, /balancetes/);
  assert.match(workflow, /pdc-contas-anuais/);
  assert.match(workflow, /rgf/);
  assert.match(workflow, /COLLECT_LIMIT: >-[\s\S]*balancetes'[\s\S]*'500'/);
  assert.match(workflow, /COVERAGE_ARGUMENTS: >-[\s\S]*--coverage-year-from 2021/);
  assert.doesNotMatch(collectionRun, /\$\{\{ matrix\.resource == 'balancetes'/);
});

test("cobertura de balancetes nao espera o download de todo o acervo", () => {
  const collectionStep = workflow.slice(
    workflow.indexOf("- name: Preservar documento financeiro"),
    workflow.indexOf("- name: Drenar documentos financeiros"),
  );
  const drainStep = workflow.slice(
    workflow.indexOf("- name: Drenar documentos financeiros"),
  );

  assert.doesNotMatch(collectionStep, /--download-documents/);
  assert.match(
    drainStep,
    /DRAIN_LIMIT: >-[\s\S]*matrix\.resource == 'balancetes'[\s\S]*'500'/,
  );
  assert.match(
    drainStep,
    /DRAIN_MAX_DOCUMENTS: >-[\s\S]*matrix\.resource == 'balancetes'[\s\S]*'5'/,
  );
  assert.match(drainStep, /--resource "\$\{\{ matrix\.resource \}\}"/);
  assert.match(drainStep, /--limit "\$DRAIN_LIMIT"/);
  assert.match(drainStep, /--max-pages "\$DRAIN_MAX_PAGES"/);
  assert.match(drainStep, /--max-documents "\$DRAIN_MAX_DOCUMENTS"/);
  assert.match(drainStep, /--download-documents/);
});

test("Transferegov classifica cada ano desde 2021 sem entrada livre no shell", () => {
  const transferegovJob = workflow.slice(workflow.indexOf("  transferegov:"));

  assert.match(transferegovJob, /--year-from "2021"/);
  assert.match(
    transferegovJob,
    /barreiras_collectors\.commands\.collect_transferegov_download_catalog/,
  );
  assert.doesNotMatch(transferegovJob, /--year-from "\$\{\{/);
  assert.doesNotMatch(transferegovJob, /--year-to "\$\{\{/);
});

test("LOA estadual e extraida deterministicamente depois da preservacao", () => {
  const loaJob = workflow.slice(
    workflow.indexOf("  bahia_state_loa_amendments:"),
  );

  assert.match(
    loaJob,
    /PYTHONPATH: workers\/collectors\/src:workers\/document-processing\/src/,
  );
  assert.match(loaJob, /"\.\[postgres,storage,pdf\]"/);
  const preserveIndex = loaJob.indexOf(
    "barreiras_collectors.commands.collect_bahia_state_loa_amendments",
  );
  const processIndex = loaJob.indexOf(
    "barreiras_docproc.commands.process_bahia_state_loa",
  );
  assert.ok(preserveIndex >= 0);
  assert.ok(processIndex > preserveIndex);
  assert.match(loaJob, /--limit "10"/);
});

test("execucao estadual e normalizada depois de preservar o ZIP oficial", () => {
  const stateJob = workflow.slice(
    workflow.indexOf("  bahia_state_amendments:"),
    workflow.indexOf("  bahia_state_loa_amendments:"),
  );

  assert.match(
    stateJob,
    /PYTHONPATH: workers\/collectors\/src:workers\/normalization\/src/,
  );
  const preserveIndex = stateJob.indexOf(
    "barreiras_collectors.commands.collect_bahia_state_amendments",
  );
  const processIndex = stateJob.indexOf(
    "barreiras_normalization.commands.process_bahia_state_execution",
  );
  assert.ok(preserveIndex >= 0);
  assert.ok(processIndex > preserveIndex);
  assert.match(stateJob, /--limit "1"/);
});

test("arquivo histórico de propostas exige opt-in e recorta Barreiras desde 2021", () => {
  const transferegovJob = workflow.slice(workflow.indexOf("  transferegov:"));

  assert.match(workflow, /include_transferegov_historical_proposals:/);
  assert.match(
    transferegovJob,
    /if: github\.event_name == 'workflow_dispatch' && inputs\.include_transferegov_historical_proposals == true/,
  );
  assert.match(
    transferegovJob,
    /barreiras_collectors\.commands\.collect_transferegov_historical_proposals/,
  );
  assert.match(transferegovJob, /--year-from "2021"/);
  assert.doesNotMatch(
    transferegovJob,
    /collect_transferegov_historical_proposals[\s\S]*--year-from "\$\{\{/,
  );
});
