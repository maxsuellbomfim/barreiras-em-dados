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
assert.ok(migrationNames.some((name) => name.endsWith("_commitment_creditor_key.sql")));

const sha = (text) => createHash("sha256").update(text).digest("hex");
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
  function record(id, type, key, payload) {
    index += 1;
    statements.push(`insert into raw.raw_records (id, raw_artifact_id, source_record_key,
      record_type, record_index, payload, payload_sha256, parser_version, idempotency_key,
      collected_at) values ('${id}', '${artifact}', '${key}', '${type}', ${index},
      '${JSON.stringify(payload)}', '${sha(`p${index}`)}', 'parser/1', '${sha(`i${index}`)}', now());`);
  }
  const uuid = (n) => `00000000-0000-4000-c000-${String(n).padStart(12, "0")}`;
  const commitment = (n, creditor, name) =>
    record(uuid(n), "municipal_commitment_webrun", `O-${n}`, {
      field1082407: "10/01/2026", field1082409: "Estimativa", field1082410: `${n}/1`,
      field1082412: "100,00", field1082413: "PREFEITURA", field1144629: name,
      field1144633: creditor,
    });
  const contract = (n, cnpj, name) =>
    record(uuid(n), "municipal_contract_teste", `K-${n}`, { documento: cnpj, favorecido: name });

  contract(101, "55.503.441/0001-06", "JS COMERCIO LTDA");
  contract(102, "12.366.653/0001-78", "PB COMBUSTIVEL LTDA");
  contract(103, "11.111.111/0001-11", "ALFA LTDA");
  contract(104, "22.222.222/0001-22", "BETA LTDA");
  commitment(1, "11809", "JS COMERCIO LTDA");      // ligação exata: ensina 11809 -> JS
  commitment(2, "11809", "J S COMERCIO LTDA");     // cita JS: confirma
  commitment(3, "11809", "J S COMERCIO LTDA");     // cita PB: outra empresa
  commitment(4, "999", "SEM HISTORICO");           // credor sem mapa: fica
  commitment(5, "777", "ALFA");                    // credor com dois CNPJs: fica
  commitment(6, "777", "ALFA LTDA");
  commitment(7, "777", "BETA LTDA");
  const link = (n, commitmentId, state, reason, contractId = null, portal = null) =>
    statements.push(`insert into finance.commitment_contract_links (id, commitment_raw_record_id,
      commitment_key, state, reason, contract_raw_record_id, contract_portal_id, rule_version)
      values ('${uuid(n)}', '${commitmentId}', 'O-${n}', '${state}', '${reason}',
      ${contractId ? `'${contractId}'` : "null"}, ${portal ? `'${portal}'` : "null"},
      'commitment-contract-link/1.0.0');`);
  const candidate = (linkN, contractId, portal, name) =>
    statements.push(`insert into finance.commitment_link_candidates (link_id,
      contract_raw_record_id, contract_portal_id, contract_number, contractor)
      values ('${uuid(linkN)}', '${contractId}', '${portal}', '1/2025', '${name}');`);
  link(201, uuid(1), "ligado", "", uuid(101), "P101");
  link(202, uuid(2), "citacao_sem_confirmacao", "favorecido_divergente");
  candidate(202, uuid(101), "P101", "JS COMERCIO LTDA");
  link(203, uuid(3), "citacao_sem_confirmacao", "favorecido_divergente");
  candidate(203, uuid(102), "P102", "PB COMBUSTIVEL LTDA");
  link(204, uuid(4), "citacao_sem_confirmacao", "favorecido_divergente");
  candidate(204, uuid(101), "P101", "JS COMERCIO LTDA");
  link(206, uuid(6), "ligado", "", uuid(103), "P103");
  link(207, uuid(7), "ligado", "", uuid(104), "P104");
  link(205, uuid(5), "citacao_sem_confirmacao", "favorecido_divergente");
  candidate(205, uuid(103), "P103", "ALFA LTDA");
  await database.exec(statements.join("\n"));

  const result = await database.query(
    "select * from finance.confirm_commitment_links_by_creditor_key()");
  assert.deepEqual(
    Object.fromEntries(result.rows.map((row) => [row.decision, row.decided])),
    { approved: 1, rejected: 1 },
  );
  const reviews = await database.query(`
    select target_id::text as link, decision, reviewer_subject,
      checklist ->> 'cnpj' as cnpj, checklist ->> 'contract_portal_id' as portal
    from editorial.editorial_reviews order by target_id`);
  assert.deepEqual(reviews.rows, [
    { link: uuid(202), decision: "approved", reviewer_subject: "automated:commitment-creditor-key",
      cnpj: "55503441000106", portal: "P101" },
    { link: uuid(203), decision: "rejected", reviewer_subject: "automated:commitment-creditor-key",
      cnpj: "55503441000106", portal: null },
  ]);

  // Idempotente: itens decididos saem da fila e não são decididos de novo.
  const again = await database.query(
    "select sum(decided)::integer as n from finance.confirm_commitment_links_by_creditor_key()");
  assert.equal(again.rows[0].n, 0);

  const published = await database.query(`
    select link_id::text as link, review_mode
    from api.get_public_commitment_contract_links(array['P101'])
    order by link_id`);
  assert.deepEqual(published.rows, [
    { link: uuid(201), review_mode: "automated" },
    { link: uuid(202), review_mode: "creditor_key" },
  ]);

  const worker = await database.query(`select has_function_privilege('collector_worker',
    'finance.confirm_commitment_links_by_creditor_key()', 'EXECUTE') as ok,
    has_function_privilege('anon', 'finance.confirm_commitment_links_by_creditor_key()',
    'EXECUTE') as anon`);
  assert.deepEqual(worker.rows[0], { ok: true, anon: false });
} finally {
  await database.close();
}

console.log("commitment creditor key migration test passed");
