import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { PGlite } from "@electric-sql/pglite";
import { pg_trgm } from "@electric-sql/pglite/contrib/pg_trgm";
import { pgcrypto } from "@electric-sql/pglite/contrib/pgcrypto";

const migrationsUrl = new URL("../../../supabase/migrations/", import.meta.url);
const migrationName = "20260901133000_tcm_ba_expense_exact_lineage.sql";
const migrationNames = (await readdir(fileURLToPath(migrationsUrl)))
  .filter((name) => name.endsWith(".sql"))
  .sort();
assert.ok(migrationNames.includes(migrationName));
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

  await database.exec(`
    insert into source.data_sources (
      id, slug, name, authority_level, is_official, homepage_url
    ) values (
      '00000000-0000-0000-0000-000000009601',
      'tcm-lineage-test', 'TCM-BA teste', 'official', true,
      'https://e.tcm.ba.gov.br/'
    );
    insert into source.source_endpoints (
      id, data_source_id, slug, endpoint_kind, base_url
    ) values (
      '00000000-0000-0000-0000-000000009602',
      '00000000-0000-0000-0000-000000009601',
      'monthly-documents', 'api',
      'https://e.tcm.ba.gov.br/epp/ConsultaPublica/listView.seam'
    );
    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version, status
    ) values (
      '00000000-0000-0000-0000-000000009603',
      '00000000-0000-0000-0000-000000009602',
      'tcm-lineage-test-run', 'test/1', 'succeeded'
    );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, idempotency_key,
      artifact_kind, source_url, retrieved_at, byte_size, sha256,
      object_key, collector_version, metadata
    ) values (
      '00000000-0000-0000-0000-000000009604',
      '00000000-0000-0000-0000-000000009603',
      '00000000-0000-0000-0000-000000009602',
      'tcm-lineage-catalog', 'http_response',
      'https://e.tcm.ba.gov.br/epp/ConsultaPublica/listView.seam',
      '2023-05-18 12:00:00+00', 100, '${"1".repeat(64)}',
      'tcm-ba/monthly/2023/04/catalog.html', 'test/1',
      '{"schema_name":"tcm-ba-monthly-public-accounts-interaction"}'::jsonb
    );
    insert into raw.raw_records (
      id, raw_artifact_id, source_record_key, record_type, record_index,
      payload, payload_sha256, parser_version, idempotency_key, collected_at
    ) values
    (
      '00000000-0000-0000-0000-000000009605',
      '00000000-0000-0000-0000-000000009604',
      'tcm-ba:document:04/2023:expense', 'tcm_ba_monthly_document', 0,
      '{"category":"PCMGE015 - Demonstrativo analítico de despesa orçamentária, gerado pelo SIGA","unit":"Prefeitura Municipal de BARREIRAS","competence":"04/2023","source_url":"https://e.tcm.ba.gov.br/epp/ConsultaPublica/listView.seam"}'::jsonb,
      '${"2".repeat(64)}', 'test/1', 'tcm-lineage-expense-record',
      '2023-05-18 12:00:00+00'
    ),
    (
      '00000000-0000-0000-0000-000000009606',
      '00000000-0000-0000-0000-000000009604',
      'tcm-ba:document:04/2023:revenue', 'tcm_ba_monthly_document', 1,
      '{"category":"PCMGE016 - Demonstrativo analítico de receita orçamentária, gerado pelo SIGA","unit":"Prefeitura Municipal de BARREIRAS","competence":"04/2023","source_url":"https://e.tcm.ba.gov.br/epp/ConsultaPublica/listView.seam"}'::jsonb,
      '${"3".repeat(64)}', 'test/1', 'tcm-lineage-revenue-record',
      '2023-05-18 12:00:00+00'
    );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, parent_artifact_id,
      idempotency_key, artifact_kind, source_url, retrieved_at, byte_size,
      sha256, object_key, collector_version, metadata
    ) values
    (
      '00000000-0000-0000-0000-000000009607',
      '00000000-0000-0000-0000-000000009603',
      '00000000-0000-0000-0000-000000009602',
      '00000000-0000-0000-0000-000000009604',
      'tcm-lineage-prepare', 'document',
      'https://e.tcm.ba.gov.br/epp/ConsultaPublica/listView.seam',
      '2023-05-18 12:01:00+00', 200, '${"4".repeat(64)}',
      'tcm-ba/monthly/2023/04/prepare.xml', 'test/1',
      '{"schema_name":"tcm-ba-document-download-prepare","document_role":"download-prepare","source_record_key":"tcm-ba:document:04/2023:expense"}'::jsonb
    ),
    (
      '00000000-0000-0000-0000-000000009608',
      '00000000-0000-0000-0000-000000009603',
      '00000000-0000-0000-0000-000000009602',
      '00000000-0000-0000-0000-000000009607',
      'tcm-lineage-pdf-artifact', 'document',
      'https://e.tcm.ba.gov.br/epp/PdfReadOnly/downloadDocumento.seam',
      '2023-05-18 12:02:00+00', 1000, '${"5".repeat(64)}',
      'tcm-ba/monthly/2023/04/expense.pdf', 'test/1',
      '{"schema_name":"tcm-ba-monthly-document","document_role":"pdf","source_record_key":"tcm-ba:document:04/2023:expense"}'::jsonb
    ),
    (
      '00000000-0000-0000-0000-000000009611',
      '00000000-0000-0000-0000-000000009603',
      '00000000-0000-0000-0000-000000009602',
      '00000000-0000-0000-0000-000000009604',
      'tcm-lineage-revenue-prepare', 'document',
      'https://e.tcm.ba.gov.br/epp/ConsultaPublica/listView.seam',
      '2023-05-18 12:04:00+00', 200, '${"6".repeat(64)}',
      'tcm-ba/monthly/2023/04/revenue-prepare.xml', 'test/1',
      '{"schema_name":"tcm-ba-document-download-prepare","document_role":"download-prepare","source_record_key":"tcm-ba:document:04/2023:revenue"}'::jsonb
    ),
    (
      '00000000-0000-0000-0000-000000009612',
      '00000000-0000-0000-0000-000000009603',
      '00000000-0000-0000-0000-000000009602',
      '00000000-0000-0000-0000-000000009611',
      'tcm-lineage-revenue-pdf', 'document',
      'https://e.tcm.ba.gov.br/epp/PdfReadOnly/downloadDocumento.seam',
      '2023-05-18 12:05:00+00', 1100, '${"7".repeat(64)}',
      'tcm-ba/monthly/2023/04/revenue.pdf', 'test/1',
      '{"schema_name":"tcm-ba-monthly-document","document_role":"pdf","source_record_key":"tcm-ba:document:04/2023:revenue"}'::jsonb
    );
    insert into org.public_bodies (
      id, origin_raw_record_id, ibge_code, name, body_type, state_code
    ) values (
      '00000000-0000-0000-0000-000000009609',
      '00000000-0000-0000-0000-000000009605', '2903201',
      'Município de Barreiras', 'executive', 'BA'
    );
  `);

  const lineage = await database.query(`
    select
      finance.has_tcm_ba_document_lineage(
        '00000000-0000-0000-0000-000000009605',
        '00000000-0000-0000-0000-000000009608'
      ) as tcm_matches,
      finance.has_exact_document_lineage(
        '00000000-0000-0000-0000-000000009605',
        '00000000-0000-0000-0000-000000009608'
      ) as exact_matches,
      finance.has_exact_document_lineage(
        '00000000-0000-0000-0000-000000009606',
        '00000000-0000-0000-0000-000000009608'
      ) as unrelated_matches,
      finance.has_tcm_ba_document_lineage(
        '00000000-0000-0000-0000-000000009606',
        '00000000-0000-0000-0000-000000009612'
      ) as revenue_matches
  `);
  assert.deepEqual(lineage.rows, [{
    tcm_matches: true,
    exact_matches: true,
    unrelated_matches: false,
    revenue_matches: true,
  }]);

  const pairs = await database.query(`
    select origin_raw_record_id::text, document_artifact_id::text
    from finance.get_exact_document_lineage_pairs()
    where document_artifact_id = '00000000-0000-0000-0000-000000009608'
  `);
  assert.deepEqual(pairs.rows, [{
    origin_raw_record_id: "00000000-0000-0000-0000-000000009605",
    document_artifact_id: "00000000-0000-0000-0000-000000009608",
  }]);

  const revenuePairs = await database.query(`
    select origin_raw_record_id::text, document_artifact_id::text
    from finance.get_exact_document_lineage_pairs()
    where document_artifact_id = '00000000-0000-0000-0000-000000009612'
  `);
  assert.deepEqual(revenuePairs.rows, [{
    origin_raw_record_id: "00000000-0000-0000-0000-000000009606",
    document_artifact_id: "00000000-0000-0000-0000-000000009612",
  }]);

  await database.exec(`
    insert into finance.expense_reports (
      id, origin_raw_record_id, source_document_artifact_id, public_body_id,
      fiscal_year, period_start, period_end, total_fixed_amount,
      total_additions_amount, total_reductions_amount, total_updated_amount,
      total_committed_period_amount, total_committed_to_date_amount,
      total_liquidated_period_amount, total_liquidated_to_date_amount,
      total_paid_period_amount, total_paid_to_date_amount,
      total_unpaid_committed_amount, total_balance_amount,
      methodology_version, validation_status, published_at
    ) values (
      '00000000-0000-0000-0000-000000009610',
      '00000000-0000-0000-0000-000000009605',
      '00000000-0000-0000-0000-000000009608',
      '00000000-0000-0000-0000-000000009609',
      2023, '2023-04-01', '2023-04-30', 798579611, 64277886.67,
      64277886.67, 798579611, 16029966.95, 534970476.92,
      62639688.25, 231420652.75, 56656735.88, 198085948.67,
      336884528.25, 263609134.08, 'tcm-ba-analytical-expense/1.0.0',
      'validated', '2023-05-18 12:03:00+00'
    );
  `);
  const publicReport = await database.query(`
    select total_paid_period_amount, document_artifact_sha256
    from api.get_public_expense_reports(10, 2023::smallint)
    where expense_report_id = '00000000-0000-0000-0000-000000009610'
  `);
  assert.deepEqual(publicReport.rows, [{
    total_paid_period_amount: "56656735.88",
    document_artifact_sha256: "5".repeat(64),
  }]);

  const acl = await database.query(`
    select
      has_function_privilege(
        'anon', 'finance.has_tcm_ba_document_lineage(uuid,uuid)', 'execute'
      ) as anon_can_execute,
      has_function_privilege(
        'authenticated',
        'finance.has_tcm_ba_document_lineage(uuid,uuid)',
        'execute'
      ) as authenticated_can_execute
  `);
  assert.deepEqual(acl.rows, [{
    anon_can_execute: false,
    authenticated_can_execute: false,
  }]);

  console.log(
    "Linhagem exata TCM-BA de despesa/receita e projeção validadas.",
  );
} finally {
  await database.close();
}
