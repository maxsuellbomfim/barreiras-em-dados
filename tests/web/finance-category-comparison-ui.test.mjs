import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pageUrl = new URL(
  "../../apps/web/app/financas/[competencia]/page.tsx",
  import.meta.url,
);
const componentUrl = new URL(
  "../../apps/web/app/financas/finance-expense-month-comparison.tsx",
  import.meta.url,
);

test("página compara somente o mês imediatamente anterior com resumo reconciliado", async () => {
  const page = await readFile(pageUrl, "utf8");
  assert.match(page, /previousMonthStart\(detail\.periodStart\)/);
  assert.match(page, /compareExpenseCategoryMonths/);
  assert.match(page, /FinanceExpenseMonthComparison/);
});

test("comparação explica variação e não converte categoria ausente em zero", async () => {
  const component = await readFile(componentUrl, "utf8");
  assert.match(component, /mês imediatamente\s+anterior/iu);
  assert.match(component, /não foi localizada no relatório anterior/iu);
  assert.match(component, /Nenhuma IA calculou/iu);
  assert.match(component, /Ver as contas de/iu);
});
