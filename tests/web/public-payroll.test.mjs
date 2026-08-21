import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { parsePublicPayrollRow } from "../../apps/web/lib/public-payroll.mjs";

const validRow = {
  reference_month: "2026-07-01",
  public_body_name: "Prefeitura Municipal de Barreiras",
  employee_count: 8184,
  gross_amount: 34971971.48,
  deduction_amount: 10422982.78,
  net_amount: 24548988.7,
  subtotal_count: 133,
  source_url:
    "https://barreiras.mtransparente.com.br/admin/data/folha-julho.pdf",
  artifact_sha256:
    "411cd4f055f0e57cd1b0bc111683798ae0b28d84b7d6013d069cc9ca2a3ed0e8",
  source_retrieved_at: "2026-08-21T13:47:57.202502-03:00",
  parser_version: "payroll-report-aggregate/1.0.0",
};

test("folha publica normaliza centavos e conserva somente totais", () => {
  const row = parsePublicPayrollRow(validRow);

  assert.ok(row);
  assert.equal(row.referenceMonth, "2026-07-01");
  assert.equal(row.employeeCount, 8184);
  assert.equal(row.grossAmount, "34971971.48");
  assert.equal(row.deductionAmount, "10422982.78");
  assert.equal(row.netAmount, "24548988.70");
  assert.equal(row.subtotalCount, 133);
  assert.equal("people" in row, false);
  assert.equal("cpf" in row, false);
  assert.equal("individualDeductions" in row, false);
});

test("folha publica recusa total que nao fecha deterministicamente", () => {
  assert.equal(parsePublicPayrollRow({ ...validRow, net_amount: 1 }), null);
});

test("folha publica recusa origem, hash ou parser inesperado", () => {
  assert.equal(parsePublicPayrollRow({ ...validRow, source_url: "http://inseguro" }), null);
  assert.equal(parsePublicPayrollRow({ ...validRow, artifact_sha256: "abc" }), null);
  assert.equal(parsePublicPayrollRow({ ...validRow, parser_version: "outro" }), null);
});

test("pagina explica vínculos, descontos e limite da informação", async () => {
  const page = await readFile(
    new URL("../../apps/web/app/financas/page.tsx", import.meta.url),
    "utf8",
  );

  assert.match(page, /Quanto custa a folha da Prefeitura/);
  assert.match(page, /Um vínculo não representa necessariamente uma pessoa única/);
  assert.match(page, /não é confirmação bancária/);
  assert.match(page, /não usa IA para calcular esses valores/);
  assert.match(page, /Abrir PDF oficial/);
});

test("pagina mantém o mês mais recente em destaque e recolhe o histórico", async () => {
  const [page, history] = await Promise.all([
    readFile(
      new URL("../../apps/web/app/financas/page.tsx", import.meta.url),
      "utf8",
    ),
    readFile(
      new URL(
        "../../apps/web/app/financas/finance-payroll-history.tsx",
        import.meta.url,
      ),
      "utf8",
    ),
  ]);

  assert.match(page, /const previousPayrollMonths = payrollMonths\.slice\(1\)/);
  assert.match(page, /<FinancePayrollHistory months=\{previousPayrollMonths\}/);
  assert.match(history, /Ver meses anteriores da folha/);
  assert.match(history, /months\.map/);
  assert.match(history, /Abrir PDF oficial deste mês/);
  assert.match(history, /Mês validado por código/);
});
