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
assert.ok(migrationNames.some((name) => name.endsWith("_receita_cnpj_registry.sql")));

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

  const endpoint = (await database.query(`select e.id from source.source_endpoints e
    join source.data_sources d on d.id = e.data_source_id
    where d.slug = 'receita-federal-cnpj' and e.slug = 'dados-abertos-cnpj'`)).rows[0]?.id;
  assert.ok(endpoint, "endpoint da Receita cadastrado");
  const run = "00000000-0000-4000-a000-000000000003";
  const artifact = "00000000-0000-4000-a000-000000000004";
  await database.exec(`
    insert into source.collection_runs (id, source_endpoint_id, idempotency_key,
      collector_version, parser_version, status, attempt_count, started_at, completed_at)
    values ('${run}', '${endpoint}', '${"e".repeat(64)}', 'test/1', 'parser/1',
      'succeeded', 1, now(), now());
    insert into raw.raw_artifacts (id, collection_run_id, source_endpoint_id, idempotency_key,
      artifact_kind, source_url, retrieved_at, http_status, content_type, byte_size, sha256,
      object_key, collector_version, metadata)
    values ('${artifact}', '${run}', '${endpoint}', '${"f".repeat(64)}', 'document',
      'https://arquivos.receitafederal.gov.br/public.php/webdav/2026-09/', now(), 200,
      'application/json', 2, '${sha("x")}', 'receita/cnpj/x.json', 'test/1', '{}');
  `);
  let index = 0;
  const record = (type, payload) => {
    index += 1;
    return `insert into raw.raw_records (raw_artifact_id, source_record_key, record_type,
      record_index, payload, payload_sha256, parser_version, idempotency_key, collected_at)
      values ('${artifact}', 'k${index}', '${type}', ${index},
      '${JSON.stringify(payload).replaceAll("'", "''")}', '${sha(`p${index}`)}', 'parser/1',
      '${sha(`i${index}`)}', now());`;
  };
  await database.exec([
    record("municipal_transparency_contratos", { documento: "44.493.204/0001-87" }),
    record("municipal_transparency_contratos", { documento: "123.456.789-09" }),
    record("pncp_contrato", { niFornecedor: "12094429000174" }),
    record("pncp_resultado", { niFornecedor: "44493204000187" }),
    record("receita_cnpj_registry", { cnpj: "44493204000187", registry_month: "2026-08",
      razao_social: "NOME ANTIGO LTDA", nome_fantasia: "" }),
    record("receita_cnpj_registry", { cnpj: "44493204000187", registry_month: "2026-09",
      razao_social: "GSV MAIS ALIMENTOS LTDA", nome_fantasia: "COMERCIAL E PAPELARIA VALOIS",
      natureza_juridica: "2062", situacao_cadastral: "02" }),
  ].join("\n"));

  const targets = (await database.query("select cnpj from finance.get_cnpj_registry_targets()"))
    .rows.map((row) => row.cnpj);
  assert.deepEqual(targets, ["12094429000174", "44493204000187"], "CPF fica fora, CNPJ sem repetição");

  const [latest] = (await database.query("select * from finance.cnpj_registry_latest()")).rows;
  assert.equal(latest.razao_social, "GSV MAIS ALIMENTOS LTDA");
  assert.equal(latest.nome_fantasia, "COMERCIAL E PAPELARIA VALOIS");
  assert.equal(latest.registry_month, "2026-09");

  const access = await database.query(`select
    has_function_privilege('collector_worker', 'finance.get_cnpj_registry_targets()', 'EXECUTE') as worker,
    has_function_privilege('anon', 'finance.cnpj_registry_latest()', 'EXECUTE') as anon,
    exists (select 1 from audit.storage_workload_identities
      where object_prefix = 'receita/cnpj/' and status = 'active') as corridor`);
  assert.deepEqual(access.rows[0], { worker: true, anon: false, corridor: true });
} finally {
  await database.close();
}

console.log("receita cnpj registry migration test passed");
