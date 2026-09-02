import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const coveragePage = await readFile(
  new URL("../../apps/web/app/financas/cobertura/page.tsx", import.meta.url),
  "utf8",
);
const component = await readFile(
  new URL(
    "../../apps/web/app/financas/finance-municipal-document-coverage.tsx",
    import.meta.url,
  ),
  "utf8",
);
const route = await readFile(
  new URL(
    "../../apps/web/app/api/municipal-finance-document-coverage/route.ts",
    import.meta.url,
  ),
  "utf8",
);
const loader = await readFile(
  new URL(
    "../../apps/web/lib/finance-document-coverage-results.ts",
    import.meta.url,
  ),
  "utf8",
);
const styles = await readFile(
  new URL("../../apps/web/app/globals.css", import.meta.url),
  "utf8",
);

test("página consulta as três famílias separadamente e publica a matriz mensal", () => {
  assert.match(loader, /getPublicFinanceDocuments\("balancetes"\)/);
  assert.match(loader, /getPublicFinanceDocuments\("pdc-resumo-execucao-da-receita"\)/);
  assert.match(loader, /getPublicFinanceDocuments\("pdc-resumo-execucao-da-despesa"\)/);
  assert.match(coveragePage, /<FinanceMunicipalDocumentCoverage initialResult=\{municipalDocumentCoverage\} \/>/);
  assert.match(coveragePage, /Balancete, receita e despesa por competência/);
});

test("matriz explica ausência, versões e preservação sem chamar lacuna de zero", () => {
  assert.match(component, /Não localizado no catálogo preservado consultado/);
  assert.match(component, /não significa valor zero/i);
  assert.match(component, /evidenceCount > 1/);
  assert.match(component, /versões/);
  assert.match(component, /documento oficial/);
});

test("rota de recuperação exige sucesso das três consultas antes de classificar lacunas", () => {
  assert.match(route, /getPublicMunicipalFinanceDocumentCoverageResult\(\)/);
  assert.match(loader, /results\.some\(\(result\) => result\.state !== "available"\)/);
  assert.match(route, /status: result\.state === "available" \? 200 : 503/);
});

test("matrizes podem encolher no grid e mantêm tabelas largas na rolagem local", () => {
  assert.match(styles, /\.finance-coverage-matrix\s*\{[^}]*min-width:\s*0/s);
  assert.match(styles, /\.finance-coverage-table-scroll\s*\{[^}]*overflow-x:\s*auto/s);
  assert.match(styles, /\.finance-municipal-document-table table\s*\{[^}]*min-width:\s*38rem/s);
});
