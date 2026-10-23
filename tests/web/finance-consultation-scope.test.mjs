import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import test from "node:test";
import * as financeDocuments from "../../apps/web/lib/finance-documents.ts";
import { buildFinanceFamilyCoverage } from "../../apps/web/lib/finance-family-coverage.mjs";

test("consulta vazia, parcial e indisponível têm estados separados sem perder documentos válidos", () => {
  const available = { state: "available", documents: [{ documentId: "same" }] };
  const empty = { state: "available", documents: [] };
  const failed = { state: "unavailable" };
  const state = financeDocuments.getFinanceDocumentConsultationState;
  assert.equal(typeof state, "function");
  assert.equal(state(empty), "available");
  assert.equal(state(available, empty), "available");
  assert.equal(state(available, failed), "partial");
  assert.equal(state(empty, failed), "partial");
  assert.equal(state(failed, failed), "unavailable");
  assert.equal(state(), "unavailable");
  assert.equal(financeDocuments.mergePublicFinanceDocumentResults(available, available, failed).length, 1);
});

test("indicadores descrevem apenas o recorte e mantêm acesso às evidências", async () => {
  const root = new URL("../../apps/web/app/financas/", import.meta.url);
  const map = await readFile(new URL("finance-family-coverage-map.tsx", root), "utf8");
  assert.doesNotMatch(map, /return "Nenhum período sem dado"/);
  assert.match(map, /no recorte consultado/);
  assert.match(map, /não comprova cobertura histórica completa/);
  assert.doesNotMatch(map, /Fonte ainda indisponível/);
  for (const file of ["finance-payroll-history.tsx", "finance-nonpayroll-workforce-coverage.tsx"]) {
    assert.match(await readFile(new URL(file, root), "utf8"), /neste recorte/);
  }
});

test("mapa renderizado não chama uma amostra sem lacunas de histórico completo", async () => {
  const requireWeb = createRequire(new URL("../../apps/web/package.json", import.meta.url));
  const ts = requireWeb("typescript");
  const { createElement } = requireWeb("react");
  const { renderToStaticMarkup } = requireWeb("react-dom/server");
  const source = await readFile(new URL("../../apps/web/app/financas/finance-family-coverage-map.tsx", import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
  } }).outputText;
  const mod = { exports: {} };
  new Function("require", "module", "exports", compiled)(requireWeb, mod, mod.exports);
  const html = renderToStaticMarkup(createElement(mod.exports.default, {
    families: buildFinanceFamilyCoverage({ financeRows: [
      { periodStart: "2026-09-01", coverageStatus: "complete" },
    ] }),
  }));
  assert.match(html, /Sem lacunas no recorte consultado/);
  assert.match(html, /1 de 1 registros mensais consultados/);
  assert.match(html, /não comprova cobertura histórica completa/);
  assert.match(html, /Cobertura não disponível nesta consulta/);
  assert.doesNotMatch(html, /Nenhum período sem dado|Fonte ainda indisponível/);
  assert.match(html, /\/financas\/cobertura#finance-coverage-title/);
});
