import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migration = await readFile(
  new URL(
    "../../supabase/migrations/20260829223000_private_tcm_pncp_contract_link_candidates.sql",
    import.meta.url,
  ),
  "utf8",
);

test("vínculo TCM-BA/PNCP permanece privado e fechado por padrão", () => {
  assert.match(
    migration,
    /function private\.get_tcm_ba_pncp_contract_link_candidates/,
  );
  assert.match(migration, /security definer\s+set search_path = ''/s);
  assert.match(migration, /from public, anon, authenticated/);
  assert.match(migration, /to collector_worker/);
  assert.doesNotMatch(migration, /grant execute[^;]+\b(?:anon|authenticated)\b/is);
});

test("somente a versão atual e o município de Barreiras entram no universo", () => {
  assert.match(
    migration,
    /tcm-ba-contract-field-candidates\/1\.1\.1/,
  );
  assert.match(migration, /body\.ibge_code = '2903201'/);
  assert.match(migration, /distinct on \(contract\.public_body_id, contract\.external_id\)/);
  assert.match(migration, /contract\.version desc/);
});

test("vínculo usa número exato e exige corroborador disponível", () => {
  assert.match(
    migration,
    /pncp\.contract_number_normalized = tcm\.contract_number_normalized/,
  );
  assert.match(migration, /supplier_cnpj = tcm\.contracted_party_cnpj/);
  assert.match(migration, /pncp\.signed_date = tcm\.signature_date/);
  assert.match(
    migration,
    /pncp\.process_number_normalized = tcm\.process_number_normalized/,
  );
  assert.match(migration, /not possible\.has_corroborator/);
  assert.match(migration, /conflicting_evidence/);
});

test("RPC não usa campos editoriais ou financeiros para fabricar identidade", () => {
  assert.doesNotMatch(migration, /object_description/);
  assert.doesNotMatch(migration, /object_text/);
  assert.doesNotMatch(migration, /amount_text/);
  assert.doesNotMatch(migration, /legal_name/);
  assert.doesNotMatch(migration, /normalized_name/);
  assert.match(migration, /tcm-ba-pncp-contract-link\/1\.0\.0/);
});
