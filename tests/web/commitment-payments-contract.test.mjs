import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  groupPaymentsByCommitment,
  parseCommitmentPaymentRows,
} from "../../apps/web/lib/commitment-payments.mjs";

const read = (path) => readFileSync(new URL(`../../${path}`, import.meta.url), "utf8");
const migration = read(
  "supabase/migrations/20260924094933_public_commitment_payments.sql",
);
const sqlBody = migration.replace(/--[^\n]*/g, "");
const page = read("apps/web/app/licitacoes/page.tsx");

const row = {
  commitment_key: "O-250790",
  payment_id: "355674",
  payment_date_text: "29/08/2026",
  amount_text: "45158,26",
  process_number: "630",
  contract_text: "014/2025CM",
  grid_artifact_sha256: "c".repeat(64),
  grid_month: "2026-08",
  methodology_version: "commitment-payments/1.0.0",
};

test("pagamentos só entram com chave, identificador, data e grade válidos", () => {
  const [parsed] = parseCommitmentPaymentRows([row]);
  assert.equal(parsed.paymentId, "355674");
  assert.equal(parsed.processNumber, "630");
  const [withoutContract] = parseCommitmentPaymentRows([
    { ...row, contract_text: null, process_number: null },
  ]);
  assert.equal(withoutContract.contractText, null);
  for (const broken of [
    { commitment_key: "E-1" },
    { payment_id: "abc" },
    { payment_date_text: "2026-08-29" },
    { methodology_version: "commitment-payments/0.1.0" },
  ]) {
    assert.equal(parseCommitmentPaymentRows([{ ...row, ...broken }]), null);
  }
  const grouped = groupPaymentsByCommitment(
    parseCommitmentPaymentRows([row, { ...row, payment_id: "355675" }]),
  );
  assert.equal(grouped.get("O-250790").length, 2);
});

test("a projeção parte das chaves, usa a grade mais recente e não soma", () => {
  assert.match(sqlBody, /with candidates as materialized \(/);
  assert.ok(sqlBody.indexOf("candidates as materialized") < sqlBody.indexOf("latest_grids as ("));
  assert.match(sqlBody, /record\.payload ->> 'field1082596' = any\(commitment_keys\)/);
  assert.match(sqlBody, /where metadata ->> 'schema_name' = 'municipal-payments-webrun-grid';/);
  assert.match(sqlBody, /cardinality\(commitment_keys\) > 500/);
  assert.doesNotMatch(sqlBody, /\bsum\(/i);
  assert.match(migration, /to anon, authenticated;/);
});

test("a página mostra pagamentos sem confundir indisponível com zero", () => {
  assert.match(page, /getPaymentsForCommitments\(linkedCommitmentKeys\)/);
  assert.match(page, /Pagamentos indisponíveis nesta consulta/);
  assert.match(page, /Nenhum pagamento deste empenho nos meses já coletados/);
  assert.match(page, /empenhado, liquidado e pago são estágios\s+distintos e nunca se somam/);
});
