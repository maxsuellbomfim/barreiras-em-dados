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
      ('c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a'),
      ('00000000-0000-4000-8000-000000000001');
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
    ) values
      (
        '00000000-0000-0000-0000-000000008003',
        '00000000-0000-0000-0000-000000008002', 'balancete-2026-06',
        'municipal_transparency_balancetes', 0,
        '{"titulo":"BALANCETE JUNHO 2026","ano":"2026","mes":"6","url":"https://portaldatransparencia.barreiras.ba.gov.br/documentos/balancete-junho-2026.pdf"}'::jsonb,
        '${"b".repeat(64)}', 'test/1', 'public-obligation-record-fixture',
        '2026-08-11 16:40:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000008008',
        '00000000-0000-0000-0000-000000008002', 'balancete-2026-05',
        'municipal_transparency_balancetes', 1,
        '{"titulo":"BALANCETE MAIO 2026","ano":"2026","mes":"5","url":"https://portaldatransparencia.barreiras.ba.gov.br/documentos/balancete-maio-2026.pdf"}'::jsonb,
        '${"c".repeat(64)}', 'test/1', 'public-obligation-record-fixture-may',
        '2026-08-11 16:40:00+00'
      );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, parent_artifact_id,
      idempotency_key, artifact_kind, source_url, retrieved_at, byte_size,
      sha256, object_key, collector_version, metadata, created_at
    ) values
      (
        '00000000-0000-0000-0000-000000008009',
        '00000000-0000-0000-0000-000000008001',
        '00000000-0000-4000-8000-000000000102',
        '00000000-0000-0000-0000-000000008002',
        'public-obligation-document-june', 'document',
        'https://portaldatransparencia.barreiras.ba.gov.br/documentos/balancete-junho-2026.pdf',
        '2026-08-11 16:41:00+00', 200, '${"d".repeat(64)}',
        'fixtures/balancete-junho-2026.pdf', 'test/1',
        '{"schema_name":"municipal-transparency-document","source_record_key":"balancete-2026-06"}'::jsonb,
        '2026-08-11 16:41:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000008010',
        '00000000-0000-0000-0000-000000008001',
        '00000000-0000-4000-8000-000000000102',
        '00000000-0000-0000-0000-000000008002',
        'public-obligation-document-may', 'document',
        'https://portaldatransparencia.barreiras.ba.gov.br/documentos/balancete-maio-2026.pdf',
        '2026-08-11 16:42:00+00', 300, '${"e".repeat(64)}',
        'fixtures/balancete-maio-2026.pdf', 'test/1',
        '{"schema_name":"municipal-transparency-document","source_record_key":"balancete-2026-05"}'::jsonb,
        '2026-08-11 16:42:00+00'
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
    insert into finance.revenues (
      id, origin_raw_record_id, public_body_id, version, external_id,
      fiscal_year, revenue_date, revenue_code, description, forecast_amount,
      collected_amount, accumulated_amount, report_total_period_amount,
      collection_direction, methodology_version, validation_status,
      published_at, source_document_artifact_id
    ) values
      (
        '00000000-0000-0000-0000-000000008011',
        '00000000-0000-0000-0000-000000008003',
        '00000000-0000-0000-0000-000000008004', 1, 'revenue-exact',
        2026, '2026-06-30', '1.0', 'Receita com evidência exata', 1000,
        900, 900, 900, 'credit', 'test/1', 'validated',
        '2026-08-11 16:45:00+00',
        '00000000-0000-0000-0000-000000008009'
      ),
      (
        '00000000-0000-0000-0000-000000008012',
        '00000000-0000-0000-0000-000000008003',
        '00000000-0000-0000-0000-000000008004', 1, 'revenue-mismatch',
        2026, '2026-06-30', '2.0', 'Receita com evidência trocada', 2000,
        1800, 1800, 1800, 'credit', 'test/1', 'validated',
        '2026-08-11 16:45:00+00',
        '00000000-0000-0000-0000-000000008010'
      );
    insert into finance.expense_reports (
      id, origin_raw_record_id, source_document_artifact_id, public_body_id,
      version, external_id, fiscal_year, period_start, period_end,
      total_fixed_amount, total_additions_amount, total_reductions_amount,
      total_updated_amount, total_committed_period_amount,
      total_committed_to_date_amount, total_liquidated_period_amount,
      total_liquidated_to_date_amount, total_paid_period_amount,
      total_paid_to_date_amount, total_unpaid_committed_amount,
      total_balance_amount, methodology_version, validation_status, published_at
    ) values
      (
        '00000000-0000-0000-0000-000000008013',
        '00000000-0000-0000-0000-000000008003',
        '00000000-0000-0000-0000-000000008009',
        '00000000-0000-0000-0000-000000008004', 1, 'expense-exact',
        2026, '2026-06-01', '2026-06-30', 1000, 0, 0, 1000,
        800, 800, 700, 700, 600, 600, 200, 200,
        'test/1', 'validated', '2026-08-11 16:45:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000008014',
        '00000000-0000-0000-0000-000000008003',
        '00000000-0000-0000-0000-000000008010',
        '00000000-0000-0000-0000-000000008004', 1, 'expense-mismatch',
        2026, '2026-06-01', '2026-06-30', 2000, 0, 0, 2000,
        1600, 1600, 1400, 1400, 1200, 1200, 400, 400,
        'test/1', 'validated', '2026-08-11 16:45:00+00'
      );
    insert into finance.expense_lines (
      id, report_id, origin_raw_record_id, line_number, expense_code,
      description, source_code, fixed_amount, additions_amount,
      reductions_amount, updated_amount, committed_period_amount,
      committed_to_date_amount, liquidated_period_amount,
      liquidated_to_date_amount, paid_period_amount, paid_to_date_amount,
      unpaid_committed_amount, balance_amount, methodology_version
    ) values
      (
        '00000000-0000-0000-0000-000000008015',
        '00000000-0000-0000-0000-000000008013',
        '00000000-0000-0000-0000-000000008003', 1, '3.3.90',
        'Linha com evidência exata', 'fixture', 1000, 0, 0, 1000,
        800, 800, 700, 700, 600, 600, 200, 200, 'test/1'
      ),
      (
        '00000000-0000-0000-0000-000000008016',
        '00000000-0000-0000-0000-000000008014',
        '00000000-0000-0000-0000-000000008003', 1, '4.4.90',
        'Linha com evidência trocada', 'fixture', 2000, 0, 0, 2000,
        1600, 1600, 1400, 1400, 1200, 1200, 400, 400, 'test/1'
      );
    insert into analysis.anomaly_findings (
      id, origin_raw_record_id, anomaly_rule_id, target_type, target_id,
      version, deterministic_inputs, deterministic_output, status,
      public_explanation
    ) values
      (
        '00000000-0000-0000-0000-000000008017',
        '00000000-0000-0000-0000-000000008003',
        (select id from analysis.anomaly_rules
          where slug = 'finance-accounting-consistency' and version = 1),
        'finance.expense_report',
        '00000000-0000-0000-0000-000000008013', 1,
        '{"fixture":"exact"}'::jsonb,
        '{"signal":true}'::jsonb, 'triage',
        'Sinal de teste com evidência exata.'
      ),
      (
        '00000000-0000-0000-0000-000000008018',
        '00000000-0000-0000-0000-000000008003',
        (select id from analysis.anomaly_rules
          where slug = 'finance-accounting-consistency' and version = 1),
        'finance.expense_report',
        '00000000-0000-0000-0000-000000008014', 1,
        '{"fixture":"mismatch"}'::jsonb,
        '{"signal":true}'::jsonb, 'triage',
        'Sinal de teste com evidência trocada.'
      );
  `);

  const firstLineageRepair = await database.query(`
    select * from finance.repair_historical_document_lineage()
  `);
  assert.deepEqual(firstLineageRepair.rows, [{
    repaired_lineages: 1,
    affected_revenues: 1,
    affected_expense_reports: 1,
    affected_expense_lines: 1,
    conflicts_recorded: 1,
  }]);

  const secondLineageRepair = await database.query(`
    select * from finance.repair_historical_document_lineage()
  `);
  assert.deepEqual(secondLineageRepair.rows, [{
    repaired_lineages: 0,
    affected_revenues: 0,
    affected_expense_reports: 0,
    affected_expense_lines: 0,
    conflicts_recorded: 0,
  }]);

  const repairedHistory = await database.query(`
    select original_lineage_version_id, corrected_lineage_version_id,
      original_raw_record_id, corrected_raw_record_id,
      document_artifact_id, document_source_record_key,
      document_artifact_sha256, affected_revenue_count,
      affected_expense_report_count, affected_expense_line_count,
      repair_methodology
    from audit.finance_lineage_repairs
  `);
  assert.equal(repairedHistory.rows.length, 1);
  assert.deepEqual({
    original_raw_record_id: repairedHistory.rows[0].original_raw_record_id,
    corrected_raw_record_id: repairedHistory.rows[0].corrected_raw_record_id,
    document_artifact_id: repairedHistory.rows[0].document_artifact_id,
    document_source_record_key: repairedHistory.rows[0].document_source_record_key,
    document_artifact_sha256: repairedHistory.rows[0].document_artifact_sha256,
    affected_revenue_count: repairedHistory.rows[0].affected_revenue_count,
    affected_expense_report_count: repairedHistory.rows[0].affected_expense_report_count,
    affected_expense_line_count: repairedHistory.rows[0].affected_expense_line_count,
    repair_methodology: repairedHistory.rows[0].repair_methodology,
  }, {
    original_raw_record_id: "00000000-0000-0000-0000-000000008003",
    corrected_raw_record_id: "00000000-0000-0000-0000-000000008008",
    document_artifact_id: "00000000-0000-0000-0000-000000008010",
    document_source_record_key: "balancete-2026-05",
    document_artifact_sha256: "e".repeat(64),
    affected_revenue_count: 1,
    affected_expense_report_count: 1,
    affected_expense_line_count: 1,
    repair_methodology: "finance-lineage-repair/1.0.0",
  });
  assert.equal(
    repairedHistory.rows[0].corrected_lineage_version_id !==
      repairedHistory.rows[0].original_lineage_version_id,
    true,
  );

  const preservedAndCorrected = await database.query(`
    select
      (select count(*)::integer from finance.revenues
       where id = '00000000-0000-0000-0000-000000008012') as old_revenue,
      (select count(*)::integer from finance.revenues
       where supersedes_id = '00000000-0000-0000-0000-000000008012')
         as cloned_revenue,
      (select count(*)::integer from finance.expense_reports
       where id = '00000000-0000-0000-0000-000000008014') as old_report,
      (select count(*)::integer from finance.expense_reports
       where supersedes_id = '00000000-0000-0000-0000-000000008014')
         as cloned_report,
      (select count(*)::integer from finance.expense_lines
       where report_id <> '00000000-0000-0000-0000-000000008014'
         and description = 'Linha com evidÃªncia trocada') as cloned_lines,
      finance.resolve_document_origin(
        '00000000-0000-0000-0000-000000008003',
        '00000000-0000-0000-0000-000000008010'
      ) as resolved_origin,
      finance.has_exact_document_lineage(
        '00000000-0000-0000-0000-000000008003',
        '00000000-0000-0000-0000-000000008010'
      ) as reconciled,
      (select count(*)::integer from evidence.source_conflicts
       where field_name = 'origin_raw_record_id'
         and status = 'resolved') as resolved_conflicts
  `);
  assert.deepEqual(preservedAndCorrected.rows, [{
    old_revenue: 1,
    cloned_revenue: 0,
    old_report: 1,
    cloned_report: 0,
    cloned_lines: 0,
    resolved_origin: "00000000-0000-0000-0000-000000008008",
    reconciled: true,
    resolved_conflicts: 1,
  }]);

  await database.exec(`
    insert into audit.reviewer_identities (
      auth_user_id,
      display_name,
      status,
      activated_at
    ) values (
      '00000000-0000-4000-8000-000000000001',
      'Revisor financeiro de teste',
      'active',
      statement_timestamp()
    ) on conflict (auth_user_id) do update
      set status = 'active', activated_at = excluded.activated_at;
    set role authenticated;
    set request.jwt.claim.sub = '00000000-0000-4000-8000-000000000001';
  `);
  const adminFinanceIntegrity = await database.query(`
    select
      revenue_document_count,
      revenue_row_count,
      revenue_direct_count,
      revenue_reconciled_count,
      revenue_pending_count,
      expense_document_count,
      expense_report_count,
      expense_line_count,
      expense_direct_count,
      expense_reconciled_count,
      expense_pending_count,
      diagnostic_status,
      methodology_version
    from api.get_admin_finance_integrity(
      120,
      2026::smallint,
      2026::smallint
    )
    where period_start = '2026-06-01'
  `);
  await database.exec("reset role");
  assert.deepEqual(adminFinanceIntegrity.rows, [{
    revenue_document_count: 2,
    revenue_row_count: 2,
    revenue_direct_count: 1,
    revenue_reconciled_count: 1,
    revenue_pending_count: 0,
    expense_document_count: 2,
    expense_report_count: 2,
    expense_line_count: 2,
    expense_direct_count: 1,
    expense_reconciled_count: 1,
    expense_pending_count: 0,
    diagnostic_status: "needs_review",
    methodology_version: "admin-finance-integrity/1.0.0",
  }]);

  await database.exec("set role anon");
  await rejects("select * from finance.public_obligations", /permission denied/);
  await rejects(
    "select * from finance.repair_historical_document_lineage()",
    /permission denied/,
  );
  await rejects("select * from finance.document_lineage_versions", /permission denied/);
  await rejects("select * from audit.finance_lineage_repairs", /permission denied/);
  await rejects(
    "select * from api.get_admin_finance_integrity(120, 2026::smallint, 2026::smallint)",
    /permission denied/,
  );
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

  const financeDocuments = await database.query(`
    select document_id, reference_month, document_artifact_sha256
    from api.get_public_finance_documents(20, 'balancetes')
    order by reference_month
  `);
  assert.deepEqual(financeDocuments.rows, [
    {
      document_id: "00000000-0000-0000-0000-000000008008",
      reference_month: 5,
      document_artifact_sha256: "e".repeat(64),
    },
    {
      document_id: "00000000-0000-0000-0000-000000008003",
      reference_month: 6,
      document_artifact_sha256: "d".repeat(64),
    },
  ]);

  const publicRevenues = await database.query(`
    select description from api.get_public_revenues(20, 2026::smallint)
    order by description
  `);
  assert.deepEqual(publicRevenues.rows, [
    { description: "Receita com evidência exata" },
    { description: "Receita com evidência trocada" },
  ]);

  const publicExpenseReports = await database.query(`
    select total_paid_period_amount
    from api.get_public_expense_reports(20, 2026::smallint)
    order by total_paid_period_amount
  `);
  assert.deepEqual(publicExpenseReports.rows, [
    { total_paid_period_amount: "600.00" },
    { total_paid_period_amount: "1200.00" },
  ]);

  const publicExpenseLines = await database.query(`
    select description from api.get_public_expense_lines(null, 20, 0)
    order by description
  `);
  assert.deepEqual(publicExpenseLines.rows, [
    { description: "Linha com evidência exata" },
    { description: "Linha com evidência trocada" },
  ]);

  const publicMonthlyClosure = await database.query(`
    select
      revenue_report_amount,
      revenue_report_count,
      revenue_line_count,
      expense_paid_amount,
      expense_report_count,
      closure_status,
      calculation_methodology
    from api.get_public_monthly_finance_closures(24, 2026::smallint)
    where period_start = '2026-06-01'
  `);
  assert.deepEqual(publicMonthlyClosure.rows, [{
    revenue_report_amount: "2700.00",
    revenue_report_count: 2,
    revenue_line_count: 2,
    expense_paid_amount: "1200.00",
    expense_report_count: 2,
    closure_status: "needs_review",
    calculation_methodology: "monthly-finance-closure/1.1.0",
  }]);

  const publicFinanceCoverage = await database.query(`
    select
      revenue_report_count,
      expense_report_count,
      coverage_status,
      calculation_methodology
    from api.get_public_finance_coverage(
      120,
      2026::smallint,
      2026::smallint
    )
    where period_start = '2026-06-01'
  `);
  assert.deepEqual(publicFinanceCoverage.rows, [{
    revenue_report_count: 2,
    expense_report_count: 2,
    coverage_status: "needs_review",
    calculation_methodology: "finance-coverage/1.1.0",
  }]);

  const publicFinanceSignals = await database.query(`
    select finding_id from api.get_public_finance_signals(20)
    order by finding_id
  `);
  assert.deepEqual(publicFinanceSignals.rows, [
    { finding_id: "00000000-0000-0000-0000-000000008017" },
    { finding_id: "00000000-0000-0000-0000-000000008018" },
  ]);

  const internalLineageAcl = await database.query(`
    select
      has_function_privilege(
        'anon',
        'finance.has_exact_document_lineage(uuid,uuid)',
        'execute'
      ) as anon_can_execute,
      has_function_privilege(
        'authenticated',
        'finance.has_exact_document_lineage(uuid,uuid)',
        'execute'
      ) as authenticated_can_execute,
      has_function_privilege(
        'anon',
        'finance.resolve_document_origin(uuid,uuid)',
        'execute'
      ) as anon_can_resolve,
      has_function_privilege(
        'authenticated',
        'finance.has_direct_document_lineage(uuid,uuid)',
        'execute'
      ) as authenticated_can_check_direct
  `);
  assert.deepEqual(internalLineageAcl.rows, [{
    anon_can_execute: false,
    authenticated_can_execute: false,
    anon_can_resolve: false,
    authenticated_can_check_direct: false,
  }]);

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
