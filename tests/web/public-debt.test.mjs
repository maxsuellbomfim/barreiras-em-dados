import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { parseDebtStatementRows } from "../../apps/web/lib/public-debt.mjs";

const read = (path) => readFileSync(new URL(`../../${path}`, import.meta.url), "utf8");
const migration = read("supabase/migrations/20260930191230_public_debt_rgf_annex2.sql");
const page = read("apps/web/app/financas/divida/page.tsx");

const row = {
  fiscal_year: 2024,
  period: 3,
  period_end: "2024-12-31",
  consolidated_debt: "851127589.5",
  deductions: "13634624.92",
  net_consolidated_debt: "837492964.58",
  adjusted_net_current_revenue: "918218391.18",
  net_debt_revenue_percent: "91.21",
  senate_limit: "1101862069.42",
  alert_limit: "991675862.47",
  composition: [
    { code: "DividaConsolidada", account: "DÍVIDA CONSOLIDADA - DC (I)", value: "851127589.5" },
  ],
  artifact_sha256: "a".repeat(64),
  retrieved_at: "2026-09-30T18:00:00+00:00",
  source_url: "https://siconfi.tesouro.gov.br/siconfi/pages/public/consulta_finbra_rgf/finbra_rgf_list.jsf",
  methodology_version: "municipal-debt-rgf-annex2/1.0.0",
};

test("demonstrativo válido mantém valores declarados em texto e contas ausentes nulas", () => {
  const [statement] = parseDebtStatementRows([{ ...row, consolidated_debt: null }]);
  assert.equal(statement.netConsolidatedDebt, "837492964.58");
  assert.equal(statement.consolidatedDebt, null);
  assert.equal(statement.composition[0].code, "DividaConsolidada");
  assert.deepEqual(parseDebtStatementRows([]), []);
  const ordered = parseDebtStatementRows([
    { ...row, fiscal_year: 2021, period: 1 },
    row,
    { ...row, fiscal_year: 2024, period: 2 },
  ]);
  assert.deepEqual(ordered.map((s) => [s.fiscalYear, s.period]), [[2024, 3], [2024, 2], [2021, 1]]);
});

test("linha fora do contrato derruba o conjunto", () => {
  for (const broken of [
    { net_consolidated_debt: 837492964.58 },
    { net_consolidated_debt: "837.492.964,58" },
    { period: 4 },
    { artifact_sha256: "abc" },
    { composition: [{ code: "X", account: "Y", value: 1 }] },
    { methodology_version: "municipal-debt-rgf-annex2/0.9.0" },
    { source_url: "http://inseguro" },
  ]) {
    assert.equal(parseDebtStatementRows([row, { ...row, ...broken }]), null, JSON.stringify(broken));
  }
});

test("projeção devolve o valor literal da fonte, sem somar, e é pública", () => {
  assert.match(migration, /grant execute on function api\.get_public_debt_statements\(\) to anon, authenticated;/);
  assert.match(migration, /'DividaConsolidadaLiquida'/);
  assert.match(migration, /distinct on \(lines\.fiscal_year, lines\.period\)/);
  assert.doesNotMatch(migration, /sum\(/i, "a plataforma não soma a dívida");
  assert.match(migration, /'siconfi\/rgf\/'/);
});

test("página diz que falha e ausência não são dívida zero", () => {
  assert.match(page, /não significa dívida zero/);
  assert.match(page, /nunca significa dívida zero/);
  assert.match(page, /municipal-debt-rgf-annex2\/1\.0\.0/);
});
