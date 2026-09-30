import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile, readdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { PGlite } from "@electric-sql/pglite";
import { pg_trgm } from "@electric-sql/pglite/contrib/pg_trgm";
import { pgcrypto } from "@electric-sql/pglite/contrib/pgcrypto";

const migrationsUrl = new URL("../../../supabase/migrations/", import.meta.url);
const migrationNames = (await readdir(fileURLToPath(migrationsUrl)))
  .filter((name) => name.endsWith(".sql"))
  .sort();
assert.ok(migrationNames.some((name) => name.endsWith("_commitment_registry_name.sql")));

const sha = (text) => createHash("sha256").update(text).digest("hex");
const q = (text) => text.replaceAll("'", "''");
const database = new PGlite({ extensions: { pgcrypto, pg_trgm } });
try {
  await database.exec(`
    create role anon nologin;
    create role authenticated nologin;
    create role authenticator nologin;
    create role service_role nologin bypassrls;
    create schema auth;
    create table auth.users (id uuid primary key);
    insert into auth.users (id) values
      ('1575c740-fcff-4b1a-89a9-e8e5a314880a'),
      ('27b3add6-f788-48e5-bf6f-50dfbd8cf198'),
      ('c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a');
    create function auth.uid() returns uuid language sql stable set search_path = ''
      as $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
    create function auth.jwt() returns jsonb language sql stable set search_path = ''
      as $$ select coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb) $$;
    create schema storage;
    create table storage.buckets (
      id text primary key, name text not null, public boolean not null default false,
      file_size_limit bigint, allowed_mime_types text[]
    );
    create table storage.objects (
      id uuid primary key, bucket_id text not null references storage.buckets(id),
      name text not null, unique(bucket_id, name)
    );
    alter table storage.objects enable row level security;
    grant usage on schema storage to authenticated;
    grant select, insert, update, delete on storage.objects to authenticated;
  `);
  for (const name of migrationNames) {
    await database.exec(await readFile(fileURLToPath(new URL(name, migrationsUrl)), "utf8"));
  }

  const normalized = (
    await database.query(`select
      finance.normalize_company_name('SUCESSO MONTADORA DE ESTRUTURAS LTDA-EPP') as a,
      finance.normalize_company_name('M.D SAÚDE S/S') as b,
      finance.normalize_company_name('B3 S.A. – Brasil, Bolsa, Balcão') as c,
      finance.normalize_company_name('COMERCIAL MAPEL EIRELI ATACADAO VITORIA') as d,
      finance.normalize_company_name('  ') as e`)
  ).rows[0];
  assert.deepEqual(normalized, {
    a: "SUCESSO MONTADORA DE ESTRUTURAS",
    b: "MD SAUDE",
    c: "B3 BRASIL BOLSA BALCAO",
    d: "COMERCIAL MAPEL ATACADAO VITORIA",
    e: null,
  });

  const run = "00000000-0000-4000-a000-000000000003";
  const artifact = "00000000-0000-4000-a000-000000000004";
  await database.exec(`
    insert into source.data_sources (id, slug, name, authority_level, homepage_url)
    values ('00000000-0000-4000-a000-000000000001', 'teste-webrun', 'WebRun de teste',
            'official', 'https://barreiras.ba.gov.br');
    insert into source.source_endpoints (id, data_source_id, slug, endpoint_kind, base_url)
    values ('00000000-0000-4000-a000-000000000002', '00000000-0000-4000-a000-000000000001',
            'grid-teste', 'api', 'https://barreiras.ba.gov.br');
    insert into source.collection_runs (id, source_endpoint_id, idempotency_key,
      collector_version, parser_version, status, attempt_count, started_at, completed_at)
    values ('${run}', '00000000-0000-4000-a000-000000000002', '${"e".repeat(64)}',
            'test/1', 'parser/1', 'succeeded', 1, now(), now());
    insert into raw.raw_artifacts (id, collection_run_id, source_endpoint_id, idempotency_key,
      artifact_kind, source_url, retrieved_at, http_status, content_type, byte_size, sha256,
      object_key, collector_version, metadata)
    values ('${artifact}', '${run}', '00000000-0000-4000-a000-000000000002', '${"f".repeat(64)}',
      'http_response', 'https://barreiras.ba.gov.br/grid', now(), 200, 'application/json', 2,
      '${sha("grid")}', 'grid/${sha("grid")}.json', 'test/1', '{}');
  `);

  let index = 0;
  const statements = [];
  const uuid = (n) => `00000000-0000-4000-c000-${String(n).padStart(12, "0")}`;
  function record(id, type, payload) {
    index += 1;
    statements.push(`insert into raw.raw_records (id, raw_artifact_id, source_record_key,
      record_type, record_index, payload, payload_sha256, parser_version, idempotency_key,
      collected_at) values ('${id}', '${artifact}', 'k${index}', '${type}', ${index},
      '${q(JSON.stringify(payload))}', '${sha(`p${index}`)}', 'parser/1', '${sha(`i${index}`)}',
      now());`);
  }
  const contract = (n, cnpj, name) =>
    record(uuid(n), "municipal_transparency_contratos", { documento: cnpj, favorecido: name });
  const commitment = (n, name) =>
    record(uuid(n), "municipal_commitment_webrun", {
      field1082407: "10/01/2026", field1082410: `${n}/1`, field1082412: "100,00",
      field1082413: "PREFEITURA", field1144629: name, field1144633: String(900 + n),
    });
  const registry = (n, cnpj, razao, fantasia) =>
    record(uuid(n), "receita_cnpj_registry", {
      cnpj, razao_social: razao, nome_fantasia: fantasia, natureza_juridica: "2062",
      registry_month: "2026-09",
    });
  const link = (n, commitmentN, reason) =>
    statements.push(`insert into finance.commitment_contract_links (id, commitment_raw_record_id,
      commitment_key, state, reason, rule_version) values ('${uuid(n)}', '${uuid(commitmentN)}',
      'O-${n}', 'citacao_sem_confirmacao', '${reason}', 'commitment-contract-link/1.0.0');`);
  const candidate = (linkN, contractN, portal, name) =>
    statements.push(`insert into finance.commitment_link_candidates (link_id,
      contract_raw_record_id, contract_portal_id, contract_number, contractor)
      values ('${uuid(linkN)}', '${uuid(contractN)}', '${portal}', '1/2025', '${q(name)}');`);

  contract(101, "44.493.204/0001-87", "COMERCIAL VALOIS LTDA");
  contract(102, "11.260.603/0001-49", "COMERCIAL MAPEL LTDA");
  contract(103, "14.770.671/0001-46", "ORTOCLINICA LTD");
  contract(104, "47.879.385/0001-72", "CARTUCHO EXPRESS");
  contract(105, "22.222.222/0001-22", "DUPLA LTDA");
  contract(106, "22.222.222/0001-22", "DUPLA LTDA - ADITIVO");
  registry(201, "44493204000187", "GSV MAIS ALIMENTOS LTDA", "COMERCIAL E PAPELARIA VALOIS");
  registry(202, "11260603000149", "COMERCIAL MAPEL LTDA", "ATACADAO VITORIA");
  registry(203, "14770671000146", "ORTOCLINICA LTDA", "CENTRO MEDICO OESTE");
  registry(204, "47879385000172", "CARTUCHO EXPRESS COMERCIO DE INFORMATICA LTDA", "");
  registry(205, "22222222000122", "DUPLA LTDA", "");
  commitment(1, "GSV MAIS ALIMENTOS LTDA");
  commitment(2, "COMERCIAL MAPEL EIRELI ATACADAO VITORIA");
  commitment(3, "CENTRO MÉDICO OESTE");
  commitment(4, "CARTUCHOS EXPRESS COMERCIO DE INFORMATICA LTDA");
  commitment(5, "DUPLA LTDA");
  link(301, 1, "favorecido_divergente"); candidate(301, 101, "P101", "COMERCIAL VALOIS LTDA");
  link(302, 2, "favorecido_divergente"); candidate(302, 102, "P102", "COMERCIAL MAPEL LTDA");
  link(303, 3, "favorecido_divergente"); candidate(303, 103, "P103", "ORTOCLINICA LTD");
  link(304, 4, "favorecido_divergente"); candidate(304, 104, "P104", "CARTUCHO EXPRESS");
  link(305, 5, "varios_contratos");
  candidate(305, 105, "P105", "DUPLA LTDA");
  candidate(305, 106, "P106", "DUPLA LTDA - ADITIVO");
  await database.exec(statements.join("\n"));

  const result = await database.query(
    "select * from finance.confirm_commitment_links_by_registry_name()");
  assert.deepEqual(result.rows, [{ decision: "approved", decided: 3 }]);
  const reviews = await database.query(`
    select target_id::text as link, reviewer_subject, checklist ->> 'matched_field' as field,
      checklist ->> 'cnpj' as cnpj, checklist ->> 'contract_portal_id' as portal
    from editorial.editorial_reviews order by target_id`);
  assert.deepEqual(reviews.rows, [
    { link: uuid(301), reviewer_subject: "automated:commitment-registry-name",
      field: "razao_social", cnpj: "44493204000187", portal: "P101" },
    { link: uuid(302), reviewer_subject: "automated:commitment-registry-name",
      field: "razao_social_e_nome_fantasia", cnpj: "11260603000149", portal: "P102" },
    { link: uuid(303), reviewer_subject: "automated:commitment-registry-name",
      field: "nome_fantasia", cnpj: "14770671000146", portal: "P103" },
  ], "erro de grafia e dois contratos possíveis continuam pendentes");

  const again = await database.query(
    "select sum(decided)::integer as n from finance.confirm_commitment_links_by_registry_name()");
  assert.equal(again.rows[0].n, 0, "decidido não é decidido de novo");

  const published = await database.query(`
    select review_mode from api.get_public_commitment_contract_links(array['P101'])`);
  assert.deepEqual(published.rows, [{ review_mode: "registry_name" }]);

  const access = await database.query(`select
    has_function_privilege('collector_worker',
      'finance.confirm_commitment_links_by_registry_name()', 'EXECUTE') as worker,
    has_function_privilege('anon',
      'finance.confirm_commitment_links_by_registry_name()', 'EXECUTE') as anon`);
  assert.deepEqual(access.rows[0], { worker: true, anon: false });
} finally {
  await database.close();
}

console.log("commitment registry name migration test passed");
