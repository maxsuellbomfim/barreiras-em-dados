import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { PGlite } from "@electric-sql/pglite";

const migrationUrl = new URL(
  "../../supabase/migrations/20260902213010_optimize_executive_profiles_rpc.sql",
  import.meta.url,
);

test("perfis do Executivo usam a chave oficial indexada e preservam a versão mais recente", async () => {
  const migration = await readFile(migrationUrl, "utf8");
  assert.match(migration, /distinct on \(record\.source_record_key\)/i);
  assert.match(migration, /record\.source_record_key is not null/i);
  assert.doesNotMatch(migration, /create\s+index/i);

  const database = new PGlite();
  try {
    await database.exec(`
      create role anon nologin;
      create role authenticated nologin;
      create schema api;
      create schema raw;
      grant usage on schema api to anon, authenticated;
      create table raw.raw_artifacts (
        id uuid primary key,
        source_url text not null,
        sha256 text not null
      );
      create table raw.raw_records (
        id uuid primary key,
        raw_artifact_id uuid not null references raw.raw_artifacts(id),
        source_record_key text,
        record_type text not null,
        payload jsonb not null,
        collected_at timestamptz not null
      );
      create index raw_records_source_key_idx
        on raw.raw_records (record_type, source_record_key)
        where source_record_key is not null;
    `);
    await database.exec(migration);
    await database.exec(`
      insert into raw.raw_artifacts (id, source_url, sha256) values
        ('00000000-0000-0000-0000-000000000101', 'https://barreiras.ba.gov.br/prefeito-e-vice/', '${"a".repeat(64)}'),
        ('00000000-0000-0000-0000-000000000102', 'https://barreiras.ba.gov.br/prefeito-e-vice/', '${"b".repeat(64)}'),
        ('00000000-0000-0000-0000-000000000103', 'https://barreiras.ba.gov.br/secretaria-municipal-de-saude/', '${"c".repeat(64)}');
      insert into raw.raw_records (
        id, raw_artifact_id, source_record_key, record_type, payload, collected_at
      ) values
        (
          '00000000-0000-0000-0000-000000000111',
          '00000000-0000-0000-0000-000000000101',
          'prefeitura:executivo:prefeito', 'barreiras_executive_profile',
          '{"profile_key":"prefeito","role":"prefeito","display_name":"Nome antigo","profile_url":"https://barreiras.ba.gov.br/prefeito-e-vice/"}',
          '2026-08-01 10:00:00+00'
        ),
        (
          '00000000-0000-0000-0000-000000000112',
          '00000000-0000-0000-0000-000000000102',
          'prefeitura:executivo:prefeito', 'barreiras_executive_profile',
          '{"profile_key":"prefeito","role":"prefeito","display_name":"Nome atual","profile_url":"https://barreiras.ba.gov.br/prefeito-e-vice/"}',
          '2026-09-01 10:00:00+00'
        ),
        (
          '00000000-0000-0000-0000-000000000113',
          '00000000-0000-0000-0000-000000000103',
          'prefeitura:executivo:saude', 'barreiras_executive_profile',
          '{"profile_key":"secretaria-saude","role":"secretario","department_name":"Saúde","display_name":"Pessoa da Saúde","profile_url":"https://barreiras.ba.gov.br/secretaria-municipal-de-saude/"}',
          '2026-09-01 11:00:00+00'
        );
    `);

    await database.exec("set role anon");
    const result = await database.query(`
      select profile_key, role, display_name, artifact_sha256,
        methodology_version
      from api.get_executive_profiles(100)
    `);
    await database.exec("reset role");

    assert.deepEqual(result.rows, [
      {
        profile_key: "prefeito",
        role: "prefeito",
        display_name: "Nome atual",
        artifact_sha256: "b".repeat(64),
        methodology_version: "executive-profiles/barreiras/1.0.0",
      },
      {
        profile_key: "secretaria-saude",
        role: "secretario",
        display_name: "Pessoa da Saúde",
        artifact_sha256: "c".repeat(64),
        methodology_version: "executive-profiles/barreiras/1.0.0",
      },
    ]);
  } finally {
    await database.close();
  }
});
