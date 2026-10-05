import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  parsePayrollWithholdingRows,
  withholdingYear,
} from "../../apps/web/lib/payroll-withholdings.mjs";

const read = (path) => readFileSync(new URL(`../../${path}`, import.meta.url), "utf8");
const migration = read("supabase/migrations/20261005135303_public_payroll_withholdings.sql");
const page = read("apps/web/app/financas/retencoes/page.tsx");

const row = {
  creditor_name: "BANCO SANTANDER",
  commitments: 2,
  amount: "800.00",
  reversal_amount: "-200.00",
  first_commitment_date: "2025-07-10",
  last_commitment_date: "2025-07-11",
  latest_commitment_key: "E-2",
  grid_artifact_sha256: "a".repeat(64),
  year_commitments: 3,
  year_amount: "1150.00",
  year_reversal_amount: "-200.00",
  year_grid_months: 12,
  year_linked_payments: 0,
  year_months: [{ month: "2025-07", commitments: 3, amount: "1150.00" }],
  source_page_url: "https://portaldatransparencia.barreiras.ba.gov.br/despesas-geral",
  methodology_version: "municipal-payroll-withholdings/1.0.0",
};

test("retenções: lê credor nomeado e linha agregada sem nome", () => {
  const parsed = parsePayrollWithholdingRows([
    row,
    { ...row, creditor_name: null, commitments: 1, amount: "350.00", reversal_amount: "0.00" },
  ]);
  assert.equal(parsed.creditors[0].creditorName, "BANCO SANTANDER");
  assert.equal(parsed.creditors[1].creditorName, null);
  assert.equal(parsed.summary.amount, "1150.00");
  assert.equal(parsed.summary.linkedPayments, 0);
  assert.deepEqual(parsed.summary.months, [
    { month: "2025-07", commitments: 3, amount: "1150.00" },
  ]);
});

test("retenções: linha inválida derruba o conjunto", () => {
  for (const broken of [
    { amount: "800" },
    { amount: 800 },
    { creditor_name: "  " },
    { latest_commitment_key: "O-2" },
    { grid_artifact_sha256: "abc" },
    { year_linked_payments: null },
    { year_months: [{ month: "julho", commitments: 1, amount: "1.00" }] },
    { year_months: null },
    { methodology_version: "municipal-payroll-withholdings/2.0.0" },
    { source_page_url: "http://inseguro" },
  ]) {
    assert.equal(parsePayrollWithholdingRows([{ ...row, ...broken }]), null, JSON.stringify(broken));
  }
  assert.equal(parsePayrollWithholdingRows(null), null);
  assert.deepEqual(parsePayrollWithholdingRows([]), { summary: null, creditors: [] });
});

test("retenções: ano fora da faixa volta ao ano corrente", () => {
  assert.equal(withholdingYear("2025", 2026), 2025);
  assert.equal(withholdingYear("2023", 2026), 2026);
  assert.equal(withholdingYear("2027", 2026), 2026);
  assert.equal(withholdingYear(undefined, 2026), 2026);
});

test("retenções: pensão e pessoa física nunca saem com nome nem histórico", () => {
  assert.match(migration, /payload ->> 'field1144634' !~\* 'pens\[ãa\]o'/);
  assert.match(migration, /finance\.payment_creditor_is_entity_v1/);
  assert.doesNotMatch(migration, /description|field1144634' as/);
  assert.doesNotMatch(page, /\.(history|description)\b|field1144634/);
  assert.match(page, /nomes não publicados/);
});

test("retenções: falha de consulta não vira zero e empenho não vira repasse", () => {
  assert.match(page, /não significa que não haja retenções/);
  assert.match(page, /Empenho é a reserva do valor, não o repasse/);
  assert.match(page, /se e quando cada repasse foi feito/);
});
