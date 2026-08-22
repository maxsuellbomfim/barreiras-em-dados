import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pageUrl = new URL(
  "../../apps/web/app/financas/[competencia]/page.tsx",
  import.meta.url,
);
const componentUrl = new URL(
  "../../apps/web/app/financas/finance-expense-category-summary.tsx",
  import.meta.url,
);

test("competência consulta categorias somente para o relatório mensal exato", async () => {
  const page = await readFile(pageUrl, "utf8");
  assert.match(page, /getPublicExpenseCategorySummary\(expenseReportId\)/);
  assert.match(page, /FinanceExpenseCategorySummary/);
  assert.doesNotMatch(page, /reduce\s*\([^)]*paidPeriodAmount/);
});

test("resumo explica universo completo, estágios e conflito de reconciliação", async () => {
  const component = await readFile(componentUrl, "utf8");
  assert.match(component, /todas as linhas contábeis do relatório/iu);
  assert.match(component, /não são pagamentos individuais/iu);
  assert.match(component, /não somou\s+empenho, liquidação e pagamento/iu);
  assert.match(component, /não\s+coincide com o total pago/iu);
  assert.match(component, /paidSharePercent/);
  assert.match(component, /classifyExpenseDescription/);
});

test("resumo prioriza oito categorias e recolhe o restante sem omitir dados", async () => {
  const component = await readFile(componentUrl, "utf8");
  assert.match(component, /const PRIMARY_CATEGORY_COUNT = 8/);
  assert.match(component, /slice\(0, PRIMARY_CATEGORY_COUNT\)/);
  assert.match(component, /slice\(PRIMARY_CATEGORY_COUNT\)/);
  assert.match(component, /<details className="finance-category-more">/);
  assert.match(component, /Ver outras.*categorias/);
});
