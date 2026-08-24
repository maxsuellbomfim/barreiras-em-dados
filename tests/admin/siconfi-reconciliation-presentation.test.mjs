import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const presentation = await import(
  "../../apps/admin/app/siconfi-reconciliation.mjs"
).catch(() => null);
const page = await readFile(
  new URL("../../apps/admin/app/page.tsx", import.meta.url),
  "utf8",
);
const panel = await readFile(
  new URL(
    "../../apps/admin/app/siconfi-reconciliation-panel.tsx",
    import.meta.url,
  ),
  "utf8",
);

const rows = [
  {
    fiscal_year: 2025,
    metric_key: "expense_committed",
    annual_amount: "1004522893.76",
    monthly_sum_amount: "1004522893.76",
    difference_amount: "0.00",
    observed_months: 12,
    missing_months: [],
    reconciliation_status: "matched_exact",
    reconciliation_note: "Os totais conferem exatamente.",
    methodology_version: "siconfi-monthly-reconciliation/1.0.0",
  },
  {
    fiscal_year: 2025,
    metric_key: "expense_liquidated",
    annual_amount: "990006209.71",
    monthly_sum_amount: "990003399.60",
    difference_amount: "2810.11",
    observed_months: 12,
    missing_months: [],
    reconciliation_status: "source_difference",
    reconciliation_note: "As fontes oficiais divergem.",
    methodology_version: "siconfi-monthly-reconciliation/1.0.0",
  },
  {
    fiscal_year: 2025,
    metric_key: "expense_paid",
    annual_amount: "950096510.57",
    monthly_sum_amount: null,
    difference_amount: null,
    observed_months: 11,
    missing_months: [4],
    reconciliation_status: "incomplete_months",
    reconciliation_note: "Abril ainda não foi publicado.",
    methodology_version: "siconfi-monthly-reconciliation/1.0.0",
  },
];

test("painel administrativo possui um contrato executável para a reconciliação", () => {
  assert.ok(presentation, "módulo administrativo de reconciliação ainda não existe");
});

test("resume concordâncias, diferenças e lacunas sem recalcular valores", () => {
  assert.ok(presentation);
  const years = presentation.parseAdminSiconfiReconciliation(rows);
  assert.ok(years);
  assert.deepEqual(presentation.summarizeAdminSiconfiReconciliation(years), {
    years: 1,
    exactMatches: 1,
    sourceDifferences: 1,
    incompleteMetrics: 1,
  });
});

test("falha fechada quando o payload financeiro contradiz o contrato", () => {
  assert.ok(presentation);
  const invalid = rows.map((row) => ({ ...row }));
  invalid[2].monthly_sum_amount = "123.45";
  assert.equal(presentation.parseAdminSiconfiReconciliation(invalid), null);
});

test("painel carrega a RPC e mantém a ressalva editorial", () => {
  assert.match(page, /get_public_siconfi_monthly_reconciliation/);
  assert.match(page, /SiconfiReconciliationPanel/);
  assert.match(panel, /Diferença entre fontes não é prova de irregularidade/);
});
