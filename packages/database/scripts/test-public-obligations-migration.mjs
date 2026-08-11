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
    select revenue_id from api.get_public_revenues(20, 2026::smallint)
    order by revenue_id
  `);
  assert.deepEqual(publicRevenues.rows, [{
    revenue_id: "00000000-0000-0000-0000-000000008011",
  }]);

  const publicExpenseReports = await database.query(`
    select expense_report_id from api.get_public_expense_reports(20, 2026::smallint)
    order by expense_report_id
  `);
  assert.deepEqual(publicExpenseReports.rows, [{
    expense_report_id: "00000000-0000-0000-0000-000000008013",
  }]);

  const publicExpenseLines = await database.query(`
    select expense_line_id from api.get_public_expense_lines(null, 20, 0)
    order by expense_line_id
  `);
  assert.deepEqual(publicExpenseLines.rows, [{
    expense_line_id: "00000000-0000-0000-0000-000000008015",
  }]);

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
    revenue_report_amount: "900.00",
    revenue_report_count: 1,
    revenue_line_count: 1,
    expense_paid_amount: "600.00",
    expense_report_count: 1,
    closure_status: "operational",
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
    revenue_report_count: 1,
    expense_report_count: 1,
    coverage_status: "complete",
    calculation_methodology: "finance-coverage/1.1.0",
  }]);

  const publicFinanceSignals = await database.query(`
    select finding_id from api.get_public_finance_signals(20)
    order by finding_id
  `);
  assert.deepEqual(publicFinanceSignals.rows, [{
    finding_id: "00000000-0000-0000-0000-000000008017",
  }]);

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
      ) as authenticated_can_execute
  `);
  assert.deepEqual(internalLineageAcl.rows, [{
    anon_can_execute: false,
    authenticated_can_execute: false,
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
