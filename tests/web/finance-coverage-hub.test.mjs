import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const overview = await readFile(
  new URL("../../apps/web/app/financas/page.tsx", import.meta.url),
  "utf8",
);
const coveragePage = await readFile(
  new URL("../../apps/web/app/financas/cobertura/page.tsx", import.meta.url),
  "utf8",
);
const familyCoverage = await readFile(
  new URL("../../apps/web/lib/finance-family-coverage.mjs", import.meta.url),
  "utf8",
);
const sitemap = await readFile(
  new URL("../../apps/web/app/sitemap.ts", import.meta.url),
  "utf8",
);

test("visão geral oferece auditoria completa sem renderizar cinco matrizes", () => {
  assert.match(overview, /href="\/financas\/cobertura"/);
  assert.match(overview, /Abrir cobertura completa por período/);
  for (const component of [
    "FinanceCoverageMatrix",
    "FinancePayrollCoverageMatrix",
    "FinanceObligationCoverageMatrix",
    "FinanceMunicipalDocumentCoverage",
    "FinanceFiscalReportCoverageMatrix",
  ]) {
    assert.doesNotMatch(overview, new RegExp(`<${component}\\b`));
  }
});

test("página dedicada preserva todas as matrizes e seus estados", () => {
  assert.match(coveragePage, /export const metadata/);
  assert.match(coveragePage, /Cobertura financeira por período/);
  assert.match(coveragePage, /FinanceCoverageMatrix initialResult=\{financeCoverage\}/);
  assert.match(coveragePage, /FinancePayrollCoverageMatrix initialResult=\{payrollCoverage\}/);
  assert.match(coveragePage, /FinanceObligationCoverageMatrix initialResult=\{obligationCoverage\}/);
  assert.match(coveragePage, /FinanceMunicipalDocumentCoverage initialResult=\{municipalDocumentCoverage\}/);
  assert.match(coveragePage, /FinanceFiscalReportCoverageMatrix initialResult=\{fiscalCoverage\}/);
});

test("mapa de fontes aponta para a página dedicada", () => {
  assert.match(familyCoverage, /href: "\/financas\/cobertura#finance-coverage-title"/);
  assert.match(familyCoverage, /href: "\/financas\/cobertura#obligation-matrix-title"/);
  assert.match(familyCoverage, /href: "\/financas\/cobertura#payroll-matrix-title"/);
  assert.match(familyCoverage, /href: "\/financas\/cobertura#fiscal-report-coverage-title"/);
  assert.match(sitemap, /route: "\/financas\/cobertura"/);
});
