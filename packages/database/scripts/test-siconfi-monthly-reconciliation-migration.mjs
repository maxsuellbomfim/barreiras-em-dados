import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { PGlite } from "@electric-sql/pglite";
import { pg_trgm } from "@electric-sql/pglite/contrib/pg_trgm";
import { pgcrypto } from "@electric-sql/pglite/contrib/pgcrypto";

const migrationsUrl = new URL("../../../supabase/migrations/", import.meta.url);
const migrationName = "20260824134559_siconfi_monthly_reconciliation.sql";
const migrationNames = (await readdir(fileURLToPath(migrationsUrl)))
  .filter((name) => name.endsWith(".sql"))
  .sort();
assert.ok(migrationNames.includes(migrationName), "migration de reconciliação ausente");

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
    const migration = await readFile(fileURLToPath(new URL(name, migrationsUrl)), "utf8");
    await database.exec(migration);
  }

  const contract = await database.query(`
    select
      to_regprocedure(
        'api.get_public_siconfi_monthly_reconciliation(smallint,smallint)'
      )::text as rpc,
      has_function_privilege(
        'anon',
        'api.get_public_siconfi_monthly_reconciliation(smallint,smallint)',
        'EXECUTE'
      ) as anon_execute,
      pg_get_function_result(
        'api.get_public_siconfi_monthly_reconciliation(smallint,smallint)'::regprocedure
      ) as result,
      pg_get_functiondef(
        'api.get_public_siconfi_monthly_reconciliation(smallint,smallint)'::regprocedure
      ) as definition
  `);
  assert.equal(
    contract.rows[0].rpc,
    "api.get_public_siconfi_monthly_reconciliation(smallint,smallint)",
  );
  assert.equal(contract.rows[0].anon_execute, true);
  assert.match(String(contract.rows[0].result), /annual_amount text/);
  assert.match(String(contract.rows[0].result), /difference_amount text/);
  assert.match(String(contract.rows[0].definition), /observed_months = 12/);
  assert.match(String(contract.rows[0].definition), /annual_amount - coverage\.monthly_sum/);
  assert.match(String(contract.rows[0].definition), /incomplete_months/);
  assert.match(String(contract.rows[0].definition), /source_difference/);
  assert.match(String(contract.rows[0].definition), /matched_exact/);
  assert.doesNotMatch(String(contract.rows[0].definition), /gross_revenue_realized/);
} finally {
  await database.close();
}

console.log("SICONFI monthly reconciliation migration test passed");
