import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const page = await readFile(
  new URL("../../apps/web/app/financas/page.tsx", import.meta.url),
  "utf8",
);

test("visão geral direciona os maiores pagamentos ao detalhe mensal", () => {
  assert.doesNotMatch(page, /getPublicExpenseLines/);
  assert.doesNotMatch(page, /FinanceExpenseLineCard/);
  assert.match(page, /monthlyFinanceHref\(latestExpenseReport\.periodStart\)/);
  assert.match(page, /Abrir o mês e ver as 25 maiores linhas pagas/);
});
