import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workflow = await readFile(
  new URL("../../.github/workflows/collect-tcm-ba-documents.yml", import.meta.url),
  "utf8",
);

test("lote documental TCM-BA é serial, limitado e auditado", () => {
  assert.doesNotMatch(workflow, /\n\s*schedule:/);
  assert.match(workflow, /workflow_dispatch:/);
  assert.match(
    workflow,
    /concurrency:\s*\n\s+group: municipal-finance-collection-production\s*\n\s+cancel-in-progress: false/,
  );
  assert.match(workflow, /max_documents:[\s\S]*options:\s*\n\s+- "1"\s*\n\s+- "5"/);
  assert.match(workflow, /--requests-per-minute "30"/);
  assert.doesNotMatch(workflow, /--requests-per-minute "(?:3[1-9]|[4-9][0-9]|[1-9][0-9]{2,})"/);

  const collectIndex = workflow.indexOf(
    "barreiras_collectors.commands.collect_tcm_ba_documents",
  );
  const auditIndex = workflow.indexOf(
    "barreiras_collectors.commands.audit_tcm_ba_document_batch",
  );
  const textIndex = workflow.indexOf(
    "barreiras_docproc.commands.process_tcm_ba_documents",
  );
  const ocrIndex = workflow.indexOf(
    "barreiras_docproc.commands.ocr_gazette_pages",
  );
  const reportIndex = workflow.indexOf(
    "barreiras_docproc.commands.report_tcm_ba_document_processing",
  );
  const familyIndex = workflow.indexOf(
    "barreiras_docproc.commands.process_tcm_ba_document_families",
  );
  const familyCoverageIndex = workflow.indexOf(
    "barreiras_docproc.commands.report_tcm_ba_document_families",
  );
  const commitmentIndex = workflow.indexOf(
    "barreiras_docproc.commands.process_tcm_ba_commitments",
  );
  const approveIndex = workflow.indexOf("TCM_BA_DOCUMENT_PILOT_APPROVED");
  assert.ok(collectIndex >= 0);
  assert.ok(auditIndex > collectIndex);
  assert.ok(textIndex > auditIndex);
  assert.ok(ocrIndex > textIndex);
  assert.ok(reportIndex > ocrIndex);
  assert.ok(familyIndex > reportIndex);
  assert.ok(familyCoverageIndex > familyIndex);
  assert.ok(commitmentIndex > familyCoverageIndex);
  assert.ok(approveIndex > commitmentIndex);
  assert.match(
    workflow,
    /PYTHONPATH: workers\/collectors\/src:workers\/document-processing\/src/,
  );
  assert.match(workflow, /\.\[postgres,storage,pdf,ocr\]/);
  assert.match(workflow, /tesseract-ocr-por/);
  assert.match(workflow, /--source tcm-ba/);
});

test("agendamento escolhe a competência mais antiga sem entrada livre no shell", () => {
  assert.match(
    workflow,
    /barreiras_collectors\.commands\.plan_tcm_ba_document_batch --year-from 2021/,
  );
  assert.match(
    workflow,
    /REQUESTED_COMPETENCE: \$\{\{ github\.event_name == 'workflow_dispatch' && inputs\.competence \|\| '' \}\}/,
  );
  assert.match(workflow, /\^\(0\[1-9\]\|1\[0-2\]\)\/\[0-9\]\{4\}\$/);
  assert.match(workflow, /if: steps\.plan\.outputs\.competence != ''/);
  assert.doesNotMatch(
    workflow,
    /--competence "\$\{\{\s*inputs\.competence\s*\}\}"/,
  );
});

