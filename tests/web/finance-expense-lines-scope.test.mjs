import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const page = await readFile(
  new URL("../../apps/web/app/financas/page.tsx", import.meta.url),
  "utf8",
);

test("maiores pagamentos usam somente o relatório mensal em destaque", () => {
  assert.match(
    page,
    /getPublicExpenseLines\(latestExpenseReport\.expenseReportId, 25\)/,
  );
  assert.doesNotMatch(page, /getPublicExpenseLines\(\)/);
  assert.match(page, /Linhas do relatório oficial de/);
});
