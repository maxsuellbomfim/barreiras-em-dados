import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migration = await readFile(
  new URL(
    "../../supabase/migrations/20260829233000_private_tcm_pncp_contract_link_coverage.sql",
    import.meta.url,
  ),
  "utf8",
);

test("diagnóstico TCM-BA/PNCP permanece privado e agregado", () => {
  assert.match(
    migration,
    /function private\.get_tcm_ba_pncp_contract_link_coverage\(\)/,
  );
  assert.match(migration, /returns jsonb/);
  assert.match(migration, /security definer\s+set search_path = ''/s);
  assert.match(migration, /from public, anon, authenticated/);
  assert.match(migration, /to collector_worker/);
  assert.doesNotMatch(migration, /legal_name|supplier_name|result_payload\s+as/);
});

test("cobertura reconcilia candidatos e resultados da RPC de vínculo", () => {
  assert.match(
    migration,
    /private\.get_tcm_ba_pncp_contract_link_candidates\(5000\)/,
  );
  assert.match(migration, /tcm_candidates_total/);
  assert.match(migration, /tcm_candidates_with_contract_number/);
  assert.match(migration, /pncp_current_contracts_total/);
  assert.match(migration, /pncp_distinct_contract_numbers/);
  assert.match(migration, /exact_number_overlap_candidates/);
  assert.match(migration, /matched_candidates/);
  assert.match(migration, /conflicting_candidates/);
});

test("estado operacional não aceita ausência silenciosa de dados", () => {
  assert.match(migration, /tcm_candidates_empty/);
  assert.match(migration, /tcm_contract_keys_missing/);
  assert.match(migration, /pncp_contracts_empty/);
  assert.match(migration, /no_exact_number_overlap/);
  assert.match(migration, /ready_for_review/);
  assert.match(migration, /tcm-ba-pncp-contract-link-coverage\/1\.0\.0/);
});
