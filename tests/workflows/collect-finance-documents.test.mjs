import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workflow = await readFile(
  new URL("../../.github/workflows/collect-finance-documents.yml", import.meta.url),
  "utf8",
);

const financeWorkflowGroups = new Map([
  ["collect-finance-documents.yml", "municipal-finance-collection-production"],
  ["collect-municipal-transparency.yml", "municipal-finance-collection-production"],
  ["publish-financial-revenues.yml", "municipal-finance-publication-production"],
  ["publish-financial-expenses.yml", "municipal-finance-publication-production"],
  ["publish-monthly-finance-commentary.yml", "municipal-finance-publication-production"],
  ["refresh-finance-signals.yml", "municipal-finance-publication-production"],
]);

const financeWorkflows = await Promise.all(
  [...financeWorkflowGroups].map(async ([fileName, concurrencyGroup]) => ({
    fileName,
    concurrencyGroup,
    contents: await readFile(
      new URL(`../../.github/workflows/${fileName}`, import.meta.url),
      "utf8",
    ),
  })),
);

test("workflows financeiros respeitam as duas filas da role PostgreSQL limitada", () => {
  for (const { fileName, concurrencyGroup, contents } of financeWorkflows) {
    assert.match(
      contents,
      new RegExp(
        `concurrency:\\s*\\n\\s+group: ${concurrencyGroup}\\s*\\n\\s+cancel-in-progress: false`,
      ),
      `${fileName} precisa usar a fila financeira correspondente`,
    );
  }
});

test("coleta financeira respeita o orçamento de conexões", () => {
  assert.match(workflow, /max-parallel: \$\{\{ \(inputs\.resource == 'all' \|\| inputs\.resource == ''\) && 1 \|\| 8 \}\}/);
  assert.match(workflow, /QUERIDO_DIARIO_DATABASE_URL/);
  assert.match(workflow, /--download-documents/);
});

test("coletores complementares aguardam uns aos outros para não saturar o Supabase", () => {
  const transferegovJob = workflow.slice(
    workflow.indexOf("  transferegov:"),
    workflow.indexOf("  bahia_state_amendments:"),
  );
  const stateExecutionJob = workflow.slice(
    workflow.indexOf("  bahia_state_amendments:"),
    workflow.indexOf("  bahia_state_loa_amendments:"),
  );
  const stateLoaJob = workflow.slice(
    workflow.indexOf("  bahia_state_loa_amendments:"),
  );

  assert.match(transferegovJob, /needs: collect/);
  assert.match(
    stateExecutionJob,
    /needs:\s*\n\s*- collect\s*\n\s*- transferegov/,
  );
  assert.match(
    stateLoaJob,
    /needs:\s*\n\s*- collect\s*\n\s*- transferegov\s*\n\s*- bahia_state_amendments/,
  );
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
  assert.match(
    workflow,
    /MUNICIPAL_TRANSPARENCY_MAX_BATCH_DOCUMENT_BYTES: \"67108864\"/,
  );
});

