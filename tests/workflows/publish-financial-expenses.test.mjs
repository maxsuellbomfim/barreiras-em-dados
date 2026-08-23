import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workflow = await readFile(
  new URL(
    "../../.github/workflows/publish-financial-expenses.yml",
    import.meta.url,
  ),
  "utf8",
);

test("workflow de despesas usa o publicador versionado e limite seguro", () => {
  assert.match(workflow, /publish_expense_reports/);
  assert.match(workflow, /publish_public_obligations/);
  assert.match(workflow, /publish_payroll_reports/);
  assert.match(workflow, /publish_payroll_regime_breakdowns/);
  assert.match(workflow, /publish_payroll_compensation_distributions/);
  assert.match(workflow, /default: "5"/);
  assert.match(workflow, /timeout-minutes: 120/);
  assert.match(workflow, /--fiscal-year-from/);
  assert.match(workflow, /--fiscal-year-to/);
  assert.match(workflow, /--limit/);
  assert.match(workflow, /QUERIDO_DIARIO_DATABASE_URL/);
  assert.match(workflow, /MUNICIPAL_TRANSPARENCY_SUPABASE_WORKLOAD_PASSWORD/);
  assert.match(workflow, /PERSISTENCE_MODE: postgres-supabase/);
  assert.match(workflow, /tesseract-ocr-por/);
  assert.match(workflow, /\[postgres,storage,pdf,ocr\]/);
  assert.match(workflow, /dry_run_public_obligations:/);
  assert.match(workflow, /inputs\.dry_run_public_obligations != true/);
  assert.match(workflow, /--dry-run/);
  const expenseStep = workflow.slice(
    workflow.indexOf("- name: Publicar janela de despesas"),
    workflow.indexOf("- name: Publicar pagamentos de restos a pagar"),
  );
  assert.match(expenseStep, /limit="\$\{INPUT_LIMIT:-5\}"/);
});

test("workflow permite publicar despesas, restos a pagar ou folha", () => {
  assert.match(workflow, /publication_scope:/);
  assert.match(workflow, /- "all"/);
  assert.match(workflow, /- "expenses"/);
  assert.match(workflow, /- "public-obligations"/);
  assert.match(workflow, /- "payroll"/);
  assert.match(
    workflow,
    /inputs\.publication_scope != 'public-obligations'/,
  );
  assert.match(workflow, /inputs\.publication_scope != 'expenses'/);
  assert.match(workflow, /inputs\.publication_scope != 'payroll'/);
});

test("workflow permite direcionar restos a pagar para um mes exato", () => {
  assert.match(workflow, /reference_month:/);
  assert.match(workflow, /INPUT_REFERENCE_MONTH: \$\{\{ inputs\.reference_month \}\}/);
  assert.match(workflow, /if \[\[ -n "\$\{INPUT_REFERENCE_MONTH:-\}" \]\]/);
  assert.match(workflow, /extra_args\+=\(--reference-month "\$INPUT_REFERENCE_MONTH"\)/);
});

test("workflow permite direcionar a folha para uma competencia exata", () => {
  const payrollStep = workflow.slice(
    workflow.indexOf("- name: Publicar totais mensais validados da folha"),
  );
  assert.match(workflow, /payroll_reference_month:/);
  assert.match(
    payrollStep,
    /INPUT_PAYROLL_REFERENCE_MONTH: \$\{\{ inputs\.payroll_reference_month \}\}/,
  );
  assert.match(
    payrollStep,
    /if \[\[ -n "\$\{INPUT_PAYROLL_REFERENCE_MONTH:-\}" \]\]/,
  );
  assert.match(
    payrollStep,
    /extra_args\+=\(--reference-month "\$INPUT_PAYROLL_REFERENCE_MONTH"\)/,
  );
  assert.match(payrollStep, /--require-complete-month/);
  assert.match(payrollStep, /publish_payroll_regime_breakdowns/);
});
