import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { PGlite } from "@electric-sql/pglite";
import { pg_trgm } from "@electric-sql/pglite/contrib/pg_trgm";
import { pgcrypto } from "@electric-sql/pglite/contrib/pgcrypto";

const migrationsUrl = new URL("../../../supabase/migrations/", import.meta.url);
const migrationName = "20260824130428_siconfi_annual_totals.sql";
const migrationNames = (await readdir(fileURLToPath(migrationsUrl)))
  .filter((name) => name.endsWith(".sql"))
  .sort();
assert.notEqual(
  migrationNames.indexOf(migrationName),
  -1,
  "migration de totais anuais SICONFI não encontrada",
);

const migrations = await Promise.all(
  migrationNames.map((name) =>
    readFile(fileURLToPath(new URL(name, migrationsUrl)), "utf8"),
  ),
);
const database = new PGlite({ extensions: { pgcrypto, pg_trgm } });

try {
  await database.exec(`
    create role anon nologin;
    create role authenticated nologin;
    create role authenticator nologin;
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
      id text primary key,
      name text not null,
      public boolean not null default false,
      file_size_limit bigint,
      allowed_mime_types text[]
    );
    create table storage.objects (
      id uuid primary key,
      bucket_id text not null references storage.buckets(id),
      name text not null,
      unique(bucket_id, name)
    );
    alter table storage.objects enable row level security;
    grant usage on schema storage to authenticated;
    grant select, insert, update, delete on storage.objects to authenticated;
  `);
  for (const migration of migrations) await database.exec(migration);

  const contract = await database.query(`
    select
      to_regclass('finance.siconfi_annual_totals')::text as totals_table,
      to_regprocedure(
        'api.get_public_siconfi_annual_totals(integer,smallint,smallint)'
      )::text as public_rpc,
      has_table_privilege(
        'anon', 'finance.siconfi_annual_totals', 'SELECT'
      ) as anon_table_select,
      has_table_privilege(
        'collector_worker', 'finance.siconfi_annual_totals', 'INSERT'
      ) as collector_insert,
      has_function_privilege(
        'anon',
        'api.get_public_siconfi_annual_totals(integer,smallint,smallint)',
        'EXECUTE'
      ) as anon_rpc_execute
  `);
  assert.deepEqual(contract.rows, [{
    totals_table: "finance.siconfi_annual_totals",
    public_rpc: "api.get_public_siconfi_annual_totals(integer,smallint,smallint)",
    anon_table_select: false,
    collector_insert: true,
    anon_rpc_execute: true,
  }]);

  const rpcResult = await database.query(`
    select pg_get_function_result(
      'api.get_public_siconfi_annual_totals(integer,smallint,smallint)'::regprocedure
    ) as result
  `);
  assert.match(String(rpcResult.rows[0].result), /amount text/);

  const rls = await database.query(`
    select relrowsecurity, relforcerowsecurity
    from pg_catalog.pg_class
    join pg_catalog.pg_namespace
      on pg_catalog.pg_namespace.oid = pg_catalog.pg_class.relnamespace
    where pg_catalog.pg_namespace.nspname = 'finance'
      and relname = 'siconfi_annual_totals'
  `);
  assert.deepEqual(rls.rows, [{ relrowsecurity: true, relforcerowsecurity: true }]);

  await database.exec(`
    insert into source.data_sources (
      id, slug, name, authority_level, is_official, homepage_url
    ) values (
      '00000000-0000-0000-0000-000000009001',
      'siconfi-contract-test', 'SICONFI teste', 'official', true,
      'https://siconfi.tesouro.gov.br/siconfi/'
    );
    insert into source.source_endpoints (
      id, data_source_id, slug, endpoint_kind, base_url
    ) values (
      '00000000-0000-0000-0000-000000009002',
      '00000000-0000-0000-0000-000000009001', 'dca',
      'api', 'https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca'
    );
    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version, status
    ) values (
      '00000000-0000-0000-0000-000000009003',
      '00000000-0000-0000-0000-000000009002',
      'siconfi-contract-run', 'test/1', 'succeeded'
    );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, idempotency_key, artifact_kind,
      source_url, retrieved_at, byte_size, sha256, object_key, collector_version
    ) values (
      '00000000-0000-0000-0000-000000009004',
      '00000000-0000-0000-0000-000000009003',
      '00000000-0000-0000-0000-000000009002',
      'siconfi-contract-artifact', 'http_response',
      'https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca?an_exercicio=2025',
      '2026-08-24 12:00:00+00', 100, '${"a".repeat(64)}',
      'siconfi/dca/2025/test.json', 'test/1'
    );
    insert into raw.raw_records (
      id, raw_artifact_id, source_record_key, record_type, record_index,
      payload, payload_sha256, parser_version, idempotency_key, collected_at
    ) values (
      '00000000-0000-0000-0000-000000009005',
      '00000000-0000-0000-0000-000000009004', 'siconfi:dca:2025:test',
      'siconfi_dca_line', 0,
      '{
        "exercicio":2025,"cod_ibge":2903201,
        "instituicao":"Prefeitura Municipal de Barreiras - BA",
        "anexo":"DCA-Anexo I-C","rotulo":"Padrão",
        "coluna":"Deduções - FUNDEB","cod_conta":"TotalReceitas",
        "conta":"TOTAL DAS RECEITAS (III) = (I + II)","valor":"-125.40"
      }'::jsonb,
      '${"b".repeat(64)}', 'test/1', 'siconfi-contract-record',
      '2026-08-24 12:00:00+00'
    );
    insert into org.public_bodies (
      id, origin_raw_record_id, ibge_code, name, body_type, state_code
    ) values (
      '00000000-0000-0000-0000-000000009006',
      '00000000-0000-0000-0000-000000009005', '2903201',
      'Município de Barreiras', 'executive', 'BA'
    );
  `);

  await database.exec("set role collector_worker");
  const inserted = await database.query(`
    insert into finance.siconfi_annual_totals (
      id, origin_raw_record_id, source_artifact_id, public_body_id,
      fiscal_year, metric_key, amount, official_annex, official_label,
      official_column_label, official_account_code, official_account_label,
      methodology_version
    ) values (
      '00000000-0000-0000-0000-000000009007',
      '00000000-0000-0000-0000-000000009005',
      '00000000-0000-0000-0000-000000009004',
      '00000000-0000-0000-0000-000000009006',
      2025, 'fundeb_deductions', -125.40,
      'DCA-Anexo I-C', 'Padrão', 'Deduções - FUNDEB',
      'TotalReceitas', 'TOTAL DAS RECEITAS (III) = (I + II)',
      'siconfi-annual-totals/1.0.0'
    ) returning amount
  `);
  assert.equal(inserted.rows[0].amount, "-125.40");

  await database.exec(`
    insert into evidence.evidence_items (
      target_type, target_id, raw_artifact_id, raw_record_id,
      evidence_kind, source_url, excerpt, locator, content_sha256,
      parser_version, is_primary
    ) values (
      'finance.siconfi_annual_totals',
      '00000000-0000-0000-0000-000000009007',
      '00000000-0000-0000-0000-000000009004',
      '00000000-0000-0000-0000-000000009005', 'source_record',
      'https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca?an_exercicio=2025',
      'linha oficial',
      '{"fiscal_year":2025}'::jsonb, '${"a".repeat(64)}',
      'siconfi-annual-totals/1.0.0', true
    )
  `);
  await database.exec("reset role");

  const publicRows = await database.query(`
    select fiscal_year, metric_key, amount, source_artifact_sha256
    from api.get_public_siconfi_annual_totals(
      70, 2021::smallint, 2025::smallint
    )
  `);
  assert.deepEqual(publicRows.rows, [{
    fiscal_year: 2025,
    metric_key: "fundeb_deductions",
    amount: "-125.40",
    source_artifact_sha256: "a".repeat(64),
  }]);

  await assert.rejects(
    database.exec(`
      update finance.siconfi_annual_totals
      set amount = 1
      where id = '00000000-0000-0000-0000-000000009007'
    `),
    /append-only|immutable|imutáveis|mutation|alterados|excluídos/i,
  );
} finally {
  await database.close();
}

console.log("SICONFI annual totals migration test passed");