test("workflow usa apenas credenciais técnicas existentes e CA verificada", () => {
  assert.match(workflow, /QUERIDO_DIARIO_DATABASE_URL/);
  assert.match(workflow, /MUNICIPAL_TRANSPARENCY_SUPABASE_WORKLOAD_EMAIL/);
  assert.match(workflow, /MUNICIPAL_TRANSPARENCY_SUPABASE_WORKLOAD_PASSWORD/);
  assert.match(workflow, /sha256sum --check --strict/);
  assert.doesNotMatch(workflow, /SUPABASE_SERVICE_ROLE_KEY|SUPABASE_SECRET_KEY/);
  assert.match(workflow, /permissions:\s*\n\s+contents: read/);
  const beforeSteps = workflow.slice(0, workflow.indexOf("    steps:"));
  assert.doesNotMatch(beforeSteps, /secrets\.|SUPABASE_WORKLOAD_PASSWORD/);
});

test("modo de backlog processa acervo preservado sem acessar o e-TCM", () => {
  assert.match(
    workflow,
    /mode:[\s\S]*options:\s*\n\s+- "collect"\s*\n\s+- "process_existing"\s*\n\s+- "process_pages"/,
  );
  assert.match(
    workflow,
    /process_existing:[\s\S]*if: github\.event_name == 'workflow_dispatch' && inputs\.mode == 'process_existing'/,
  );
  const processExistingStart = workflow.indexOf("  process_existing:");
  const processPagesStart = workflow.indexOf("  process_pages:");
  assert.ok(processExistingStart >= 0);
  assert.ok(processPagesStart > processExistingStart);
  const backlogJob = workflow.slice(processExistingStart, processPagesStart);
  assert.match(
    backlogJob,
    /barreiras_docproc\.commands\.report_tcm_ba_document_processing/,
  );
  assert.match(
    backlogJob,
    /barreiras_docproc\.commands\.process_tcm_ba_document_families/,
  );
  assert.match(
    backlogJob,
    /barreiras_docproc\.commands\.report_tcm_ba_document_families/,
  );
  assert.match(
    backlogJob,
    /barreiras_docproc\.commands\.process_tcm_ba_commitments/,
  );
  assert.match(backlogJob, /TCM_BA_COMMITMENT_BACKLOG_APPROVED/);
  assert.doesNotMatch(
    backlogJob,
    /collect_tcm_ba_documents|SUPABASE_WORKLOAD_(?:EMAIL|PASSWORD)|SUPABASE_PUBLISHABLE_KEY/,
  );
});
test("modo de páginas processa Storage já preservado sem abrir o e-TCM", () => {
  const pagesJob = workflow.slice(workflow.indexOf("  process_pages:"));
  const textIndex = pagesJob.indexOf(
    "barreiras_docproc.commands.process_tcm_ba_documents",
  );
  const ocrIndex = pagesJob.indexOf(
    "barreiras_docproc.commands.ocr_gazette_pages",
  );
  const reportIndex = pagesJob.indexOf(
    "barreiras_docproc.commands.report_tcm_ba_document_processing",
  );
  const familyIndex = pagesJob.indexOf(
    "barreiras_docproc.commands.process_tcm_ba_document_families",
  );
  const familyCoverageIndex = pagesJob.indexOf(
    "barreiras_docproc.commands.report_tcm_ba_document_families",
  );
  const commitmentIndex = pagesJob.indexOf(
    "barreiras_docproc.commands.process_tcm_ba_commitments",
  );
  assert.match(
    pagesJob,
    /if: github\.event_name == 'workflow_dispatch' && inputs\.mode == 'process_pages'/,
  );
  assert.ok(textIndex >= 0);
  assert.ok(ocrIndex > textIndex);
  assert.ok(reportIndex > ocrIndex);
  assert.ok(familyIndex > reportIndex);
  assert.ok(familyCoverageIndex > familyIndex);
  assert.ok(commitmentIndex > familyCoverageIndex);
  assert.match(pagesJob, /TCM_BA_PRESERVED_PAGES_APPROVED/);
  assert.match(pagesJob, /MUNICIPAL_TRANSPARENCY_SUPABASE_WORKLOAD_EMAIL/);
  assert.match(pagesJob, /MUNICIPAL_TRANSPARENCY_SUPABASE_WORKLOAD_PASSWORD/);
  assert.doesNotMatch(pagesJob, /collect_tcm_ba_documents/);
});
