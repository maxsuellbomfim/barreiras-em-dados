import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migration = await readFile(
  new URL(
    "../../supabase/migrations/20260829234500_fix_tcm_pncp_contract_link_coverage.sql",
    import.meta.url,
  ),
  "utf8",
);

test("correção conta todo candidato TCM antes de avaliar a chave", () => {
  assert.match(migration, /count\(\*\)::integer as candidates_total/);
  assert.match(
    migration,
    /count\(\*\) filter \(\s*where contract_number_normalized is not null/s,
  );
  assert.match(
    migration,
    /result_payload -> 'source_anchors' \? link_field/s,
  );
  assert.match(migration, /evaluation_reconciled/);
});

test("diagnóstico explicita a faixa temporal comparada", () => {
  assert.match(migration, /tcm_earliest_signature_date/);
  assert.match(migration, /tcm_latest_signature_date/);
  assert.match(migration, /pncp_earliest_signed_date/);
  assert.match(migration, /pncp_latest_signed_date/);
  assert.match(
    migration,
    /tcm-ba-pncp-contract-link-coverage\/1\.1\.0/,
  );
});

test("gate bloqueia reconciliação truncada ou inconsistente", () => {
  assert.match(migration, /evaluation_incomplete/);
  assert.match(migration, /publication_gate/);
  assert.match(migration, /'BLOCK'/);
  assert.match(migration, /security definer\s+set search_path = ''/s);
  assert.match(migration, /from public, anon, authenticated/);
});
