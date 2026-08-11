import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { PGlite } from "@electric-sql/pglite";
import { pg_trgm } from "@electric-sql/pglite/contrib/pg_trgm";
import { pgcrypto } from "@electric-sql/pglite/contrib/pgcrypto";

const migrationsUrl = new URL("../../../supabase/migrations/", import.meta.url);
const migrationNames = (await readdir(fileURLToPath(migrationsUrl)))
  .filter((name) => name.endsWith(".sql"))
  .sort();
const migrations = await Promise.all(
  migrationNames.map((name) => readFile(fileURLToPath(new URL(name, migrationsUrl)), "utf8")),
);
const seed = await readFile(
  fileURLToPath(new URL("../../../supabase/seed.sql", import.meta.url)),
  "utf8",
);
const database = new PGlite({ extensions: { pgcrypto, pg_trgm } });

async function rejects(sql, pattern = undefined) {
  await assert.rejects(database.exec(sql), pattern);
}

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
  await database.exec(seed);

  const relation = await database.query(`
    select to_regclass('finance.public_obligations')::text as obligations
  `);
  assert.deepEqual(relation.rows, [{ obligations: "finance.public_obligations" }]);

  const security = await database.query(`
    select
      (select relrowsecurity from pg_class
       where oid = 'finance.public_obligations'::regclass) as rls,
      (select relforcerowsecurity from pg_class
       where oid = 'finance.public_obligations'::regclass) as force_rls,
      has_table_privilege('anon', 'finance.public_obligations', 'SELECT') as anon_select,
      has_table_privilege('collector_worker', 'finance.public_obligations', 'INSERT') as worker_insert,
      has_table_privilege('collector_worker', 'finance.public_obligations', 'UPDATE') as worker_update,
      has_function_privilege(
        'anon', 'api.get_public_obligations(integer,integer,text)', 'EXECUTE'
      ) as anon_rpc
  `);
  assert.deepEqual(security.rows, [{
    rls: true,
    force_rls: true,
    anon_select: false,
    worker_insert: true,
    worker_update: false,
    anon_rpc: true,
  }]);

  await database.exec(`
    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version, status
    ) values (
      '00000000-0000-0000-0000-000000008001',
      '00000000-0000-4000-8000-000000000102',
      'public-obligation-run-fixture', 'test/1', 'succeeded'
    );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, idempotency_key, artifact_kind,
      source_url, retrieved_at, byte_size, sha256, object_key, collector_version
    ) values (
      '00000000-0000-0000-0000-000000008002',
      '00000000-0000-0000-0000-000000008001',
      '00000000-0000-4000-8000-000000000102',
      'public-obligation-artifact-fixture', 'http_response',
      'https://portaldatransparencia.barreiras.ba.gov.br/api?resource=balancetes',
      '2026-08-11 16:40:00+00', 100, '${"a".repeat(64)}',
      'fixtures/obligations.json', 'test/1'
    );
    insert into raw.raw_records (
      id, raw_artifact_id, source_record_key, record_type, record_index,
      payload, payload_sha256, parser_version, idempotency_key, collected_at
    ) values (
      '00000000-0000-0000-0000-000000008003',
      '00000000-0000-0000-0000-000000008002', 'balancete-2026-06',
      'municipal_transparency_balancetes', 0,
      '{"titulo":"BALANCETE JUNHO 2026"}'::jsonb, '${"b".repeat(64)}',
      'test/1', 'public-obligation-record-fixture', '2026-08-11 16:40:00+00'
    );
    insert into org.public_bodies (
      id, origin_raw_record_id, ibge_code, name, body_type, state_code
    ) values
      (
        '00000000-0000-0000-0000-000000008004',
        '00000000-0000-0000-0000-000000008003', '2903201',
        'Município de Barreiras', 'executive', 'BA'
      ),
      (
        '00000000-0000-0000-0000-000000008007',
        '00000000-0000-0000-0000-000000008003', null,
        'Câmara Municipal de Barreiras', 'legislative', 'BA'
      );
    insert into finance.public_obligations (
      id, origin_raw_record_id, public_body_id, obligation_key,
      obligation_type, description, fiscal_year, period_start, period_end,
      opening_balance, additions_amount, reductions_amount, payments_amount,
      closing_balance, status, validation_state, methodology_version, validated_at
    ) values
      (
        '00000000-0000-0000-0000-000000008005',
        '00000000-0000-0000-0000-000000008003',
        '00000000-0000-0000-0000-000000008004', 'loan-hospital-2026',
        'loan', 'Empréstimo para conclusão do hospital', 2026,
        '2026-01-01', '2026-06-30', 10000000.00, 1000000.00,
        500000.00, 250000.00, 10250000.00, 'active', 'reconciled',
        'public-obligations/1.0.0', '2026-08-11 16:45:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000008006',
        '00000000-0000-0000-0000-000000008003',
        '00000000-0000-0000-0000-000000008004', 'precat-2026',
        'precatorio', 'Precatório ainda não reconciliado', 2026,
        '2026-01-01', '2026-06-30', null, null, null, null, 500000.00,
        'reported', 'extracted', 'public-obligations/1.0.0', null
      );
  `);

  await database.exec("set role anon");
  await rejects("select * from finance.public_obligations", /permission denied/);
  const projection = await database.query(`
    select * from api.get_public_obligations(20, 2026, null)
  `);
  await database.exec("reset role");
  assert.equal(projection.rows.length, 1);
  assert.deepEqual(projection.rows[0], {
    obligation_id: "00000000-0000-0000-0000-000000008005",
    obligation_type: "loan",
    description: "Empréstimo para conclusão do hospital",
    fiscal_year: 2026,
    period_start: "2026-01-01",
    period_end: "2026-06-30",
    opening_balance: "10000000.00",
    additions_amount: "1000000.00",
    reductions_amount: "500000.00",
    payments_amount: "250000.00",
    closing_balance: "10250000.00",
    status: "active",
    validation_state: "reconciled",
    source_url: "https://portaldatransparencia.barreiras.ba.gov.br/api?resource=balancetes",
    artifact_sha256: "a".repeat(64),
    source_retrieved_at: new Date("2026-08-11T16:40:00.000Z"),
    methodology_version: "public-obligations/1.0.0",
  });
  assert.equal("total_debt" in projection.rows[0], false);

  await rejects(
    "select * from api.get_public_obligations(0, null, null)",
    /page_size deve estar entre 1 e 200/,
  );
  await rejects(
    "select * from api.get_public_obligations(20, null, 'cpf')",
    /obligation_type_filter nao permitido/,
  );
  await rejects(`
    insert into finance.public_obligations (
      origin_raw_record_id, public_body_id, obligation_key, obligation_type,
      description, fiscal_year, period_end, closing_balance, status,
      validation_state, methodology_version, validated_at
    ) values (
      '00000000-0000-0000-0000-000000008003',
      '00000000-0000-0000-0000-000000008004', 'invalid-negative', 'loan',
      'Saldo inválido', 2026, '2026-06-30', -1, 'active', 'validated',
      'public-obligations/1.0.0', '2026-08-11 16:45:00+00'
    )
  `, /public_obligations_closing_balance_check/);
  await rejects(`
    insert into finance.public_obligations (
      origin_raw_record_id, public_body_id, supersedes_id, version,
      obligation_key, obligation_type, description, fiscal_year, period_end,
      closing_balance, status, validation_state, methodology_version
    ) values (
      '00000000-0000-0000-0000-000000008003',
      '00000000-0000-0000-0000-000000008007',
      '00000000-0000-0000-0000-000000008005', 2,
      'loan-hospital-2026', 'loan', 'Retificação atribuída ao órgão errado',
      2026, '2026-06-30', 10250000.00, 'active', 'extracted',
      'public-obligations/1.0.0'
    )
  `, /public_obligations_supersedes_same_body/);
  await rejects(
    "update finance.public_obligations set description = 'alterado' where id = '00000000-0000-0000-0000-000000008005'",
    /immutable relation/,
  );
  await rejects(
    "delete from finance.public_obligations where id = '00000000-0000-0000-0000-000000008005'",
    /immutable relation/,
  );

  console.log("Obrigações normalizadas: evidência, RLS, imutabilidade e projeção pública verificadas.");
} finally {
  await database.close();
}
