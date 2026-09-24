import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  groupLiquidationsByCommitment,
  parseCommitmentLiquidationRows,
} from "../../apps/web/lib/commitment-liquidations.mjs";

const read = (path) => readFileSync(new URL(`../../${path}`, import.meta.url), "utf8");
const migration = read(
  "supabase/migrations/20260924023520_public_commitment_liquidations.sql",
);
const sqlBody = migration.replace(/--[^\n]*/g, "");
const page = read("apps/web/app/licitacoes/page.tsx");

const row = {
  commitment_key: "O-250959",
  liquidation_date_text: "31/08/2026",
  amount_text: "1021,27",
  grid_artifact_sha256: "b".repeat(64),
  grid_month: "2026-08",
  methodology_version: "commitment-liquidations/1.0.0",
};

test("liquidações só entram com chave orçamentária, data e grade válidas", () => {
  const [parsed] = parseCommitmentLiquidationRows([row]);
  assert.equal(parsed.amountText, "1021,27");
  for (const broken of [
    { commitment_key: "E-1" },
    { liquidation_date_text: "2026-08-31" },
    { grid_month: "08/2026" },
    { methodology_version: "commitment-liquidations/0.1.0" },
  ]) {
    assert.equal(parseCommitmentLiquidationRows([{ ...row, ...broken }]), null);
  }
  const grouped = groupLiquidationsByCommitment(
    parseCommitmentLiquidationRows([row, { ...row, amount_text: "10" }]),
  );
  assert.equal(grouped.get("O-250959").length, 2);
});

test("a projeção usa a chave oficial, a grade mais recente do mês e não soma", () => {
  assert.match(sqlBody, /record\.payload ->> 'field1089487' = any\(commitment_keys\)/);
  assert.match(sqlBody, /distinct on \(artifact\.metadata -> 'cursor' ->> 'month'\)/);
  assert.match(sqlBody, /artifact\.retrieved_at desc/);
  assert.match(sqlBody, /cardinality\(commitment_keys\) > 500/);
  assert.doesNotMatch(sqlBody, /\bsum\(/i);
  assert.match(migration, /to anon, authenticated;/);
});

test("as grades de liquidação têm índice parcial com o mesmo predicado da RPC", () => {
  const index = read(
    "supabase/migrations/20260924023609_liquidation_grid_month_index.sql",
  );
  assert.match(
    index,
    /where metadata ->> 'schema_name' = 'municipal-liquidations-webrun-grid';/,
  );
  assert.match(sqlBody, /artifact\.metadata ->> 'schema_name' = 'municipal-liquidations-webrun-grid'/);
});

test("a versão vigente busca primeiro pelas chaves e só depois pela grade do mês", () => {
  const current = read(
    "supabase/migrations/20260924035354_commitment_liquidations_key_first.sql",
  ).replace(/--[^\n]*/g, "");
  assert.match(current, /with candidates as materialized \(/);
  assert.ok(current.indexOf("candidates as materialized") < current.indexOf("latest_grids as ("));
  assert.match(current, /record\.payload ->> 'field1089487' = any\(commitment_keys\)/);
  assert.match(current, /'commitment-liquidations\/1\.0\.0'::text/);
  assert.doesNotMatch(current, /\bsum\(/i);
});

test("a página diferencia indisponível de nenhuma liquidação", () => {
  assert.match(page, /getLiquidationsForCommitments\(/);
  assert.match(page, /Liquidações indisponíveis nesta consulta/);
  assert.match(page, /Nenhuma liquidação deste empenho nos meses já coletados/);
  assert.match(page, /mesma chave oficial do empenho/);
});
