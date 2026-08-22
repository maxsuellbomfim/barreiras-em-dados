import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workflow = await readFile(
  new URL("../../.github/workflows/backfill-payroll.yml", import.meta.url),
  "utf8",
);

test("backfill da folha limita e valida a janela antes de acessar fontes", () => {
  assert.match(workflow, /start_month:/);
  assert.match(workflow, /end_month:/);
  assert.match(workflow, /max_months:[\s\S]*- "6"/);
  assert.match(workflow, /Validar janela mensal/);
  assert.match(
    workflow,
    /barreiras_collectors\.commands\.plan_payroll_backfill/,
  );
  assert.match(workflow, /--github-output "\$GITHUB_OUTPUT"/);
  assert.match(workflow, /jobs:\s*\n\s+plan:/);
  assert.match(workflow, /months: \$\{\{ steps\.window\.outputs\.months \}\}/);
});

test("coleta e publicação usam filas distintas e sequenciais", () => {
  assert.match(
    workflow,
    /collect:[\s\S]*concurrency:\s*\n\s+group: municipal-finance-collection-production/,
  );
  assert.match(
    workflow,
    /publish:[\s\S]*needs: \[plan, collect\][\s\S]*concurrency:\s*\n\s+group: municipal-finance-publication-production/,
  );
});

test("credenciais ficam limitadas aos passos que acessam dados", () => {
  const globalEnvironment = workflow.slice(
    workflow.indexOf("env:"),
    workflow.indexOf("jobs:"),
  );
  assert.doesNotMatch(globalEnvironment, /DATABASE_URL|WORKLOAD_PASSWORD/);
  assert.match(workflow, /QUERIDO_DIARIO_DATABASE_URL/);
  assert.match(workflow, /MUNICIPAL_TRANSPARENCY_SUPABASE_WORKLOAD_EMAIL/);
  assert.match(workflow, /MUNICIPAL_TRANSPARENCY_SUPABASE_WORKLOAD_PASSWORD/);
  assert.match(workflow, /SUPABASE_RAW_ARTIFACTS_BUCKET: raw-artifacts/);
});

test("cada competencia preserva somente folha regular e publica depois", () => {
  const collectIndex = workflow.indexOf(
    "barreiras_collectors.commands.collect_municipal_transparency",
  );
  const publishIndex = workflow.indexOf(
    "barreiras_normalization.commands.publish_payroll_reports",
  );

  assert.ok(collectIndex >= 0);
  assert.ok(publishIndex > collectIndex);
  assert.match(workflow, /--resource servidores/);
  assert.match(workflow, /--document-reference-month "\$month"/);
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
  assert.match(workflow, /--max-pages 20/);
  assert.match(workflow, /--max-documents 20/);
  assert.match(workflow, /--require-document-match/);
  assert.match(workflow, /--reference-month "\$month"/);
  assert.match(workflow, /--require-complete-month/);
  assert.match(workflow, /--limit 20/);
  assert.match(workflow, /set -euo pipefail/);
  assert.doesNotMatch(workflow, /--allow-partial/);
});

test("ausencia comprovada de folha regular nao interrompe os demais meses", () => {
  assert.match(workflow, /id: collect_months/);
  assert.match(workflow, /missing_months: \$\{\{ steps\.collect_months\.outputs\.missing_months \}\}/);
  assert.match(workflow, /pipeline_status=\("\$\{PIPESTATUS\[@\]\}"\)/);
  assert.match(workflow, /collector_status="\$\{pipeline_status\[0\]\}"/);
  assert.match(workflow, /tee_status="\$\{pipeline_status\[1\]\}"/);
  assert.match(workflow, /if \[\[ "\$tee_status" -ne 0 \]\]; then/);
  assert.match(workflow, /Falha ao preservar o log operacional/);
  assert.match(workflow, /if \[\[ "\$collector_status" -eq 3 \]\]; then/);
  assert.match(workflow, /missing_months="\$\{missing_months\}\$\{missing_months:\+ \}\$month"/);
  assert.match(workflow, /echo "missing_months=\$missing_months" >> "\$GITHUB_OUTPUT"/);
  assert.match(workflow, /MISSING_MONTHS: \$\{\{ needs\.collect\.outputs\.missing_months \}\}/);
  assert.match(workflow, /if \[\[ " \$MISSING_MONTHS " == \*" \$month "\* \]\]; then/);
  assert.match(workflow, /Sem folha regular localizada na fonte para \$month/);
  assert.doesNotMatch(workflow, /continue-on-error:/);
});

test("resumo permanece visível mas falha junto com qualquer etapa obrigatória", () => {
  assert.match(workflow, /if: \$\{\{ always\(\) \}\}/);
  assert.match(workflow, /\$PLAN_RESULT" != "success"/);
  assert.match(workflow, /\$COLLECT_RESULT" != "success"/);
  assert.match(workflow, /\$PUBLISH_RESULT" != "success"/);
  assert.match(workflow, /MISSING_MONTHS:/);
  assert.match(workflow, /Compet\u00eancias sem folha regular localizada:/);
  assert.match(workflow, /exit 1/);
});

test("workflow não recebe segredos nem valores financeiros por input", () => {
  assert.doesNotMatch(workflow, /DATABASE_URL:\s*\$\{\{ inputs\./);
  assert.doesNotMatch(workflow, /SUPABASE[^\n]*:\s*\$\{\{ inputs\./);
  assert.doesNotMatch(workflow, /gross_amount:|net_amount:|deduction_amount:/);
});
