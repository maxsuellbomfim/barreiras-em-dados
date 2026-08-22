import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pageUrl = new URL("../../apps/web/app/financas/page.tsx", import.meta.url);
const componentUrl = new URL(
  "../../apps/web/app/financas/finance-annual-summary.tsx",
  import.meta.url,
);

test("página resume os fechamentos já publicados sem recalcular no JSX", async () => {
  const page = await readFile(pageUrl, "utf8");
  assert.match(page, /summarizeAnnualFinances\(sortedMonthlyClosures\)/);
  assert.match(page, /FinanceAnnualSummary/);
  assert.doesNotMatch(page, /reduce\s*\([^)]*revenueReportAmount/);
});

test("quadro anual explicita meses incluídos e proíbe comparação enganosa", async () => {
  const component = await readFile(componentUrl, "utf8");
  assert.match(component, /meses reconciliados/iu);
  assert.match(component, /Ano completo/iu);
  assert.match(component, /Recorte parcial/iu);
  assert.match(component, /não compare anos com coberturas diferentes/iu);
  assert.match(component, /Nenhuma IA calculou/iu);
});