test("coleta financeira preserva fontes oficiais de dividas e obrigacoes", () => {
  const collectionStep = workflow.slice(
    workflow.indexOf("- name: Preservar catálogo municipal"),
    workflow.indexOf("- name: Drenar documentos municipais"),
  );
  const collectionRun = collectionStep.slice(collectionStep.indexOf("run: >-"));

  assert.match(workflow, /balancetes/);
  assert.match(workflow, /pdc-contas-anuais/);
  assert.match(workflow, /rgf/);
  assert.match(workflow, /COLLECT_LIMIT: >-[\s\S]*balancetes'[\s\S]*'500'/);
  assert.match(workflow, /COVERAGE_ARGUMENTS: >-[\s\S]*--coverage-year-from 2021/);
  assert.doesNotMatch(collectionRun, /\$\{\{ matrix\.resource == 'balancetes'/);
});

test("coleta financeira preserva o catalogo privado de pessoal sem publica-lo", () => {
  assert.match(workflow, /- "servidores"/);
  assert.match(
    workflow,
    /\["balancetes"[\s\S]*"servidores"\]/,
  );
  assert.match(
    workflow,
    /COLLECT_LIMIT: >-[\s\S]*matrix\.resource == 'servidores'[\s\S]*'500'/,
  );
  assert.match(
    workflow,
    /DRAIN_MAX_DOCUMENTS: >-[\s\S]*matrix\.resource == 'servidores'[\s\S]*'5'/,
  );
  assert.doesNotMatch(workflow, /publish[_-]payroll/i);
});

test("coleta de pessoal aceita uma competencia exata sem baixar outros tipos", () => {
  assert.match(workflow, /personnel_reference_month:/);
  assert.match(workflow, /INPUT_PERSONNEL_REFERENCE_MONTH:/);
  assert.match(
    workflow,
    /--document-reference-month "\$INPUT_PERSONNEL_REFERENCE_MONTH"/,
  );
  assert.match(workflow, /--document-type "1"/);
  assert.match(
    workflow,
    /--allow-untyped-document-title "Relação de Servidores"/,
  );
  assert.match(workflow, /--document-title "Relação de Servidores"/);
  assert.match(workflow, /--document-title "Relação Servidores"/);
  assert.match(
    workflow,
    /--document-title "Relação de Servidores 13º Salário"/,
  );
  assert.match(
    workflow,
    /\^20\[2-9\]\[0-9\]-\(0\[1-9\]\|1\[0-2\]\)\$/,
  );
});

test("cobertura de balancetes nao espera o download de todo o acervo", () => {
  const collectionStep = workflow.slice(
    workflow.indexOf("- name: Preservar catálogo municipal"),
    workflow.indexOf("- name: Drenar documentos municipais"),
  );
  const drainStep = workflow.slice(
    workflow.indexOf("- name: Drenar documentos municipais"),
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

test("DOCX municipais preservados recebem texto privado uma unica vez", () => {
  const collectJob = workflow.slice(
    workflow.indexOf("  collect:"),
    workflow.indexOf("  transferegov:"),
  );
  const drainIndex = collectJob.indexOf("- name: Drenar documentos municipais");
  const processIndex = collectJob.indexOf("- name: Processar texto dos DOCX municipais");

  assert.match(
    collectJob,
    /PYTHONPATH: workers\/collectors\/src:workers\/document-processing\/src/,
  );
  assert.ok(drainIndex >= 0);
  assert.ok(processIndex > drainIndex);
  assert.match(
    collectJob,
    /if: matrix\.resource == 'pdc-contas-anuais'/,
  );
  assert.match(
    collectJob,
    /barreiras_docproc\.commands\.process_municipal_docx\s+--limit 10\s+--minimum-total 4/,
  );
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

test("CGU federal completa emendas de Barreiras sem chave privada", () => {
  const transferegovJob = workflow.slice(
    workflow.indexOf("  transferegov:"),
    workflow.indexOf("  bahia_state_amendments:"),
  );

  assert.match(
    transferegovJob,
    /barreiras_collectors\.commands\.collect_cgu_federal_amendments/,
  );
  assert.match(
    transferegovJob,
    /barreiras_collectors\.commands\.collect_cgu_federal_amendment_documents[\s\S]*--year-from "2021"/,
  );
  assert.doesNotMatch(transferegovJob, /TRANSPARENCIA_API_KEY/);
  assert.ok(
    transferegovJob.indexOf("collect_cgu_federal_amendments") <
      transferegovJob.indexOf("collect_cgu_federal_amendment_documents"),
  );
  assert.ok(
    transferegovJob.indexOf("collect_cgu_federal_amendment_documents") <
      transferegovJob.indexOf("collect_transferegov_parcerias"),
  );
});

test("modo somente Transferegov nao abre coletores independentes", () => {
  const collectJob = workflow.slice(
    workflow.indexOf("  collect:"),
    workflow.indexOf("  transferegov:"),
  );
  const transferegovJob = workflow.slice(
    workflow.indexOf("  transferegov:"),
    workflow.indexOf("  bahia_state_amendments:"),
  );
  const stateJobs = workflow.slice(
    workflow.indexOf("  bahia_state_amendments:"),
  );

  assert.match(workflow, /- "transferegov-only"/);
  assert.match(
    collectJob,
    /inputs\.resource != 'transferegov-only'/,
  );
  assert.match(
    transferegovJob,
    /inputs\.resource == 'transferegov-only'/,
  );
  assert.match(
    stateJobs,
    /inputs\.resource != 'transferegov-only'/,
  );
});

test("modo somente Bahia executa as duas trilhas estaduais sem abrir jobs alheios", () => {
  const collectJob = workflow.slice(
    workflow.indexOf("  collect:"),
    workflow.indexOf("  transferegov:"),
  );
  const transferegovJob = workflow.slice(
    workflow.indexOf("  transferegov:"),
    workflow.indexOf("  bahia_state_amendments:"),
  );
  const stateExecutionJob = workflow.slice(
    workflow.indexOf("  bahia_state_amendments:"),
    workflow.indexOf("  bahia_state_loa_amendments:"),
  );
  const stateLoaJob = workflow.slice(
    workflow.indexOf("  bahia_state_loa_amendments:"),
  );

  assert.match(workflow, /- "bahia-state-only"/);
  assert.match(collectJob, /inputs\.resource != 'bahia-state-only'/);
  assert.match(transferegovJob, /inputs\.resource != 'bahia-state-only'/);
  assert.match(stateExecutionJob, /inputs\.resource == 'bahia-state-only'/);
  assert.match(stateLoaJob, /inputs\.resource == 'bahia-state-only'/);
});

test("execucao municipal direcionada nao dispara coletores complementares por padrao", () => {
  const transferegovJob = workflow.slice(
    workflow.indexOf("  transferegov:"),
    workflow.indexOf("  bahia_state_amendments:"),
  );
  const stateJobs = workflow.slice(
    workflow.indexOf("  bahia_state_amendments:"),
  );

  assert.match(
    transferegovJob,
    /inputs\.resource == 'all'\s*&&\s*inputs\.include_transferegov == true/,
  );
  assert.match(
    stateJobs,
    /inputs\.resource == 'all'\s*&&\s*inputs\.include_bahia_state_amendments == true/,
  );
  assert.match(
    stateJobs,
    /inputs\.resource == 'all'\s*&&\s*inputs\.include_bahia_special_transfers == true/,
  );
  assert.match(
    stateJobs,
    /inputs\.resource == 'all'\s*&&\s*inputs\.include_bahia_state_loa_amendments == true/,
  );
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

test("catálogo mensal do TCM-BA exige disparo manual e intervalo explícito", () => {
  const tcmJob = workflow.slice(
    workflow.indexOf("  tcm_ba_monthly:"),
    workflow.indexOf("  bahia_state_amendments:"),
  );

  assert.match(workflow, /- "tcm-ba-only"/);
  assert.match(workflow, /include_tcm_ba_monthly:/);
  assert.match(workflow, /tcm_month_from:/);
  assert.match(workflow, /tcm_month_to:/);
  assert.match(tcmJob, /github\.event_name == 'workflow_dispatch'/);
  assert.match(
    tcmJob,
    /barreiras_collectors\.commands\.collect_tcm_ba_monthly_catalog/,
  );
  assert.match(tcmJob, /--month-from "\$\{\{ inputs\.tcm_month_from \}\}"/);
  assert.match(tcmJob, /--month-to "\$\{\{ inputs\.tcm_month_to \}\}"/);
  assert.match(tcmJob, /--requests-per-minute "30"/);
  assert.doesNotMatch(tcmJob, /github\.event_name == 'schedule'/);
  assert.doesNotMatch(tcmJob, /secrets\.(tcm_month_from|tcm_month_to)/i);
});
