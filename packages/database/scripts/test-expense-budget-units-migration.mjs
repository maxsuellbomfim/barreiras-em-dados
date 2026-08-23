import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { PGlite } from "@electric-sql/pglite";
import { pg_trgm } from "@electric-sql/pglite/contrib/pg_trgm";
import { pgcrypto } from "@electric-sql/pglite/contrib/pgcrypto";

const migrationsUrl = new URL("../../../supabase/migrations/", import.meta.url);
const migrationName = "20260823223000_public_expense_unit_source_conflicts.sql";
const migrationNames = (await readdir(fileURLToPath(migrationsUrl)))
  .filter((name) => name.endsWith(".sql"))
  .sort();
const migrationIndex = migrationNames.indexOf(migrationName);
assert.notEqual(migrationIndex, -1, "migration de unidades orcamentarias nao encontrada");

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
      to_regclass('finance.expense_line_budget_units')::text as allocation_table,
      to_regprocedure(
        'api.get_public_expense_budget_unit_summary(uuid)'
      )::text as public_rpc,
      has_table_privilege(
        'anon', 'finance.expense_line_budget_units', 'SELECT'
      ) as anon_table_select,
      has_table_privilege(
        'collector_worker', 'finance.expense_line_budget_units', 'INSERT'
      ) as collector_insert,
      has_function_privilege(
        'anon', 'api.get_public_expense_budget_unit_summary(uuid)', 'EXECUTE'
      ) as anon_rpc_execute,
      has_function_privilege(
        'anon',
        'api.get_public_expense_report_source_conflicts(integer,smallint)',
        'EXECUTE'
      ) as anon_conflict_rpc_execute,
      has_table_privilege(
        'anon', 'evidence.source_conflicts', 'SELECT'
      ) as anon_conflict_table_select
  `);
  assert.deepEqual(contracts.rows, [{
    allocation_table: "finance.expense_line_budget_units",
    public_rpc: "api.get_public_expense_budget_unit_summary(uuid)",
    anon_table_select: false,
    collector_insert: true,
    anon_rpc_execute: true,
    anon_conflict_rpc_execute: true,
    anon_conflict_table_select: false,
  }]);

  const rls = await database.query(`
    select relrowsecurity, relforcerowsecurity
    from pg_catalog.pg_class
    join pg_catalog.pg_namespace
      on pg_catalog.pg_namespace.oid = pg_catalog.pg_class.relnamespace
    where pg_catalog.pg_namespace.nspname = 'finance'
      and relname = 'expense_line_budget_units'
  `);
  assert.deepEqual(rls.rows, [{ relrowsecurity: true, relforcerowsecurity: true }]);

  await database.exec(`
    insert into source.data_sources (
      id, slug, name, authority_level, is_official, homepage_url
    ) values (
      '00000000-0000-0000-0000-000000007001',
      'expense-budget-unit-test', 'Fonte de teste', 'official', true,
      'https://example.org/'
    );
    insert into source.source_endpoints (
      id, data_source_id, slug, endpoint_kind, base_url
    ) values (
      '00000000-0000-0000-0000-000000007002',
      '00000000-0000-0000-0000-000000007001', 'expense-report',
      'api', 'https://example.org/api'
    );
    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version, status
    ) values (
      '00000000-0000-0000-0000-000000007003',
      '00000000-0000-0000-0000-000000007002',
      'expense-budget-unit-test-run', 'test/1', 'succeeded'
    );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, idempotency_key, artifact_kind,
      source_url, retrieved_at, byte_size, sha256, object_key, collector_version
    ) values (
      '00000000-0000-0000-0000-000000007004',
      '00000000-0000-0000-0000-000000007003',
      '00000000-0000-0000-0000-000000007002',
      'expense-budget-unit-parent-artifact', 'http_response',
      'https://example.org/api?resource=expense', '2025-02-01 12:00:00+00',
      100, '${"1".repeat(64)}', 'fixtures/expense/catalog.json', 'test/1'
    );
    insert into raw.raw_records (
      id, raw_artifact_id, source_record_key, record_type, record_index,
      payload, payload_sha256, parser_version, idempotency_key, collected_at
    ) values (
      '00000000-0000-0000-0000-000000007005',
      '00000000-0000-0000-0000-000000007004', 'expense-2025-01',
      'municipal_transparency_pdc-resumo-execucao-da-despesa', 0,
      '{"ano":"2025","mes":"1","url":"https://example.org/expense-2025-01.pdf"}'::jsonb,
      '${"2".repeat(64)}',
      'test/1', 'expense-budget-unit-record', '2025-02-01 12:00:00+00'
    );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, parent_artifact_id,
      idempotency_key, artifact_kind, source_url, retrieved_at, byte_size,
      sha256, object_key, collector_version, metadata
    ) values
    (
      '00000000-0000-0000-0000-000000007006',
      '00000000-0000-0000-0000-000000007003',
      '00000000-0000-0000-0000-000000007002',
      '00000000-0000-0000-0000-000000007004',
      'expense-budget-unit-document', 'document',
      'https://example.org/expense-2025-01.pdf', '2025-02-01 12:01:00+00',
      1000, '${"3".repeat(64)}', 'fixtures/expense/2025-01.pdf', 'test/1',
      '{"schema_name":"municipal-transparency-document","source_record_key":"expense-2025-01"}'::jsonb
    ),
    (
      '00000000-0000-0000-0000-000000007007',
      '00000000-0000-0000-0000-000000007003',
      '00000000-0000-0000-0000-000000007002',
      '00000000-0000-0000-0000-000000007004',
      'expense-budget-unit-unrelated-document', 'document',
      'https://example.org/unrelated.pdf', '2025-02-01 12:01:00+00',
      1000, '${"4".repeat(64)}', 'fixtures/expense/unrelated.pdf', 'test/1',
      '{"schema_name":"municipal-transparency-document","source_record_key":"expense-2025-01"}'::jsonb
    );
    insert into org.public_bodies (
      id, origin_raw_record_id, ibge_code, name, body_type, state_code
    ) values (
      '00000000-0000-0000-0000-000000007008',
      '00000000-0000-0000-0000-000000007005', '2903201',
      'Município de Barreiras', 'executive', 'BA'
    );
    insert into finance.expense_reports (
      id, origin_raw_record_id, source_document_artifact_id, public_body_id,
      fiscal_year, period_start, period_end, total_fixed_amount,
      total_additions_amount, total_reductions_amount, total_updated_amount,
      total_committed_period_amount, total_committed_to_date_amount,
      total_liquidated_period_amount, total_liquidated_to_date_amount,
      total_paid_period_amount, total_paid_to_date_amount,
      total_unpaid_committed_amount, total_balance_amount,
      validation_status, published_at
    ) values (
      '00000000-0000-0000-0000-000000007009',
      '00000000-0000-0000-0000-000000007005',
      '00000000-0000-0000-0000-000000007006',
      '00000000-0000-0000-0000-000000007008',
      2025, '2025-01-01', '2025-01-31', 100, 0, 0, 100,
      100, 100, 100, 100, 100, 100, 0, 0,
      'validated', '2025-02-01 12:02:00+00'
    );
    insert into finance.expense_lines (
      id, report_id, origin_raw_record_id, line_number, expense_code,
      description, source_code, fixed_amount, additions_amount,
      reductions_amount, updated_amount, committed_period_amount,
      committed_to_date_amount, liquidated_period_amount,
      liquidated_to_date_amount, paid_period_amount, paid_to_date_amount,
      unpaid_committed_amount, balance_amount
    ) values
    (
      '00000000-0000-0000-0000-000000007010',
      '00000000-0000-0000-0000-000000007009',
      '00000000-0000-0000-0000-000000007005', 1,
      '3.3.9.0.30.00.00', 'Material de consumo', '1500',
      60, 0, 0, 60, 60, 60, 60, 60, 60, 60, 0, 0
    ),
    (
      '00000000-0000-0000-0000-000000007011',
      '00000000-0000-0000-0000-000000007009',
      '00000000-0000-0000-0000-000000007005', 2,
      '3.3.9.0.39.00.00', 'Serviços de terceiros', '1500',
      40, 0, 0, 40, 40, 40, 40, 40, 40, 40, 0, 0
    );
    insert into finance.expense_line_budget_units (
      expense_line_id, origin_raw_record_id, source_document_artifact_id,
      budget_unit_code, budget_unit_name, methodology_version
    ) values
    (
      '00000000-0000-0000-0000-000000007010',
      '00000000-0000-0000-0000-000000007005',
      '00000000-0000-0000-0000-000000007006',
      '030501', 'SECRETARIA MUNICIPAL DE ADMINISTRAÇÃO',
      'public-expense-pdf/1.1.0'
    ),
    (
      '00000000-0000-0000-0000-000000007011',
      '00000000-0000-0000-0000-000000007005',
      '00000000-0000-0000-0000-000000007006',
      '031101', 'SECRETARIA MUNICIPAL DE SAÚDE',
      'public-expense-pdf/1.1.0'
    );
  `);

  await database.exec("set role collector_worker");
  await database.exec(`
    insert into evidence.evidence_items (
      id, target_type, target_id, raw_artifact_id, raw_record_id,
      evidence_kind, source_url, excerpt, locator, content_sha256,
      parser_version, is_primary
    ) values
    (
      '00000000-0000-0000-0000-000000007012',
      'finance.expense_reports',
      '00000000-0000-0000-0000-000000007009',
      '00000000-0000-0000-0000-000000007006',
      '00000000-0000-0000-0000-000000007005',
      'document', 'https://example.org/expense-2025-01.pdf',
      'Total geral declarado', '{"section":"Total"}'::jsonb,
      '${"3".repeat(64)}', 'public-expense-pdf/1.4.0', true
    ),
    (
      '00000000-0000-0000-0000-000000007013',
      'finance.expense_reports',
      '00000000-0000-0000-0000-000000007009',
      '00000000-0000-0000-0000-000000007006',
      '00000000-0000-0000-0000-000000007005',
      'document', 'https://example.org/expense-2025-01.pdf',
      'Soma conferida por unidade', '{"section":"Total da Unidade"}'::jsonb,
      '${"3".repeat(64)}', 'public-expense-pdf/1.4.0', true
    ),
    (
      '00000000-0000-0000-0000-000000007014',
      'finance.expense_reports',
      '00000000-0000-0000-0000-000000007009',
      '00000000-0000-0000-0000-000000007006',
      '00000000-0000-0000-0000-000000007005',
      'document', 'https://example.org/expense-2025-01.pdf',
      'Subtotal oficial da unidade 030850',
      '{"section":"Total da Unidade"}'::jsonb,
      '${"3".repeat(64)}', 'public-expense-pdf/1.4.0', true
    ),
    (
      '00000000-0000-0000-0000-000000007015',
      'finance.expense_reports',
      '00000000-0000-0000-0000-000000007009',
      '00000000-0000-0000-0000-000000007006',
      '00000000-0000-0000-0000-000000007005',
      'document', 'https://example.org/expense-2025-01.pdf',
      'Soma das linhas da unidade 030850',
      '{"section":"Linhas da Unidade"}'::jsonb,
      '${"3".repeat(64)}', 'public-expense-pdf/1.4.0', true
    );
    insert into evidence.source_conflicts (
      target_type, target_id, field_name,
      first_evidence_item_id, second_evidence_item_id,
      first_value, second_value, status
    ) values
    (
      'finance.expense_reports',
      '00000000-0000-0000-0000-000000007009',
      'total_reductions_amount',
      '00000000-0000-0000-0000-000000007012',
      '00000000-0000-0000-0000-000000007013',
      '{"declared_amount":"263599171.60"}'::jsonb,
      '{"calculated_amount":"263599171.68","difference_amount":"0.08"}'::jsonb,
      'open'
    ),
    (
      'finance.expense_reports',
      '00000000-0000-0000-0000-000000007009',
      'budget_unit_subtotal:030850:reductions_amount',
      '00000000-0000-0000-0000-000000007014',
      '00000000-0000-0000-0000-000000007015',
      '{"scope":"budget_unit_subtotal","field_name":"reductions_amount","budget_unit_code":"030850","budget_unit_name":"FME - FUNDO MUNICIPAL DE EDUCAÇÃO","declared_amount":"141419262.90"}'::jsonb,
      '{"scope":"budget_unit_subtotal","field_name":"reductions_amount","budget_unit_code":"030850","budget_unit_name":"FME - FUNDO MUNICIPAL DE EDUCAÇÃO","calculated_amount":"141419262.97","difference_amount":"0.07"}'::jsonb,
      'open'
    );
  `);
  await database.exec("reset role");

  await database.exec("set role anon");
  const summary = await database.query(`
    select budget_unit_code, budget_unit_name, paid_period_amount,
      reconciliation_status, paid_share_percent
    from api.get_public_expense_budget_unit_summary(
      '00000000-0000-0000-0000-000000007009'
    )
    order by budget_unit_code
  `);
  await database.exec("reset role");
  assert.deepEqual(summary.rows, [
    {
      budget_unit_code: "030501",
      budget_unit_name: "SECRETARIA MUNICIPAL DE ADMINISTRAÇÃO",
      paid_period_amount: "60.00",
      reconciliation_status: "matched",
      paid_share_percent: "60.00",
    },
    {
      budget_unit_code: "031101",
      budget_unit_name: "SECRETARIA MUNICIPAL DE SAÚDE",
      paid_period_amount: "40.00",
      reconciliation_status: "matched",
      paid_share_percent: "40.00",
    },
  ]);

  await database.exec("set role anon");
  const sourceConflicts = await database.query(`
    select fiscal_year, period_start::text, conflict_scope, field_name,
      budget_unit_code, budget_unit_name, declared_amount,
      calculated_amount, difference_amount, methodology_version
    from api.get_public_expense_report_source_conflicts(100, 2025::smallint)
  `);
  await database.exec("reset role");
  assert.deepEqual(sourceConflicts.rows, [
    {
      fiscal_year: 2025,
      period_start: "2025-01-01",
      conflict_scope: "budget_unit_subtotal",
      field_name: "reductions_amount",
      budget_unit_code: "030850",
      budget_unit_name: "FME - FUNDO MUNICIPAL DE EDUCAÇÃO",
      declared_amount: "141419262.90",
      calculated_amount: "141419262.97",
      difference_amount: "0.07",
      methodology_version: "public-expense-source-conflicts/1.1.0",
    },
    {
      fiscal_year: 2025,
      period_start: "2025-01-01",
      conflict_scope: "report_total",
      field_name: "total_reductions_amount",
      budget_unit_code: null,
      budget_unit_name: null,
      declared_amount: "263599171.60",
      calculated_amount: "263599171.68",
      difference_amount: "0.08",
      methodology_version: "public-expense-source-conflicts/1.1.0",
    },
  ]);

  await assert.rejects(
    database.exec(`
      insert into finance.expense_line_budget_units (
        expense_line_id, origin_raw_record_id, source_document_artifact_id,
        version, budget_unit_code, budget_unit_name, methodology_version
      ) values (
        '00000000-0000-0000-0000-000000007010',
        '00000000-0000-0000-0000-000000007005',
        '00000000-0000-0000-0000-000000007007', 2,
        '030501', 'SECRETARIA MUNICIPAL DE ADMINISTRAÇÃO',
        'public-expense-pdf/1.1.0'
      )
    `),
    /linhagem da unidade orcamentaria diverge/i,
  );

  console.log("Unidades orcamentarias de despesa: contrato, RLS e RPC validados.");
} finally {
  await database.close();
}
