import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const page = await readFile(
  new URL("../../apps/web/app/financas/page.tsx", import.meta.url),
  "utf8",
);

test("visão geral limita listas extensas sem reduzir contagens nem acesso à cobertura", () => {
  assert.match(page, /const FINANCE_OVERVIEW_LIMIT = 6;/);
  assert.match(
    page,
    /const recentExpenseReports = sortedExpenseReports\.slice\(0, FINANCE_OVERVIEW_LIMIT\);/,
  );
  assert.match(
    page,
    /const recentRevenues = sortedRevenues\.slice\(0, FINANCE_OVERVIEW_LIMIT\);/,
  );
  assert.match(
    page,
    /const recentMonthlyClosures = sortedMonthlyClosures\.slice\(0, FINANCE_OVERVIEW_LIMIT\);/,
  );
  assert.match(
    page,
    /const recentFinanceSignals = financeSignals\.slice\(0, FINANCE_OVERVIEW_LIMIT\);/,
  );
  assert.match(
    page,
    /const recentPublicObligations = publicObligations\.slice\(0, FINANCE_OVERVIEW_LIMIT\);/,
  );
  assert.match(
    page,
    /const previousPayrollMonths = payrollMonths\.slice\(1, FINANCE_OVERVIEW_LIMIT \+ 1\);/,
  );

  for (const fullList of [
    "sortedExpenseReports",
    "sortedRevenues",
    "sortedMonthlyClosures",
    "financeSignals",
    "publicObligations",
  ]) {
    assert.doesNotMatch(page, new RegExp(`\\{${fullList}\\.map\\(`));
  }

  assert.match(page, /href="\/financas\/cobertura"/);
  assert.match(page, /href="\/financas\/cobertura#payroll-matrix-title"/);
  assert.match(page, /href="\/financas\/cobertura#obligation-matrix-title"/);
  assert.doesNotMatch(page, /<FinanceCoverageMatrix\b/);
  assert.doesNotMatch(page, /<FinancePayrollCoverageMatrix\b/);
  assert.doesNotMatch(page, /<FinancePayrollCoverage\b/);
  assert.doesNotMatch(page, /obligationCoverageGaps\.map/);
  assert.match(page, /de um total de \{sortedExpenseReports\.length/);
  assert.match(page, /de um total de \{sortedRevenues\.length/);
  assert.match(page, /recentPublicObligations\.length\.toLocaleString/);
  assert.match(page, /recentObligationDocuments\.length\.toLocaleString/);
  assert.match(page, /recentFiscalDocuments\.length\.toLocaleString/);
});
