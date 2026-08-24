import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pagePath = new URL(
  "../../apps/web/app/financas/ano/[ano]/page.tsx",
  import.meta.url,
);
const componentPath = new URL(
  "../../apps/web/app/financas/ano/[ano]/finance-year-siconfi.tsx",
  import.meta.url,
);

test("página anual consulta DCA e reconciliação determinística do mesmo exercício", async () => {
  const page = await readFile(pagePath, "utf8");
  assert.match(page, /getPublicSiconfiAnnualTotals\(\)/);
  assert.match(page, /getPublicSiconfiMonthlyReconciliation\(\)/);
  assert.match(page, /year\.fiscalYear === fiscalYear/);
  assert.match(page, /<FinanceYearSiconfi/);
});

test("detalhe anual explica ausência, diferença e evidência sem acusação", async () => {
  const component = await readFile(componentPath, "utf8");
  assert.match(component, /DCA de \{fiscalYear\} ainda não localizada/);
  assert.match(component, /Isso não significa receita ou despesa zero/);
  assert.match(component, /A soma dos meses confere com o ano/);
  assert.match(component, /Diferença entre fontes não prova irregularidade/);
  assert.match(component, /Receita não é[\s\S]*comparada/);
  assert.match(component, /Conferência mensal ainda não disponível/);
  assert.match(component, /não significa que os valores conferem/);
  assert.match(component, /Nenhuma IA somou ou comparou valores/);
  assert.doesNotMatch(component, /corrupção|fraude/i);
});
