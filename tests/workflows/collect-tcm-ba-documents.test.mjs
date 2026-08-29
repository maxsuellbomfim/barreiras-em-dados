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
  const approveIndex = workflow.indexOf("TCM_BA_DOCUMENT_PILOT_APPROVED");
  assert.ok(collectIndex >= 0);
  assert.ok(auditIndex > collectIndex);
  assert.ok(textIndex > auditIndex);
  assert.ok(ocrIndex > textIndex);
  assert.ok(reportIndex > ocrIndex);
  assert.ok(approveIndex > reportIndex);
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
