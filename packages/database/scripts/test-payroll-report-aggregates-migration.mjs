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
const migrationEntries = await Promise.all(
  migrationNames.map(async (name) => ({
    name,
    sql: await readFile(fileURLToPath(new URL(name, migrationsUrl)), "utf8"),
  })),
);
const strictTitleMigrationName =
  "20260822023000_strict_payroll_staff_title_lineage.sql";
const strictTitleMigrationIndex = migrationEntries.findIndex(
  ({ name }) => name === strictTitleMigrationName,
);
assert.notEqual(strictTitleMigrationIndex, -1);
const privateSelectionMigrationName =
  "20260822030000_private_payroll_document_selection.sql";
const privateSelectionMigrationIndex = migrationEntries.findIndex(
  ({ name }) => name === privateSelectionMigrationName,
);
assert.ok(privateSelectionMigrationIndex > strictTitleMigrationIndex);
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

  for (const { sql } of migrationEntries.slice(0, strictTitleMigrationIndex)) {
    await database.exec(sql);
  }

  await database.exec(`
    insert into source.data_sources (
      id, slug, name, authority_level, is_official, homepage_url
    ) values (
      '00000000-0000-0000-0000-000000009001',
      'prefeitura-barreiras-transparencia',
      'Portal da Transparência da Prefeitura de Barreiras',
      'official', true,
      'https://portaldatransparencia.barreiras.ba.gov.br/'
    );
    insert into source.source_endpoints (
      id, data_source_id, slug, endpoint_kind, base_url
    ) values (
      '00000000-0000-0000-0000-000000009002',
      '00000000-0000-0000-0000-000000009001', 'dados-abertos-api',
      'api', 'https://portaldatransparencia.barreiras.ba.gov.br/api'
    );
    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version, status
    ) values (
      '00000000-0000-0000-0000-000000008003',
      '00000000-0000-0000-0000-000000009002',
      'legacy-intern-payroll-fixture', 'test/1', 'succeeded'
    );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, idempotency_key, artifact_kind,
      source_url, retrieved_at, byte_size, sha256, object_key, collector_version
    ) values (
      '00000000-0000-0000-0000-000000008004',
      '00000000-0000-0000-0000-000000008003',
      '00000000-0000-0000-0000-000000009002',
      'legacy-intern-catalog-artifact', 'http_response',
      'https://portaldatransparencia.barreiras.ba.gov.br/api?resource=servidores',
      '2024-06-01 12:00:00+00', 100, '${"7".repeat(64)}',
      'fixtures/payroll/legacy-intern-catalog.json', 'test/1'
    );
    insert into raw.raw_records (
      id, raw_artifact_id, source_record_key, record_type, record_index,
      payload, payload_sha256, parser_version, idempotency_key, collected_at
    ) values (
      '00000000-0000-0000-0000-000000008005',
      '00000000-0000-0000-0000-000000008004', 'legacy-interns-type-one',
      'municipal_transparency_servidores', 0,
      '{"tipo":"1","titulo":"Relação de Estagiários","ano_ref":"2024","mes_ref":"5","url":"https://barreiras.mtransparente.com.br/admin/data/ESTAGIARIOS010624.pdf"}'::jsonb,
      '${"8".repeat(64)}', 'test/1', 'legacy-intern-record',
      '2024-06-01 12:00:00+00'
    );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, parent_artifact_id,
      idempotency_key, artifact_kind, source_url, retrieved_at, byte_size,
      sha256, object_key, collector_version, metadata
    ) values (
      '00000000-0000-0000-0000-000000008006',
      '00000000-0000-0000-0000-000000008003',
      '00000000-0000-0000-0000-000000009002',
      '00000000-0000-0000-0000-000000008004',
      'legacy-intern-document-artifact', 'document',
      'https://barreiras.mtransparente.com.br/admin/data/ESTAGIARIOS010624.pdf',
      '2024-06-01 12:01:00+00', 500000, '${"9".repeat(64)}',
      'municipal-transparency/servidores/legacy-interns.pdf', 'test/1',
      '{"schema_name":"municipal-transparency-document","source_record_key":"legacy-interns-type-one"}'::jsonb
    );
    insert into org.public_bodies (
      id, origin_raw_record_id, ibge_code, name, body_type, state_code
    ) values (
      '00000000-0000-0000-0000-000000008007',
      '00000000-0000-0000-0000-000000008005', '2903201',
      'Município de Barreiras', 'executive', 'BA'
    );
    insert into hr.payroll_report_aggregates (
      id, origin_raw_record_id, source_document_artifact_id, public_body_id,
      reference_month, employee_count, gross_amount, deduction_amount,
      net_amount, subtotal_count, parser_version, validated_at
    ) values (
      '00000000-0000-0000-0000-000000008008',
      '00000000-0000-0000-0000-000000008005',
      '00000000-0000-0000-0000-000000008006',
      '00000000-0000-0000-0000-000000008007', '2024-05-01', 10,
      1000.00, 100.00, 900.00, 1,
      'payroll-report-aggregate/1.2.0', '2024-06-01 12:02:00+00'
    );
    insert into raw.raw_records (
      id, raw_artifact_id, source_record_key, record_type, record_index,
      payload, payload_sha256, parser_version, idempotency_key, collected_at
    ) values (
      '00000000-0000-0000-0000-000000008009',
      '00000000-0000-0000-0000-000000008004', 'legacy-missing-title',
      'municipal_transparency_servidores', 1,
      '{"tipo":"1","ano_ref":"2024","mes_ref":"4","url":"https://barreiras.mtransparente.com.br/admin/data/SEM-TITULO010524.pdf"}'::jsonb,
      '${"a".repeat(64)}', 'test/1', 'legacy-missing-title-record',
      '2024-05-01 12:00:00+00'
    );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, parent_artifact_id,
      idempotency_key, artifact_kind, source_url, retrieved_at, byte_size,
      sha256, object_key, collector_version, metadata
    ) values (
      '00000000-0000-0000-0000-000000008010',
      '00000000-0000-0000-0000-000000008003',
      '00000000-0000-0000-0000-000000009002',
      '00000000-0000-0000-0000-000000008004',
      'legacy-missing-title-document', 'document',
      'https://barreiras.mtransparente.com.br/admin/data/SEM-TITULO010524.pdf',
      '2024-05-01 12:01:00+00', 500000, '${"b".repeat(64)}',
      'municipal-transparency/servidores/legacy-missing-title.pdf', 'test/1',
      '{"schema_name":"municipal-transparency-document","source_record_key":"legacy-missing-title"}'::jsonb
    );
    insert into hr.payroll_report_aggregates (
      id, origin_raw_record_id, source_document_artifact_id, public_body_id,
      reference_month, employee_count, gross_amount, deduction_amount,
      net_amount, subtotal_count, parser_version, validated_at
    ) values (
      '00000000-0000-0000-0000-000000008011',
      '00000000-0000-0000-0000-000000008009',
      '00000000-0000-0000-0000-000000008010',
      '00000000-0000-0000-0000-000000008007', '2024-04-01', 9,
      900.00, 90.00, 810.00, 1,
      'payroll-report-aggregate/1.2.0', '2024-05-01 12:02:00+00'
    );
  `);

  await database.exec(migrationEntries[strictTitleMigrationIndex].sql);
  for (const { sql } of migrationEntries.slice(strictTitleMigrationIndex + 1)) {
    await database.exec(sql);
  }

  const retroactiveInvalidation = await database.query(`
    select reason_code, invalidator_version
    from hr.payroll_report_aggregate_invalidations
    where aggregate_id = '00000000-0000-0000-0000-000000008008'
  `);
  assert.deepEqual(retroactiveInvalidation.rows, [
    {
      reason_code: "non_staff_catalog_title",
      invalidator_version: "payroll-title-invalidation/1.0.0",
    },
  ]);
  const missingTitleInvalidation = await database.query(`
    select reason_code, invalidator_version
    from hr.payroll_report_aggregate_invalidations
    where aggregate_id = '00000000-0000-0000-0000-000000008011'
  `);
  assert.deepEqual(missingTitleInvalidation.rows, [
    {
      reason_code: "missing_staff_catalog_title",
      invalidator_version: "payroll-title-invalidation/1.0.0",
    },
  ]);
  await database.exec("set role anon");
  const publicRowsAfterRepair = await database.query(
    "select * from api.get_public_payroll_months(24)",
  );
  await database.exec("reset role");
  assert.equal(publicRowsAfterRepair.rows.length, 0);

  const contracts = await database.query(`
    select
      to_regclass('hr.payroll_report_aggregates')::text as aggregate_table,
      to_regclass('hr.payroll_report_aggregate_invalidations')::text
        as invalidation_table,
      to_regprocedure('api.get_public_payroll_months(integer)')::text as public_rpc,
      to_regprocedure('hr.payroll_month_is_public(date)')::text
        as completion_function,
      to_regprocedure(
        'hr.get_pending_payroll_documents(integer,integer,integer,date)'
      )::text as pending_function,
      to_regprocedure('hr.payroll_unresolved_document_count(date)')::text
        as unresolved_function,
      (select relrowsecurity from pg_class
       where oid = 'hr.payroll_report_aggregates'::regclass) as rls,
      (select relforcerowsecurity from pg_class
       where oid = 'hr.payroll_report_aggregates'::regclass) as force_rls,
      (select relrowsecurity from pg_class
       where oid = 'hr.payroll_report_aggregate_invalidations'::regclass)
        as invalidation_rls,
      has_table_privilege('anon', 'hr.payroll_report_aggregates', 'SELECT')
        as anon_select,
      has_table_privilege('authenticated', 'hr.payroll_report_aggregates', 'SELECT')
        as authenticated_select,
      has_table_privilege('collector_worker', 'hr.payroll_report_aggregates', 'INSERT')
        as worker_insert,
      has_table_privilege('collector_worker', 'hr.payroll_report_aggregates', 'UPDATE')
        as worker_update,
      has_table_privilege(
        'anon', 'hr.payroll_report_aggregate_invalidations', 'SELECT'
      ) as anon_invalidation_select,
      has_table_privilege(
        'collector_worker', 'hr.payroll_report_aggregate_invalidations', 'INSERT'
      ) as worker_invalidation_insert,
      has_function_privilege(
        'anon', 'api.get_public_payroll_months(integer)', 'EXECUTE'
      ) as anon_rpc,
      has_function_privilege(
        'collector_worker', 'hr.payroll_month_is_public(date)', 'EXECUTE'
      ) as worker_completion_execute,
      has_function_privilege(
        'anon', 'hr.payroll_month_is_public(date)', 'EXECUTE'
      ) as anon_completion_execute,
      has_function_privilege(
        'authenticated', 'hr.payroll_month_is_public(date)', 'EXECUTE'
      ) as authenticated_completion_execute,
      has_function_privilege(
        'collector_worker',
        'hr.get_pending_payroll_documents(integer,integer,integer,date)',
        'EXECUTE'
      ) as worker_pending_execute,
      has_function_privilege(
        'anon',
        'hr.get_pending_payroll_documents(integer,integer,integer,date)',
        'EXECUTE'
      ) as anon_pending_execute,
      has_function_privilege(
        'authenticated',
        'hr.get_pending_payroll_documents(integer,integer,integer,date)',
        'EXECUTE'
      ) as authenticated_pending_execute,
      has_function_privilege(
        'collector_worker', 'hr.payroll_unresolved_document_count(date)',
        'EXECUTE'
      ) as worker_unresolved_execute,
      has_function_privilege(
        'anon', 'hr.payroll_unresolved_document_count(date)', 'EXECUTE'
      ) as anon_unresolved_execute,
      has_function_privilege(
        'authenticated', 'hr.payroll_unresolved_document_count(date)',
        'EXECUTE'
      ) as authenticated_unresolved_execute,
      pg_get_functiondef(
        'hr.payroll_month_is_public(date)'::regprocedure
      ) as completion_definition,
      pg_get_functiondef(
        'hr.get_pending_payroll_documents(integer,integer,integer,date)'::regprocedure
      ) as pending_definition,
      to_regclass(
        'hr.payroll_report_aggregates_series_version_unique_idx'
      )::text as series_version_index
  `);
  assert.equal(contracts.rows.length, 1);
  const [{
    completion_definition: completionDefinition,
    pending_definition: pendingDefinition,
    ...contract
  }] = contracts.rows;
  assert.match(completionDefinition, /public_body\.ibge_code = '2903201'/);
  assert.match(completionDefinition, /public_body\.body_type = 'executive'/);
  assert.match(
    pendingDefinition,
    /data_source\.slug = 'prefeitura-barreiras-transparencia'/,
  );
  assert.match(pendingDefinition, /endpoint\.slug = 'dados-abertos-api'/);
  assert.match(pendingDefinition, /payroll-report-aggregate\/1\.3\.0/);
  assert.match(pendingDefinition, /payroll_report_publication\/1\.2\.0/);
  assert.deepEqual(contract, {
    aggregate_table: "hr.payroll_report_aggregates",
    invalidation_table: "hr.payroll_report_aggregate_invalidations",
    public_rpc: "api.get_public_payroll_months(integer)",
    completion_function: "hr.payroll_month_is_public(date)",
    pending_function:
      "hr.get_pending_payroll_documents(integer,integer,integer,date)",
    unresolved_function: "hr.payroll_unresolved_document_count(date)",
    rls: true,
    force_rls: true,
    invalidation_rls: true,
    anon_select: false,
    authenticated_select: false,
    worker_insert: true,
    worker_update: false,
    anon_invalidation_select: false,
    worker_invalidation_insert: false,
    anon_rpc: true,
    worker_completion_execute: true,
    anon_completion_execute: false,
    authenticated_completion_execute: false,
    worker_pending_execute: true,
    anon_pending_execute: false,
    authenticated_pending_execute: false,
    worker_unresolved_execute: true,
    anon_unresolved_execute: false,
    authenticated_unresolved_execute: false,
    series_version_index: "hr.payroll_report_aggregates_series_version_unique_idx",
  });

  await database.exec(`
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
        '{"tipo":"1","titulo":" RELAÇÃO DE SERVIDORES ","ano_ref":"2026","mes_ref":"7","url":"https://barreiras.mtransparente.com.br/admin/data/SERVIDORES060826145033.pdf"}'::jsonb,
        '${"b".repeat(64)}', 'test/1', 'payroll-report-catalog-record-fixture',
        '2026-08-06 18:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009009',
        '00000000-0000-0000-0000-000000009004', 'estagiarios-244',
        'municipal_transparency_servidores', 1,
        '{"tipo":"1","titulo":"Relação de Estagiários","ano_ref":"2026","mes_ref":"7","url":"https://barreiras.mtransparente.com.br/admin/data/SERVIDORES060826145033.pdf"}'::jsonb,
        '${"d".repeat(64)}', 'test/1', 'payroll-intern-catalog-record-fixture',
        '2026-08-06 18:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009010',
        '00000000-0000-0000-0000-000000009004', 'servidores-245',
        'municipal_transparency_servidores', 2,
        '{"tipo":"1","titulo":"Relação de Servidores 13º Salário","ano_ref":"2026","mes_ref":"7","url":"https://barreiras.mtransparente.com.br/admin/data/SERVIDORES060826150000.pdf"}'::jsonb,
        '${"e".repeat(64)}', 'test/1', 'payroll-thirteenth-catalog-record-fixture',
        '2026-08-06 18:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009013',
        '00000000-0000-0000-0000-000000009004', 'servidores-130',
        'municipal_transparency_servidores', 3,
        '{"tipo":"","titulo":"RELAÇÃO   DE SERVIDORES","ano_ref":"2025","mes_ref":"2","url":"https://barreiras.mtransparente.com.br/admin/data/SERVIDORES120325160604.pdf"}'::jsonb,
        '${"1".repeat(64)}', 'test/1', 'payroll-historical-catalog-record-fixture',
        '2025-03-12 16:06:04+00'
      ),
      (
        '00000000-0000-0000-0000-000000009016',
        '00000000-0000-0000-0000-000000009004', 'estagiarios-untyped-130',
        'municipal_transparency_servidores', 4,
        '{"tipo":"","titulo":"Relação de Estagiários","ano_ref":"2025","mes_ref":"2","url":"https://barreiras.mtransparente.com.br/admin/data/ESTAGIARIOS120325160604.pdf"}'::jsonb,
        '${"3".repeat(64)}', 'test/1', 'payroll-untyped-intern-record-fixture',
        '2025-03-12 16:06:04+00'
      );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, parent_artifact_id,
      idempotency_key, artifact_kind, source_url, retrieved_at, byte_size,
      sha256, object_key, collector_version, metadata
    ) values
      (
        '00000000-0000-0000-0000-000000009006',
        '00000000-0000-0000-0000-000000009003',
        '00000000-0000-0000-0000-000000009002',
        '00000000-0000-0000-0000-000000009004',
        'payroll-report-document-artifact-fixture', 'document',
        'https://barreiras.mtransparente.com.br/admin/data/SERVIDORES060826145033.pdf',
        '2026-08-06 18:01:00+00', 2478977, '${"c".repeat(64)}',
        'municipal-transparency/servidores/report.pdf', 'test/1',
        '{"schema_name":"municipal-transparency-document","source_record_key":"servidores-244"}'::jsonb
      ),
      (
        '00000000-0000-0000-0000-000000009011',
        '00000000-0000-0000-0000-000000009003',
        '00000000-0000-0000-0000-000000009002',
        '00000000-0000-0000-0000-000000009004',
        'payroll-thirteenth-document-artifact-fixture', 'document',
        'https://barreiras.mtransparente.com.br/admin/data/SERVIDORES060826150000.pdf',
        '2026-08-06 18:05:00+00', 2000000, '${"f".repeat(64)}',
        'municipal-transparency/servidores/thirteenth.pdf', 'test/1',
        '{"schema_name":"municipal-transparency-document","source_record_key":"servidores-245"}'::jsonb
      ),
      (
        '00000000-0000-0000-0000-000000009014',
        '00000000-0000-0000-0000-000000009003',
        '00000000-0000-0000-0000-000000009002',
        '00000000-0000-0000-0000-000000009004',
        'payroll-historical-document-artifact-fixture', 'document',
        'https://barreiras.mtransparente.com.br/admin/data/SERVIDORES120325160604.pdf',
        '2025-03-12 16:07:00+00', 1945162, '${"2".repeat(64)}',
        'municipal-transparency/servidores/historical.pdf', 'test/1',
        '{"schema_name":"municipal-transparency-document","source_record_key":"servidores-130"}'::jsonb
      ),
      (
        '00000000-0000-0000-0000-000000009017',
        '00000000-0000-0000-0000-000000009003',
        '00000000-0000-0000-0000-000000009002',
        '00000000-0000-0000-0000-000000009004',
        'payroll-intern-document-artifact-fixture', 'document',
        'https://barreiras.mtransparente.com.br/admin/data/SERVIDORES060826145033.pdf',
        '2026-08-06 18:01:00+00', 2478977, '${"4".repeat(64)}',
        'municipal-transparency/servidores/interns.pdf', 'test/1',
        '{"schema_name":"municipal-transparency-document","source_record_key":"estagiarios-244"}'::jsonb
      );
  `);

  await database.exec(`
    insert into source.data_sources (
      id, slug, name, authority_level, is_official, homepage_url
    ) values (
      '00000000-0000-0000-0000-000000009018', 'unrelated-payroll-source',
      'Fonte alheia ao contrato municipal', 'official', true,
      'https://example.gov.br/'
    );
    insert into source.source_endpoints (
      id, data_source_id, slug, endpoint_kind, base_url
    ) values (
      '00000000-0000-0000-0000-000000009019',
      '00000000-0000-0000-0000-000000009018', 'unrelated-api',
      'api', 'https://example.gov.br/api'
    );
    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version, status
    ) values (
      '00000000-0000-0000-0000-000000009020',
      '00000000-0000-0000-0000-000000009019',
      'unrelated-payroll-run', 'test/1', 'succeeded'
    );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, idempotency_key, artifact_kind,
      source_url, retrieved_at, byte_size, sha256, object_key, collector_version
    ) values (
      '00000000-0000-0000-0000-000000009021',
      '00000000-0000-0000-0000-000000009020',
      '00000000-0000-0000-0000-000000009019',
      'unrelated-payroll-catalog', 'http_response',
      'https://example.gov.br/api/servidores', '2026-08-06 18:00:00+00',
      100, '${"5".repeat(64)}', 'fixtures/payroll/unrelated.json', 'test/1'
    );
    insert into raw.raw_records (
      id, raw_artifact_id, source_record_key, record_type, record_index,
      payload, payload_sha256, parser_version, idempotency_key, collected_at
    ) values (
      '00000000-0000-0000-0000-000000009022',
      '00000000-0000-0000-0000-000000009021', 'unrelated-staff',
      'municipal_transparency_servidores', 0,
      '{"tipo":"1","titulo":"Relação de Servidores","ano_ref":"2026","mes_ref":"7","url":"https://example.gov.br/servidores.pdf"}'::jsonb,
      '${"6".repeat(64)}', 'test/1', 'unrelated-payroll-record',
      '2026-08-06 18:00:00+00'
    );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, parent_artifact_id,
      idempotency_key, artifact_kind, source_url, retrieved_at, byte_size,
      sha256, object_key, collector_version, metadata
    ) values (
      '00000000-0000-0000-0000-000000009023',
      '00000000-0000-0000-0000-000000009020',
      '00000000-0000-0000-0000-000000009019',
      '00000000-0000-0000-0000-000000009021',
      'unrelated-payroll-document', 'document',
      'https://example.gov.br/servidores.pdf', '2026-08-06 18:01:00+00',
      1000, '${"0".repeat(64)}', 'fixtures/payroll/unrelated.pdf', 'test/1',
      '{"schema_name":"municipal-transparency-document","source_record_key":"unrelated-staff"}'::jsonb
    );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, parent_artifact_id,
      idempotency_key, artifact_kind, source_url, retrieved_at, byte_size,
      sha256, object_key, collector_version, metadata
    ) values (
      '00000000-0000-0000-0000-000000009024',
      '00000000-0000-0000-0000-000000009020',
      '00000000-0000-0000-0000-000000009019',
      '00000000-0000-0000-0000-000000009021',
      'cross-endpoint-payroll-document', 'document',
      'https://barreiras.mtransparente.com.br/admin/data/SERVIDORES060826145033.pdf',
      '2026-08-06 18:01:00+00', 2478977, '${"7".repeat(64)}',
      'fixtures/payroll/cross-endpoint.pdf', 'test/1',
      '{"schema_name":"municipal-transparency-document","source_record_key":"servidores-244"}'::jsonb
    );
  `);

  await database.exec("set role collector_worker");
  const pendingJulyDocuments = await database.query(`
    select id, parent_record_id, reference_month
    from hr.get_pending_payroll_documents(5, 2021, 2026, '2026-07-01')
  `);
  const unresolvedJulyDocuments = await database.query(`
    select hr.payroll_unresolved_document_count('2026-07-01') as count
  `);
  await database.exec("reset role");
  assert.deepEqual(pendingJulyDocuments.rows, [
    {
      id: "00000000-0000-0000-0000-000000009006",
      parent_record_id: "00000000-0000-0000-0000-000000009005",
      reference_month: new Date("2026-07-01T00:00:00.000Z"),
    },
    {
      id: "00000000-0000-0000-0000-000000009011",
      parent_record_id: "00000000-0000-0000-0000-000000009010",
      reference_month: new Date("2026-07-01T00:00:00.000Z"),
    },
  ]);
  assert.equal(unresolvedJulyDocuments.rows[0].count, 2);

  await assert.rejects(
    database.query(
      "select * from hr.get_pending_payroll_documents(21, 2021, 2026, null)",
    ),
    /limite de documentos da folha invalido/,
  );
  await assert.rejects(
    database.query(
      "select hr.payroll_unresolved_document_count('2026-07-02')",
    ),
    /competencia da folha invalida/,
  );

  await assert.rejects(
    database.exec(`
      insert into hr.payroll_report_aggregates (
        origin_raw_record_id, source_document_artifact_id, public_body_id,
        reference_month, employee_count, gross_amount, deduction_amount,
        net_amount, subtotal_count, parser_version, validated_at
      ) values (
        '00000000-0000-0000-0000-000000009022',
        '00000000-0000-0000-0000-000000009023',
        '00000000-0000-0000-0000-000000008007', '2026-07-01', 1,
        100.00, 10.00, 90.00, 1,
        'payroll-report-aggregate/1.2.0', '2026-08-06 18:02:00+00'
      )
    `),
    /requires an official municipal staff catalog record/,
  );

  await assert.rejects(
    database.exec(`
      insert into hr.payroll_report_aggregates (
        origin_raw_record_id, source_document_artifact_id, public_body_id,
        reference_month, employee_count, gross_amount, deduction_amount,
        net_amount, subtotal_count, parser_version, validated_at
      ) values (
        '00000000-0000-0000-0000-000000009005',
        '00000000-0000-0000-0000-000000009024',
        '00000000-0000-0000-0000-000000008007', '2026-07-01', 8184,
        34971971.48, 10422982.78, 24548988.70, 133,
        'payroll-report-aggregate/1.2.0', '2026-08-06 18:02:00+00'
      )
    `),
    /document does not match official catalog evidence/,
  );

  await assert.rejects(
    database.exec(`
      insert into hr.payroll_report_aggregates (
        origin_raw_record_id, source_document_artifact_id, public_body_id,
        reference_month, employee_count, gross_amount, deduction_amount,
        net_amount, subtotal_count, parser_version, validated_at
      ) values (
        '00000000-0000-0000-0000-000000009005',
        '00000000-0000-0000-0000-000000009006',
        '00000000-0000-0000-0000-000000008007', '2026-07-01', 8184,
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
        '00000000-0000-0000-0000-000000009017',
        '00000000-0000-0000-0000-000000008007', '2026-07-01', 1,
        100.00, 10.00, 90.00, 1,
        'payroll-report-aggregate/1.0.0', '2026-08-06 18:02:00+00'
      )
    `),
    /requires an official municipal staff catalog record/,
  );

  await assert.rejects(
    database.exec(`
      insert into hr.payroll_report_aggregates (
        origin_raw_record_id, source_document_artifact_id, public_body_id,
        reference_month, employee_count, gross_amount, deduction_amount,
        net_amount, subtotal_count, parser_version, validated_at
      ) values (
        '00000000-0000-0000-0000-000000009016',
        '00000000-0000-0000-0000-000000009014',
        '00000000-0000-0000-0000-000000008007', '2025-02-01', 10,
        100.00, 10.00, 90.00, 1,
        'payroll-report-aggregate/1.2.0', '2025-03-12 16:08:00+00'
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
      '00000000-0000-0000-0000-000000008007', '2026-07-01', 8184,
      34971971.48, 10422982.78, 24548988.70, 133,
      'payroll-report-aggregate/1.0.0', '2026-08-06 18:02:00+00'
    );
    insert into hr.payroll_report_aggregates (
      id, origin_raw_record_id, source_document_artifact_id, public_body_id,
      reference_month, payroll_cycle, employee_count, gross_amount,
      deduction_amount, net_amount, subtotal_count, parser_version,
      validated_at
    ) values (
      '00000000-0000-0000-0000-000000009012',
      '00000000-0000-0000-0000-000000009010',
      '00000000-0000-0000-0000-000000009011',
      '00000000-0000-0000-0000-000000008007', '2026-07-01',
      'thirteenth_advance', 8000, 5000000.00, 500000.00, 4500000.00,
      120, 'payroll-report-aggregate/1.1.0', '2026-08-06 18:06:00+00'
    );
    insert into hr.payroll_report_aggregates (
      id, origin_raw_record_id, source_document_artifact_id, public_body_id,
      reference_month, payroll_cycle, employee_count, gross_amount,
      deduction_amount, net_amount, subtotal_count, parser_version,
      validated_at
    ) values (
      '00000000-0000-0000-0000-000000009015',
      '00000000-0000-0000-0000-000000009013',
      '00000000-0000-0000-0000-000000009014',
      '00000000-0000-0000-0000-000000008007', '2025-02-01',
      'regular', 6000, 30000000.00, 10000000.00, 20000000.00,
      130, 'payroll-report-aggregate/1.2.0', '2025-03-12 16:08:00+00'
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

  await database.exec("set role collector_worker");
  const completedMonth = await database.query(
    "select hr.payroll_month_is_public('2026-07-01') as completed",
  );
  await database.exec("reset role");
  assert.equal(completedMonth.rows[0].completed, true);

  assert.equal(publicRows.rows.length, 2);
  const [publicRow, historicalRow] = publicRows.rows;
  const sourceDocuments = publicRow.source_documents;
  const historicalDocuments = historicalRow.source_documents;
  delete publicRow.source_documents;
  delete historicalRow.source_documents;
  assert.deepEqual(publicRow, {
    reference_month: "2026-07-01",
    public_body_name: "Município de Barreiras",
    employee_count: 8184,
    gross_amount: "39971971.48",
    deduction_amount: "10922982.78",
    net_amount: "29048988.70",
    subtotal_count: 253,
    document_count: 2,
    source_url:
      "https://barreiras.mtransparente.com.br/admin/data/SERVIDORES060826145033.pdf",
    artifact_sha256: "c".repeat(64),
    source_retrieved_at: new Date("2026-08-06T18:01:00.000Z"),
    parser_version: "payroll-monthly-total/1.0.0",
  });
  assert.equal(sourceDocuments.length, 2);
  assert.deepEqual(
    sourceDocuments.map(({ source_retrieved_at, ...document }) => document),
    [
      {
        payroll_cycle: "regular",
        source_url:
          "https://barreiras.mtransparente.com.br/admin/data/SERVIDORES060826145033.pdf",
        artifact_sha256: "c".repeat(64),
        parser_version: "payroll-report-aggregate/1.0.0",
      },
      {
        payroll_cycle: "thirteenth_advance",
        source_url:
          "https://barreiras.mtransparente.com.br/admin/data/SERVIDORES060826150000.pdf",
        artifact_sha256: "f".repeat(64),
        parser_version: "payroll-report-aggregate/1.1.0",
      },
    ],
  );
  assert.deepEqual(
    sourceDocuments.map((document) =>
      new Date(document.source_retrieved_at).toISOString()
    ),
    ["2026-08-06T18:01:00.000Z", "2026-08-06T18:05:00.000Z"],
  );
  assert.deepEqual(historicalRow, {
    reference_month: "2025-02-01",
    public_body_name: "Município de Barreiras",
    employee_count: 6000,
    gross_amount: "30000000.00",
    deduction_amount: "10000000.00",
    net_amount: "20000000.00",
    subtotal_count: 130,
    document_count: 1,
    source_url:
      "https://barreiras.mtransparente.com.br/admin/data/SERVIDORES120325160604.pdf",
    artifact_sha256: "2".repeat(64),
    source_retrieved_at: new Date("2025-03-12T16:07:00.000Z"),
    parser_version: "payroll-monthly-total/1.0.0",
  });
  assert.equal(historicalDocuments.length, 1);
  assert.equal(historicalDocuments[0].payroll_cycle, "regular");
  const serialized = JSON.stringify(publicRows.rows).toLowerCase();
  for (const forbidden of ["cpf", "nome", "matricula", "conta", "raw_record"]) {
    assert.equal(serialized.includes(forbidden), false, `campo proibido: ${forbidden}`);
  }

  await database.exec(`
    insert into hr.payroll_report_aggregate_invalidations (
      aggregate_id, evidence_artifact_id, reason_code, invalidator_version,
      details, invalidated_at
    ) values (
      '00000000-0000-0000-0000-000000009008',
      '00000000-0000-0000-0000-000000009006',
      'mixed_payroll_cycle_header', 'payroll-cycle-invalidation/test',
      '{"observed_header":"1-Normal, 4-Adiant. 13º"}'::jsonb,
      '2026-08-21 22:00:00+00'
    );
  `);
  await assert.rejects(
    database.exec(`
      update hr.payroll_report_aggregate_invalidations
      set reason_code = 'mixed_payroll_cycle_header'
      where aggregate_id = '00000000-0000-0000-0000-000000009008'
    `),
    /immutable relation/,
  );
  await database.exec("set role anon");
  await assert.rejects(
    database.query("select * from hr.payroll_report_aggregate_invalidations"),
    /permission denied/,
  );
  const rowsAfterInvalidation = await database.query(
    "select * from api.get_public_payroll_months(24)",
  );
  await database.exec("reset role");
  await database.exec("set role collector_worker");
  const invalidatedMonth = await database.query(
    "select hr.payroll_month_is_public('2026-07-01') as completed",
  );
  await database.exec("reset role");
  assert.equal(invalidatedMonth.rows[0].completed, false);
  assert.deepEqual(
    rowsAfterInvalidation.rows.map((row) => row.reference_month),
    ["2025-02-01"],
  );

  await assert.rejects(
    database.query("select * from api.get_public_payroll_months(61)"),
    /limite de meses da folha invalido/,
  );
  console.log("Agregados mensais da folha: imutabilidade, linhagem e RPC segura verificados.");
} finally {
  await database.close();
}
