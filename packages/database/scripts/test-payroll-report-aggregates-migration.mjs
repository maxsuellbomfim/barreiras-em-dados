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

  const contracts = await database.query(`
    select
      to_regclass('hr.payroll_report_aggregates')::text as aggregate_table,
      to_regprocedure('api.get_public_payroll_months(integer)')::text as public_rpc,
      (select relrowsecurity from pg_class
       where oid = 'hr.payroll_report_aggregates'::regclass) as rls,
      (select relforcerowsecurity from pg_class
       where oid = 'hr.payroll_report_aggregates'::regclass) as force_rls,
      has_table_privilege('anon', 'hr.payroll_report_aggregates', 'SELECT')
        as anon_select,
      has_table_privilege('authenticated', 'hr.payroll_report_aggregates', 'SELECT')
        as authenticated_select,
      has_table_privilege('collector_worker', 'hr.payroll_report_aggregates', 'INSERT')
        as worker_insert,
      has_table_privilege('collector_worker', 'hr.payroll_report_aggregates', 'UPDATE')
        as worker_update,
      has_function_privilege(
        'anon', 'api.get_public_payroll_months(integer)', 'EXECUTE'
      ) as anon_rpc
  `);
  assert.deepEqual(contracts.rows, [{
    aggregate_table: "hr.payroll_report_aggregates",
    public_rpc: "api.get_public_payroll_months(integer)",
    rls: true,
    force_rls: true,
    anon_select: false,
    authenticated_select: false,
    worker_insert: true,
    worker_update: false,
    anon_rpc: true,
  }]);

  await database.exec(`
    insert into source.data_sources (
      id, slug, name, authority_level, is_official, homepage_url
    ) values (
      '00000000-0000-0000-0000-000000009001', 'payroll-test-source',
      'Fonte oficial de teste da folha', 'official', true,
      'https://portaldatransparencia.barreiras.ba.gov.br/'
    );
    insert into source.source_endpoints (
      id, data_source_id, slug, endpoint_kind, base_url
    ) values (
      '00000000-0000-0000-0000-000000009002',
      '00000000-0000-0000-0000-000000009001', 'payroll-test-endpoint',
      'api', 'https://portaldatransparencia.barreiras.ba.gov.br/api'
    );
    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version, status
    ) values (
      '00000000-0000-0000-0000-000000009003',
      '00000000-0000-0000-0000-000000009002',
      'payroll-report-aggregate-run-fixture', 'test/1', 'succeeded'
    );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, idempotency_key, artifact_kind,
      source_url, retrieved_at, byte_size, sha256, object_key, collector_version
    ) values (
      '00000000-0000-0000-0000-000000009004',
      '00000000-0000-0000-0000-000000009003',
      '00000000-0000-0000-0000-000000009002',
      'payroll-report-catalog-artifact-fixture', 'http_response',
      'https://portaldatransparencia.barreiras.ba.gov.br/api?resource=servidores',
      '2026-08-06 18:00:00+00', 100, '${"a".repeat(64)}',
      'fixtures/payroll/catalog.json', 'test/1'
    );
    insert into raw.raw_records (
      id, raw_artifact_id, source_record_key, record_type, record_index,
      payload, payload_sha256, parser_version, idempotency_key, collected_at
    ) values
      (
        '00000000-0000-0000-0000-000000009005',
        '00000000-0000-0000-0000-000000009004', 'servidores-244',
        'municipal_transparency_servidores', 0,
        '{"tipo":"1","ano_ref":"2026","mes_ref":"7","url":"https://barreiras.mtransparente.com.br/admin/data/SERVIDORES060826145033.pdf"}'::jsonb,
        '${"b".repeat(64)}', 'test/1', 'payroll-report-catalog-record-fixture',
        '2026-08-06 18:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009009',
        '00000000-0000-0000-0000-000000009004', 'estagiarios-244',
        'municipal_transparency_servidores', 1,
        '{"tipo":"3","ano_ref":"2026","mes_ref":"7","url":"https://barreiras.mtransparente.com.br/admin/data/SERVIDORES060826145033.pdf"}'::jsonb,
        '${"d".repeat(64)}', 'test/1', 'payroll-intern-catalog-record-fixture',
        '2026-08-06 18:00:00+00'
      );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, parent_artifact_id,
      idempotency_key, artifact_kind, source_url, retrieved_at, byte_size,
      sha256, object_key, collector_version, metadata
    ) values (
      '00000000-0000-0000-0000-000000009006',
      '00000000-0000-0000-0000-000000009003',
      '00000000-0000-0000-0000-000000009002',
      '00000000-0000-0000-0000-000000009004',
      'payroll-report-document-artifact-fixture', 'document',
      'https://barreiras.mtransparente.com.br/admin/data/SERVIDORES060826145033.pdf',
      '2026-08-06 18:01:00+00', 2478977, '${"c".repeat(64)}',
      'municipal-transparency/servidores/report.pdf', 'test/1',
      '{"schema_name":"municipal-transparency-document","source_record_key":"servidores-244"}'::jsonb
    );
    insert into org.public_bodies (
      id, origin_raw_record_id, ibge_code, name, body_type, state_code
    ) values (
      '00000000-0000-0000-0000-000000009007',
      '00000000-0000-0000-0000-000000009005', '2903201',
      'Município de Barreiras', 'executive', 'BA'
    );
  `);

  await assert.rejects(
    database.exec(`
      insert into hr.payroll_report_aggregates (
        origin_raw_record_id, source_document_artifact_id, public_body_id,
        reference_month, employee_count, gross_amount, deduction_amount,
        net_amount, subtotal_count, parser_version, validated_at
      ) values (
        '00000000-0000-0000-0000-000000009005',
        '00000000-0000-0000-0000-000000009006',
        '00000000-0000-0000-0000-000000009007', '2026-07-01', 8184,
        34971971.48, 10422982.78, 1.00, 133,
        'payroll-report-aggregate/1.0.0', '2026-08-06 18:02:00+00'
      )
    `),
    /gross_amount.*deduction_amount.*net_amount|arithmetic/i,
  );

  await assert.rejects(
    database.exec(`
      insert into hr.payroll_report_aggregates (
        origin_raw_record_id, source_document_artifact_id, public_body_id,
        reference_month, employee_count, gross_amount, deduction_amount,
        net_amount, subtotal_count, parser_version, validated_at
      ) values (
        '00000000-0000-0000-0000-000000009009',
        '00000000-0000-0000-0000-000000009006',
        '00000000-0000-0000-0000-000000009007', '2026-07-01', 1,
        100.00, 10.00, 90.00, 1,
        'payroll-report-aggregate/1.0.0', '2026-08-06 18:02:00+00'
      )
    `),
    /requires an official municipal staff catalog record/,
  );

  await database.exec(`
    insert into hr.payroll_report_aggregates (
      id, origin_raw_record_id, source_document_artifact_id, public_body_id,
      reference_month, employee_count, gross_amount, deduction_amount,
      net_amount, subtotal_count, parser_version, validated_at
    ) values (
      '00000000-0000-0000-0000-000000009008',
      '00000000-0000-0000-0000-000000009005',
      '00000000-0000-0000-0000-000000009006',
      '00000000-0000-0000-0000-000000009007', '2026-07-01', 8184,
      34971971.48, 10422982.78, 24548988.70, 133,
      'payroll-report-aggregate/1.0.0', '2026-08-06 18:02:00+00'
    );
  `);

  await assert.rejects(
    database.exec(`
      update hr.payroll_report_aggregates
      set employee_count = 8185
      where id = '00000000-0000-0000-0000-000000009008'
    `),
    /immutable relation/,
  );

  await database.exec("set role anon");
  await assert.rejects(
    database.query("select * from hr.payroll_report_aggregates"),
    /permission denied/,
  );
  const publicRows = await database.query(
    "select * from api.get_public_payroll_months(24)",
  );
  await database.exec("reset role");

  assert.equal(publicRows.rows.length, 1);
  assert.deepEqual(publicRows.rows[0], {
    reference_month: "2026-07-01",
    public_body_name: "Município de Barreiras",
    employee_count: 8184,
    gross_amount: "34971971.48",
    deduction_amount: "10422982.78",
    net_amount: "24548988.70",
    subtotal_count: 133,
    source_url:
      "https://barreiras.mtransparente.com.br/admin/data/SERVIDORES060826145033.pdf",
    artifact_sha256: "c".repeat(64),
    source_retrieved_at: new Date("2026-08-06T18:01:00.000Z"),
    parser_version: "payroll-report-aggregate/1.0.0",
  });
  const serialized = JSON.stringify(publicRows.rows).toLowerCase();
  for (const forbidden of ["cpf", "nome", "matricula", "conta", "raw_record"]) {
    assert.equal(serialized.includes(forbidden), false, `campo proibido: ${forbidden}`);
  }

  await assert.rejects(
    database.query("select * from api.get_public_payroll_months(61)"),
    /limite de meses da folha invalido/,
  );
  console.log("Agregados mensais da folha: imutabilidade, linhagem e RPC segura verificados.");
} finally {
  await database.close();
}
