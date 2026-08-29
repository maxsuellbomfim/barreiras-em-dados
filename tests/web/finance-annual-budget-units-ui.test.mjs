import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pagePath = new URL("../../apps/web/app/financas/ano/[ano]/page.tsx", import.meta.url);
const componentPath = new URL(
  "../../apps/web/app/financas/ano/[ano]/finance-annual-budget-units.tsx",
  import.meta.url,
);

test("página anual consulta e agrega unidades para os mesmos relatórios comparáveis", async () => {
  const page = await readFile(pagePath, "utf8");
  assert.match(page, /getPublicExpenseBudgetUnitSummary/);
  assert.match(page, /buildAnnualExpenseBudgetUnits/);
  assert.match(page, /<FinanceAnnualBudgetUnits result=\{annualBudgetUnits\}/);
});

test("UI explica unidade contábil, prioriza oito e recolhe o restante", async () => {
  const component = await readFile(componentPath, "utf8");
  assert.match(component, /Pagamentos por unidade orçamentária/);
  assert.match(component, /unidade orçamentária[\s\S]*não significa que o titular[\s\S]*gastou/i);
  assert.match(component, /slice\(0, PRIMARY_UNIT_COUNT\)/);
  assert.match(component, /<details className="finance-annual-category-more">/);
  assert.match(component, /Mês sem atribuição integral não foi convertido em zero/);
  assert.match(component, /Abrir balancete oficial/);
  assert.match(component, /IA não calcula valores/);
  assert.match(component, /não identifica empenhos individuais/i);
  assert.match(component, /não liga esta unidade\s+a contratos ou fornecedores/i);
  assert.match(component, /número oficial do empenho/i);
});
