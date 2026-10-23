import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import test from "node:test";

import { buildFinanceCoverageMatrix } from "../../apps/web/lib/finance-coverage-matrix.mjs";
import { buildPayrollCoverageMatrix } from "../../apps/web/lib/payroll-coverage-matrix.mjs";
import { buildObligationCoverageMatrix } from "../../apps/web/lib/obligation-coverage-matrix.mjs";
import { buildFiscalReportCoverageMatrix } from "../../apps/web/lib/fiscal-report-coverage-matrix.mjs";
import { buildMunicipalFinanceDocumentCoverage } from "../../apps/web/lib/municipal-finance-document-coverage.mjs";
import { getPublicFinanceCoverage } from "../../apps/web/lib/finance-coverage.ts";
import { getPublicFinanceDocuments } from "../../apps/web/lib/finance-documents.ts";
import { getPublicPayrollCoverage } from "../../apps/web/lib/public-payroll.mjs";
import { getPublicObligationCoverage } from "../../apps/web/lib/public-obligations.mjs";

const finance = {
  coverageId: "finance-2025-12", fiscalYear: 2025, periodStart: "2025-12-01",
  periodEnd: "2025-12-31", publicBodyName: "Prefeitura", revenueReportCount: 1,
  expenseReportCount: 1, coverageStatus: "complete", coverageNote: "Validado.",
  calculationMethodology: "finance-coverage/1.2.0",
};
const payroll = {
  referenceMonth: "2025-12-01", coverageStatus: "published", coverageNote: "Validado.",
  catalogDocumentCount: 1, preservedDocumentCount: 1, sourceUrl: "https://barreiras.ba.gov.br/folha/",
  artifactSha256: "a".repeat(64), catalogCheckedAt: "2026-01-31T12:00:00Z",
  methodologyVersion: "payroll-coverage/1.0.0",
};
const obligation = {
  coverageId: "obligation-2025-12", fiscalYear: 2025, periodStart: "2025-12-01",
  periodEnd: "2025-12-31", coverageStatus: "published", sourceUrl: "https://barreiras.ba.gov.br/balancete.pdf",
  documentArtifactSha256: "a".repeat(64), searchEvidenceSha256: null,
  evidenceArtifactCount: null, conflictPreviousPeriodAmount: null, conflictReportedPriorAmount: null,
  conflictDifferenceAmount: null, checkedAt: "2026-01-31T12:00:00Z",
  methodologyVersion: "public-obligation-coverage/1.2.0",
};

test("calendários mensais mostram meses passados omitidos, inclusive depois da última linha recebida", () => {
  const matrices = [
    buildFinanceCoverageMatrix([finance], 2021, "2026-10").bodies[0],
    buildPayrollCoverageMatrix([payroll], 2021, "2026-10"),
    buildObligationCoverageMatrix([obligation], 2021, "2026-10"),
  ];
  for (const matrix of matrices) {
    assert.equal(matrix.years[0].year, 2026);
    assert.equal(matrix.years[0].months[0].status, "unclassified");
    assert.equal(matrix.years[0].months[8].status, "unclassified");
    assert.equal(matrix.years[0].months[9].status, "not_due");
    assert.equal(matrix.years[0].months[11].status, "not_due");
    assert.ok(["complete", "published"].includes(matrix.years[1].months[11].status));
  }
});

test("listas documentais vazias ou limitadas nunca comprovam documento não localizado", () => {
  const options = { startYear: 2021, today: "2026-10-23" };
  const fiscal = buildFiscalReportCoverageMatrix([], options);
  const monthly = buildMunicipalFinanceDocumentCoverage([], options);
  assert.equal(fiscal.years.at(-1).periods[0].status, "unclassified");
  assert.equal(monthly.years.at(-1).months[0].families[0].status, "unclassified");
  assert.equal(fiscal.years[0].periods[5].status, "not_due");
  assert.equal(monthly.years[0].months[11].families[0].status, "not_due");
  assert.equal(fiscal.years.flatMap((year) => year.periods).some((cell) => cell.status === "not_found"), false);
  assert.equal(monthly.years.flatMap((year) => year.months.flatMap((month) => month.families)).some((cell) => cell.status === "not_listed"), false);
});

test("página de calendários revela os limites e não promete cobertura completa", async () => {
  const root = new URL("../../apps/web/app/financas/", import.meta.url);
  const page = await readFile(new URL("cobertura/page.tsx", root), "utf8");
  assert.match(page, /120/);
  assert.match(page, /200/);
  assert.match(page, /não comprova.*ausência/s);
  const overview = await readFile(new URL("page.tsx", root), "utf8");
  assert.doesNotMatch(overview, /Abrir cobertura completa por período/);
  const financeUi = await readFile(new URL("finance-coverage-matrix.tsx", root), "utf8");
  assert.match(financeUi, /href="\/financas#document-title"/);
});

test("consultas mantêm limites de 120 meses/registros e 200 documentos; linha inválida não desaparece silenciosamente", async (t) => {
  const savedUrl = process.env.PUBLIC_DATA_SUPABASE_URL;
  const savedKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY;
  process.env.PUBLIC_DATA_SUPABASE_URL = "https://example.test";
  process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY = "sb_publishable_test";
  t.after(() => {
    if (savedUrl === undefined) delete process.env.PUBLIC_DATA_SUPABASE_URL;
    else process.env.PUBLIC_DATA_SUPABASE_URL = savedUrl;
    if (savedKey === undefined) delete process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY;
    else process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY = savedKey;
  });
  const requests = [];
  let payload = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    requests.push({ url, body: JSON.parse(options.body) });
    return Response.json(payload);
  });
  await getPublicFinanceCoverage();
  await getPublicPayrollCoverage();
  await getPublicObligationCoverage();
  await getPublicFinanceDocuments("rreo");
  assert.deepEqual(requests.map(({ body }) => body.page_size ?? body.month_limit), [120, 120, 120, 200]);
  payload = [null];
  assert.deepEqual(await getPublicFinanceCoverage(), { state: "unavailable" });
  payload = [{ coverage_id: "invalid" }];
  assert.deepEqual(await getPublicFinanceCoverage(), { state: "unavailable" });
});

test("calendários documentais renderizados não acusam ausência a partir de uma lista vazia", async () => {
  const requireWeb = createRequire(new URL("../../apps/web/package.json", import.meta.url));
  const ts = requireWeb("typescript");
  const { createElement } = requireWeb("react");
  const { renderToStaticMarkup } = requireWeb("react-dom/server");
  for (const [component, library] of [
    ["finance-fiscal-report-coverage-matrix", "fiscal-report-coverage-matrix"],
    ["finance-municipal-document-coverage", "municipal-finance-document-coverage"],
  ]) {
    const source = await readFile(new URL(`../../apps/web/app/financas/${component}.tsx`, import.meta.url), "utf8");
    const lib = await import(`../../apps/web/lib/${library}.mjs`);
    const compiled = ts.transpileModule(source, { compilerOptions: {
      module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
    } }).outputText;
    const mod = { exports: {} };
    new Function("require", "module", "exports", compiled)(
      (name) => name === `../../lib/${library}.mjs` ? lib : requireWeb(name), mod, mod.exports,
    );
    const html = renderToStaticMarkup(createElement(mod.exports.default, { initialResult: { state: "available", entries: [] } }));
    assert.match(html, /Não classificado/);
    assert.match(html, /200 registros/);
    assert.doesNotMatch(html, /Não localizado|vencidos não localizados|PDFs preservados/);
    assert.match(html, /tabindex="0"/);
  }
});
