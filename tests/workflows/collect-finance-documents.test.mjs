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
