import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { PGlite } from "@electric-sql/pglite";

const migration = await readFile(
  new URL(
    "../../supabase/migrations/20260904051500_harden_tcm_pncp_contract_link_gate.sql",
    import.meta.url,
  ),
  "utf8",
);

test("diagnóstico TCM-BA usa índice parcial para o universo contratual", () => {
  assert.match(
    migration,
    /create index if not exists extraction_results_tcm_ba_contract_candidates_idx/,
  );
  assert.match(migration, /candidate_type = 'tcm_ba_contract_field_candidate'/);
  assert.match(migration, /tcm-ba-contract-field-candidates\/1\.1\.1/);
  assert.match(migration, /tcm-ba-contract-field-candidate/);
});

test("número igual sem segundo identificador oficial nunca vira vínculo", () => {
  assert.match(
    migration,
    /possible\.number_match\s+and possible\.has_corroborator\s+and/s,
  );
  assert.match(migration, /then 'uncorroborated'/);
  assert.doesNotMatch(migration, /else 'exact_unique_number'/);
});

test("cobertura reconcilia todos os estados e explicita a janela datada", () => {
  assert.match(migration, /uncorroborated_candidates/);
  assert.match(migration, /tcm_candidates_without_signature_date/);
  assert.match(migration, /dated_windows_overlap/);
  assert.match(migration, /evaluation_reconciled/);
  assert.match(migration, /tcm-ba-pncp-contract-link-coverage\/1\.2\.0/);
  assert.match(migration, /publication_gate/);
  assert.match(migration, /'REVIEW_REQUIRED'/);
  assert.match(migration, /'BLOCK'/);
});

test("RPCs corrigidas continuam privadas", () => {
  assert.match(migration, /security definer\s+set search_path = ''/s);
  assert.match(migration, /from public, anon, authenticated/g);
  assert.match(migration, /to collector_worker/g);
});

test("execução SQL bloqueia número isolado e aceita CNPJ corroborado", async () => {
  const database = new PGlite();
  await database.exec(`
    create role anon;
    create role authenticated;
    create role collector_worker;
    create schema raw;
    create schema procurement;
    create schema org;
    create schema private;
    create table raw.extraction_results (
      id uuid primary key,
      candidate_type text not null,
      extractor_version text not null,
      result_payload jsonb not null,
      created_at timestamptz not null
    );
    create table org.public_bodies (
      id uuid primary key,
      ibge_code text
    );
    create table procurement.suppliers (
      id uuid primary key,
      public_registration_number text
    );
    create table procurement.procurements (
      id uuid primary key,
      process_number text
    );
    create table procurement.contracts (
      id uuid primary key,
      public_body_id uuid not null,
      external_id text,
      contract_number text,
      signed_date date,
      supplier_id uuid,
      procurement_id uuid,
      version integer not null,
      created_at timestamptz not null
    );
  `);
  await database.exec(migration);
  await database.exec(`
    insert into org.public_bodies values
      ('10000000-0000-0000-0000-000000000001', '2903201');
    insert into procurement.suppliers values
      ('20000000-0000-0000-0000-000000000001', '12345678000199');
    insert into procurement.procurements values
      ('30000000-0000-0000-0000-000000000001', 'PA-45/2025');
    insert into procurement.contracts values (
      '40000000-0000-0000-0000-000000000001',
      '10000000-0000-0000-0000-000000000001',
      'PNCP-1',
      '123/2025',
      '2025-05-20',
      '20000000-0000-0000-0000-000000000001',
      '30000000-0000-0000-0000-000000000001',
      1,
      '2025-05-21T12:00:00Z'
    );
    insert into raw.extraction_results values (
      '50000000-0000-0000-0000-000000000001',
      'tcm_ba_contract_field_candidate',
      'tcm-ba-contract-field-candidates/1.1.1',
      '{
        "schema_name": "tcm-ba-contract-field-candidate",
        "source_artifact_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "source_segment_ordinal": 1,
        "document_kind": "contract",
        "instrument_number": "123/2025",
        "source_anchors": ["instrument_number"]
      }',
      '2025-05-21T13:00:00Z'
    );
  `);

  const isolatedNumber = await database.query(`
    select link_status, match_basis, pncp_contract_id
    from private.get_tcm_ba_pncp_contract_link_candidates(5000)
  `);
  assert.deepEqual(isolatedNumber.rows, [{
    link_status: "uncorroborated",
    match_basis: null,
    pncp_contract_id: null,
  }]);

  await database.exec(`
    update raw.extraction_results
    set result_payload = result_payload || '{
      "contracted_party_cnpj": "12345678000199",
      "source_anchors": ["instrument_number", "contracted_party_cnpj"]
    }'
    where id = '50000000-0000-0000-0000-000000000001';
  `);
  const corroborated = await database.query(`
    select link_status, match_basis, pncp_external_id
    from private.get_tcm_ba_pncp_contract_link_candidates(5000)
  `);
  assert.deepEqual(corroborated.rows, [{
    link_status: "matched",
    match_basis: "exact_number_cnpj",
    pncp_external_id: "PNCP-1",
  }]);

  const coverage = await database.query(`
    select private.get_tcm_ba_pncp_contract_link_coverage() as value
  `);
  assert.equal(coverage.rows[0].value.publication_gate, "REVIEW_REQUIRED");
  assert.equal(coverage.rows[0].value.matched_candidates, 1);
  assert.equal(coverage.rows[0].value.uncorroborated_candidates, 0);
  await database.close();
});
