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
  migrationNames.map(async (name) =>
    readFile(fileURLToPath(new URL(name, migrationsUrl)), "utf8"),
  ),
);
const seedUrl = new URL("../../../supabase/seed.sql", import.meta.url);
const seed = await readFile(fileURLToPath(seedUrl), "utf8");
const database = new PGlite({
  extensions: { pgcrypto, pg_trgm },
});

try {
  await database.exec(`
    do $$
    begin
      if not exists (
        select 1 from pg_catalog.pg_roles where rolname = 'anon'
      ) then
        create role anon nologin;
      end if;
      if not exists (
        select 1 from pg_catalog.pg_roles where rolname = 'authenticated'
      ) then
        create role authenticated nologin;
      end if;
      if not exists (
        select 1 from pg_catalog.pg_roles where rolname = 'authenticator'
      ) then
        create role authenticator nologin;
      end if;
    end
    $$;

    create schema auth;
    create table auth.users (
      id uuid primary key
    );
    -- A migration de representação provisiona um corredor de Storage para
    -- o workload da Câmara Federal. O fixture precisa reproduzir esse
    -- usuário de serviço antes de executar as migrations; em produção ele
    -- é criado pelo provisionamento de credenciais, não pela migration.
    insert into auth.users (id) values
      ('1575c740-fcff-4b1a-89a9-e8e5a314880a'),
      ('27b3add6-f788-48e5-bf6f-50dfbd8cf198'),
      ('c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a');
    create function auth.uid()
    returns uuid
    language sql
    stable
    set search_path = ''
    as $$
      select nullif(
        current_setting('request.jwt.claim.sub', true),
        ''
      )::uuid;
    $$;

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
      bucket_id text not null references storage.buckets (id),
      name text not null,
      unique (bucket_id, name)
    );
    alter table storage.objects enable row level security;
    grant usage on schema storage to authenticated;
    grant select, insert, update, delete on storage.objects to authenticated;
  `);

  for (const migration of migrations) {
    await database.exec(migration);
  }

  await database.exec(`
    insert into audit.assist_diagnostics (
      command, provider, model, outcome, detail
    ) values (
      'digest_gazette_editions',
      'local-deterministic',
      'digest-rules-v1',
      'fallback_succeeded',
      'external_provider_unavailable'
    );
  `);
  const deterministicAssistDiagnostic = await database.query(`
    select outcome, provider
    from audit.assist_diagnostics
    where command = 'digest_gazette_editions'
  `);
  assert.deepEqual(deterministicAssistDiagnostic.rows, [
    {
      outcome: 'fallback_succeeded',
      provider: 'local-deterministic',
    },
  ]);

  const municipalWorkloads = await database.query(`
    select
      slug,
      auth_user_id::text as auth_user_id,
      status,
      can_select,
      can_insert
    from audit.storage_workload_identities
    where object_prefix = 'municipal-transparency/'
    order by slug
  `);
  assert.deepEqual(municipalWorkloads.rows, [
    {
      slug: "municipal-transparency-collector",
      auth_user_id: "c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a",
      status: "active",
      can_select: true,
      can_insert: true,
    },
    {
      slug: "municipal-transparency-collector-retired-20260802",
      auth_user_id: "27b3add6-f788-48e5-bf6f-50dfbd8cf198",
      status: "retired",
      can_select: false,
      can_insert: false,
    },
  ]);

  const relations = await database.query(`
    select count(*)::integer as count
    from pg_catalog.pg_tables
    where schemaname in (
      'source', 'raw', 'org', 'hr', 'procurement', 'finance',
      'evidence', 'analysis', 'editorial', 'audit'
    )
  `);
  assert.equal(relations.rows[0].count, 55);

  const rlsRelations = await database.query(`
    select count(*)::integer as count
    from pg_catalog.pg_tables as table_record
    join pg_catalog.pg_class as relation
      on relation.relname = table_record.tablename
    join pg_catalog.pg_namespace as namespace
      on namespace.oid = relation.relnamespace
     and namespace.nspname = table_record.schemaname
    where table_record.schemaname in (
      'source', 'raw', 'org', 'hr', 'procurement', 'finance',
      'evidence', 'analysis', 'editorial', 'audit'
    )
      and relation.relrowsecurity
  `);
  assert.equal(rlsRelations.rows[0].count, 55);

  const originColumns = await database.query(`
    select count(*)::integer as count
    from information_schema.columns
    where column_name = 'origin_raw_record_id'
      and table_schema in ('org', 'hr', 'procurement', 'finance', 'analysis', 'editorial')
  `);
  assert.equal(originColumns.rows[0].count, 28);

  const nullableOrigins = await database.query(`
    select count(*)::integer as count
    from information_schema.columns
    where column_name = 'origin_raw_record_id'
      and is_nullable <> 'NO'
  `);
  assert.equal(nullableOrigins.rows[0].count, 0);

  const revenueAutomationColumns = await database.query(`
    select column_name
    from information_schema.columns
    where table_schema = 'finance'
      and table_name = 'revenues'
      and column_name in (
        'source_document_artifact_id', 'accumulated_amount',
        'report_total_period_amount',
        'difference_more', 'difference_less', 'collection_direction',
        'methodology_version', 'validation_status', 'published_at'
      )
    order by column_name
  `);
  assert.deepEqual(
    revenueAutomationColumns.rows.map((row) => row.column_name),
    [
      'accumulated_amount',
      'collection_direction',
      'difference_less',
      'difference_more',
      'methodology_version',
      'published_at',
      'report_total_period_amount',
      'source_document_artifact_id',
      'validation_status',
    ],
  );

  const expenseTables = await database.query(`
    select table_name
    from information_schema.tables
    where table_schema = 'finance'
      and table_name in ('expense_reports', 'expense_lines')
    order by table_name
  `);
  assert.deepEqual(
    expenseTables.rows.map((row) => row.table_name),
    ['expense_lines', 'expense_reports'],
  );

  const expenseFunction = await database.query(`
    select pg_get_function_result(
      'api.get_public_expense_reports(integer,smallint)'::regprocedure
    ) as result
  `);
  assert.match(String(expenseFunction.rows[0].result), /total_paid_period_amount/);
  assert.match(String(expenseFunction.rows[0].result), /document_artifact_sha256/);

  const revenueFunction = await database.query(`
    select pg_get_function_result(
      'api.get_public_revenues(integer,smallint)'::regprocedure
    ) as result
  `);
  assert.match(String(revenueFunction.rows[0].result), /document_artifact_sha256/);
  assert.match(String(revenueFunction.rows[0].result), /validation_status/);

  const immutableTriggers = await database.query(`
    select count(*)::integer as count
    from pg_catalog.pg_trigger
    where tgname = 'reject_mutation'
      and not tgisinternal
  `);
  assert.equal(immutableTriggers.rows[0].count, 11);

  const extensionSchema = await database.query(`
    select namespace.nspname as schema_name
    from pg_catalog.pg_extension as extension_record
    join pg_catalog.pg_namespace as namespace
      on namespace.oid = extension_record.extnamespace
    where extension_record.extname = 'pg_trgm'
  `);
  assert.equal(extensionSchema.rows[0].schema_name, "extensions");

  const unindexedForeignKeys = await database.query(`
    select count(*)::integer as count
    from pg_catalog.pg_constraint as constraint_record
    join pg_catalog.pg_class as relation
      on relation.oid = constraint_record.conrelid
    join pg_catalog.pg_namespace as namespace
      on namespace.oid = relation.relnamespace
    where constraint_record.contype = 'f'
      and namespace.nspname in (
        'source', 'raw', 'org', 'hr', 'procurement', 'finance',
        'evidence', 'analysis', 'editorial', 'audit'
      )
      and not exists (
        select 1
        from pg_catalog.pg_index as index_record
        where index_record.indrelid = constraint_record.conrelid
          and index_record.indisvalid
          and index_record.indisready
          and index_record.indpred is null
          and (
            index_record.indkey::smallint[]
          )[0:cardinality(constraint_record.conkey) - 1]
            = constraint_record.conkey
      )
  `);
  assert.equal(unindexedForeignKeys.rows[0].count, 0);

  const collectorPrivileges = await database.query(`
    select
      has_column_privilege(
        'collector_worker',
        'raw.raw_artifacts',
        'collection_run_id',
        'INSERT'
      ) as can_insert,
      has_table_privilege(
        'collector_worker',
        'raw.raw_artifacts',
        'DELETE'
      ) as can_delete
  `);
  assert.deepEqual(collectorPrivileges.rows[0], {
    can_insert: true,
    can_delete: false,
  });

  const workloadRole = await database.query(`
    select
      role_record.rolcanlogin as can_login,
      role_record.rolinherit as inherits,
      role_record.rolsuper as superuser,
      role_record.rolbypassrls as bypasses_rls,
      role_record.rolconnlimit as connection_limit,
      pg_has_role(
        'collector_querido_diario',
        'collector_worker',
        'MEMBER'
      ) as is_worker_member
    from pg_catalog.pg_roles as role_record
    where role_record.rolname = 'collector_querido_diario'
  `);
  assert.deepEqual(workloadRole.rows[0], {
    can_login: false,
    inherits: true,
    superuser: false,
    bypasses_rls: false,
    connection_limit: 2,
    is_worker_member: true,
  });

  await database.exec(seed);
  await database.exec(seed);

  const workloadUserId = "00000000-0000-4000-8000-000000000301";
  await database.exec(`
    insert into auth.users (id) values ('${workloadUserId}');
    insert into audit.storage_workload_identities (
      slug,
      auth_user_id,
      bucket_id,
      object_prefix,
      status,
      activated_at
    ) values (
      'querido-diario-collector',
      '${workloadUserId}',
      'raw-artifacts',
      'querido-diario/gazettes/',
      'active',
      statement_timestamp()
    );
    select set_config(
      'request.jwt.claim.sub',
      '${workloadUserId}',
      false
    );
  `);

  const storageAuthorization = await database.query(`
    select
      api.can_access_raw_artifact(
        'insert',
        'raw-artifacts',
        'querido-diario/gazettes/sha256/aa/file.json'
      ) as can_insert,
      api.can_access_raw_artifact(
        'select',
        'raw-artifacts',
        'querido-diario/gazettes/sha256/aa/file.json'
      ) as can_select,
      api.can_access_raw_artifact(
        'update',
        'raw-artifacts',
        'querido-diario/gazettes/sha256/aa/file.json'
      ) as can_update,
      api.can_access_raw_artifact(
        'insert',
        'raw-artifacts',
        'pncp/file.json'
      ) as can_escape_prefix
  `);
  assert.deepEqual(storageAuthorization.rows[0], {
    can_insert: true,
    can_select: true,
    can_update: false,
    can_escape_prefix: false,
  });

  const allowedStorageObjectId = "00000000-0000-4000-8000-000000000302";
  await database.exec(`
    set role authenticated;
    insert into storage.objects (id, bucket_id, name) values (
      '${allowedStorageObjectId}',
      'raw-artifacts',
      'querido-diario/gazettes/sha256/aa/file.json'
    );
    reset role;
  `);
  await assert.rejects(
    database.exec(`
      set role authenticated;
      insert into storage.objects (id, bucket_id, name) values (
        '00000000-0000-4000-8000-000000000303',
        'raw-artifacts',
        'pncp/file.json'
      );
    `),
    /row-level security/,
  );
  await database.exec("reset role;");

  await database.exec(`
    set role authenticated;
    delete from storage.objects where id = '${allowedStorageObjectId}';
    reset role;
  `);
  const immutableStorageObject = await database.query(`
    select count(*)::integer as count
    from storage.objects
    where id = '${allowedStorageObjectId}'
  `);
  assert.equal(immutableStorageObject.rows[0].count, 1);

  const endpointId = "00000000-0000-4000-8000-000000000101";
  const runId = "00000000-0000-0000-0000-000000000401";
  const artifactId = "00000000-0000-0000-0000-000000000402";
  await database.exec(`
    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version,
      parser_version, status, attempt_count, started_at, completed_at
    ) values (
      '${runId}', '${endpointId}', '${"1".repeat(64)}', 'test/1',
      'parser/1', 'succeeded', 1, now(), now()
    );

    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, idempotency_key,
      artifact_kind, source_url, retrieved_at, http_status, content_type,
      byte_size, sha256, object_key, collector_version, metadata
    ) values (
      '${artifactId}', '${runId}', '${endpointId}', '${"2".repeat(64)}',
      'http_response', 'https://api.queridodiario.ok.org.br/gazettes',
      now(), 200, 'application/json', 2, '${"3".repeat(64)}',
      'querido-diario/gazettes/sha256/33/${"3".repeat(64)}.json',
      'test/1', '{"source_record_key":"gazette:1"}'
    );

    insert into raw.raw_records (
      raw_artifact_id, source_record_key, record_type, record_index, payload,
      payload_sha256, parser_version, idempotency_key, collected_at
    ) values (
      '${artifactId}', 'gazette:1', 'querido_diario_gazette', 0,
      '{"date":"2026-06-10","territory_id":"2903201","v":1}',
      '${"4".repeat(64)}', 'parser/1', '${"5".repeat(64)}', now()
    ) on conflict (idempotency_key) do nothing;

    insert into raw.raw_records (
      raw_artifact_id, source_record_key, record_type, record_index, payload,
      payload_sha256, parser_version, idempotency_key, collected_at
    ) values (
      '${artifactId}', 'gazette:1', 'querido_diario_gazette', 0,
      '{"date":"2026-06-10","territory_id":"2903201","v":2}',
      '${"6".repeat(64)}', 'parser/2', '${"7".repeat(64)}', now()
    ) on conflict (idempotency_key) do nothing;

    insert into raw.raw_records (
      raw_artifact_id, source_record_key, record_type, record_index, payload,
      payload_sha256, parser_version, idempotency_key, collected_at
    ) values (
      '${artifactId}', 'gazette:1', 'querido_diario_gazette', 0,
      '{"date":"2026-06-10","territory_id":"2903201","v":2}',
      '${"6".repeat(64)}', 'parser/2', '${"7".repeat(64)}', now()
    ) on conflict (idempotency_key) do nothing;
  `);
  const replay = await database.query(`
    select
      (select count(*)::integer from raw.raw_artifacts) as artifacts,
      (select count(*)::integer from raw.raw_records) as records
  `);
  assert.deepEqual(replay.rows[0], { artifacts: 1, records: 2 });

  const failedRunId = "00000000-0000-0000-0000-000000000405";
  await database.exec(`
    insert into source.collection_partitions (
      id, source_endpoint_id, partition_key, period_start, period_end,
      status, expected_records, observed_records, collection_run_id,
      last_attempted_at, completed_at
    ) values (
      '00000000-0000-0000-0000-000000000406', '${endpointId}',
      '2026-06-10', '2026-06-10', '2026-06-10', 'complete', 1, 1,
      '${runId}', '2026-06-10 12:00:00+00', '2026-06-10 12:00:00+00'
    );

    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version,
      parser_version, status, attempt_count, started_at, completed_at,
      error_code, error_detail
    ) values (
      '${failedRunId}', '${endpointId}', '${"9".repeat(64)}',
      'test/2', 'parser/2', 'failed', 2,
      '2026-06-11 12:00:00+00', '2026-06-11 12:01:00+00',
      'upstream_timeout', 'detalhe interno que não deve sair pela RPC'
    );

    insert into source.collection_partitions (
      id, source_endpoint_id, partition_key, period_start, period_end,
      status, observed_records, collection_run_id, last_attempted_at
    ) values (
      '00000000-0000-0000-0000-000000000407', '${endpointId}',
      '2026-06-11', '2026-06-11', '2026-06-11', 'failed', 0,
      '${failedRunId}', '2026-06-11 12:01:00+00'
    );

    insert into source.collection_failures (
      id, collection_run_id, source_endpoint_id, partition_key, status,
      error_type, error_detail, attempt_count, retryable, next_retry_at,
      failed_at
    ) values (
      '00000000-0000-0000-0000-000000000408', '${failedRunId}',
      '${endpointId}', '2026-06-11', 'retry_scheduled',
      'upstream_timeout', 'A fonte oficial excedeu o tempo de resposta.',
      2, true, '2026-06-11 13:00:00+00', '2026-06-11 12:01:00+00'
    );
  `);

  const anonymousRawPrivilege = await database.query(`
    select has_table_privilege(
      'anon',
      'raw.raw_records',
      'SELECT'
    ) as can_read_raw_records
  `);
  await database.exec("set role anon;");
  const publicCollectionStatus = await database.query(`
    select
      source_slug,
      latest_status,
      coverage_start::text as coverage_start,
      coverage_end::text as coverage_end,
      preserved_response_count::integer as preserved_response_count,
      preserved_edition_count::integer as preserved_edition_count,
      methodology_version
    from api.get_querido_diario_collection_status()
  `);
  await database.exec("reset role;");
  assert.deepEqual(publicCollectionStatus.rows[0], {
    source_slug: "querido-diario",
    latest_status: "succeeded",
    coverage_start: "2026-06-10",
    coverage_end: "2026-06-10",
    preserved_response_count: 1,
    preserved_edition_count: 1,
    methodology_version: "querido-diario-collection-status/1.0.0",
  });
  assert.deepEqual(anonymousRawPrivilege.rows[0], {
    can_read_raw_records: false,
  });

  await assert.rejects(
    database.exec(`
      update raw.raw_artifacts
      set content_type = 'text/plain'
      where id = '${artifactId}'
    `),
    /immutable relation/,
  );

  await database.exec(`
    insert into raw.extraction_jobs (
      id, raw_artifact_id, job_type, idempotency_key, status, attempt_count
    ) values (
      '00000000-0000-0000-0000-000000000601', '${artifactId}',
      'gazette_act_candidates', '${"8".repeat(64)}', 'succeeded', 1
    );
    insert into raw.extraction_results (
      id, extraction_job_id, candidate_type, extractor_version,
      validator_version, result_payload, validation_status
    ) values (
      '00000000-0000-0000-0000-000000000602',
      '00000000-0000-0000-0000-000000000601',
      'nomeacao', 'gazette-act-candidates/1.0.0',
      'human-review-pending/1.0.0',
      '{"excerpt":"NOMEAR FULANO DE TAL"}', 'needs_review'
    );
    insert into raw.extraction_results (
      id, extraction_job_id, supersedes_id, candidate_type,
      extractor_version, validator_version, result_payload, validation_status
    ) values (
      '00000000-0000-0000-0000-000000000603',
      '00000000-0000-0000-0000-000000000601',
      '00000000-0000-0000-0000-000000000602',
      'assisted_enrichment', 'assisted-inference/2.0.0',
      'human-review-pending/1.0.0',
      '{"provider":"teste","summary":"Resumo de teste","clean_text":"Nomeação de teste"}',
      'needs_review'
    );
  `);

  const reviewerUserId = "00000000-0000-4000-8000-000000000701";
  await database.exec(`
    insert into auth.users (id) values ('${reviewerUserId}');
    select set_config('request.jwt.claim.sub', '${workloadUserId}', false);
  `);
  await assert.rejects(
    database.query("select * from api.get_extraction_review_queue(20)"),
    /acesso restrito a revisores ativos/,
  );
  await assert.rejects(
    database.query("select * from api.get_collection_health(200)"),
    /acesso restrito a revisores ativos/,
  );
  await assert.rejects(
    database.query("select * from api.get_collection_health_v2(200)"),
    /acesso restrito a revisores ativos/,
  );
  await assert.rejects(
    database.query("select * from api.get_collection_health_v3(200)"),
    /acesso restrito a revisores ativos/,
  );

  await database.exec(`
    insert into audit.reviewer_identities (
      auth_user_id, display_name, status, activated_at
    ) values (
      '${reviewerUserId}', 'Revisor de Teste', 'active', statement_timestamp()
    );
    select set_config('request.jwt.claim.sub', '${reviewerUserId}', false);
  `);

  await database.exec(`
    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version,
      parser_version, collection_window_start, collection_window_end,
      status, attempt_count, started_at, completed_at
    ) values
      (
        '00000000-0000-0000-0000-000000000411', '${endpointId}',
        '${"a".repeat(64)}', 'test/backfill', 'parser/1',
        '2026-07-24 00:00:00+00', '2026-07-30 23:59:59+00',
        'succeeded', 1, '2026-08-05 17:30:00+00',
        '2026-08-05 17:31:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000000412', '${endpointId}',
        '${"b".repeat(64)}', 'test/backfill', 'parser/1',
        '2026-07-31 00:00:00+00', '2026-08-04 23:59:59+00',
        'succeeded', 1, '2026-08-05 17:32:00+00',
        '2026-08-05 17:33:00+00'
      );

    insert into source.collection_partitions (
      id, source_endpoint_id, partition_key, period_start, period_end,
      status, observed_records, collection_run_id, last_attempted_at,
      completed_at
    ) values
      (
        '00000000-0000-0000-0000-000000000413', '${endpointId}',
        'published:2026-07-24:2026-07-30', '2026-07-24', '2026-07-30',
        'empty', 0, '00000000-0000-0000-0000-000000000411',
        '2026-08-05 17:31:00+00', '2026-08-05 17:31:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000000414', '${endpointId}',
        'published:2026-07-31:2026-08-04', '2026-07-31', '2026-08-04',
        'empty', 0, '00000000-0000-0000-0000-000000000412',
        '2026-08-05 17:33:00+00', '2026-08-05 17:33:00+00'
      );

    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version,
      parser_version, collection_window_start, collection_window_end,
      status, attempt_count, started_at, completed_at
    ) values (
      '00000000-0000-0000-0000-000000000415', '${endpointId}',
      '${"c".repeat(64)}', 'test/retry', 'parser/1',
      '2026-08-05 00:00:00+00', '2026-08-11 23:59:59+00',
      'failed', 1, '2026-08-12 10:00:00+00',
      '2026-08-12 10:01:00+00'
    );

    insert into source.collection_partitions (
      id, source_endpoint_id, partition_key, period_start, period_end,
      status, observed_records, collection_run_id, last_attempted_at
    ) values (
      '00000000-0000-0000-0000-000000000416', '${endpointId}',
      'published:2026-08-05:2026-08-11', '2026-08-05', '2026-08-11',
      'failed', 0, '00000000-0000-0000-0000-000000000415',
      '2026-08-12 10:01:00+00'
    );

    insert into source.source_endpoints (
      id, data_source_id, slug, endpoint_kind, base_url, enabled,
      freshness_policy_kind, freshness_expected_hours,
      freshness_grace_hours, freshness_policy_note,
      freshness_policy_version
    ) values (
      '00000000-0000-4000-8000-000000000417',
      (select id from source.data_sources where slug = 'querido-diario'),
      'freshness-current-test', 'api',
      'https://api.queridodiario.ok.org.br/freshness-test', true,
      'scheduled', 24, 24,
      'Fixture diária com tolerância operacional.',
      'source-freshness/1.0.0'
    );

    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version,
      parser_version, collection_window_start, collection_window_end,
      status, attempt_count, started_at, completed_at
    ) values (
      '00000000-0000-0000-0000-000000000418',
      '00000000-0000-4000-8000-000000000417',
      '${"d".repeat(64)}', 'test/freshness', 'parser/1',
      statement_timestamp() - interval '2 hours',
      statement_timestamp() - interval '1 hour',
      'succeeded', 1, statement_timestamp() - interval '70 minutes',
      statement_timestamp() - interval '1 hour'
    );

    insert into source.collection_partitions (
      id, source_endpoint_id, partition_key, period_start, period_end,
      status, observed_records, collection_run_id, last_attempted_at,
      completed_at
    ) values (
      '00000000-0000-0000-0000-000000000419',
      '00000000-0000-4000-8000-000000000417',
      'freshness-current', current_date, current_date, 'complete', 1,
      '00000000-0000-0000-0000-000000000418',
      statement_timestamp() - interval '1 hour',
      statement_timestamp() - interval '1 hour'
    );
  `);

  await assert.rejects(
    database.query("select * from api.get_collection_health(501)"),
    /page_size deve estar entre 1 e 500/,
  );

  await database.exec("set role anon;");
  await assert.rejects(
    database.query("select * from api.get_collection_health(200)"),
    /permission denied/,
  );
  await assert.rejects(
    database.query("select * from api.get_collection_health_v2(200)"),
    /permission denied/,
  );
  await assert.rejects(
    database.query("select * from api.get_collection_health_v3(200)"),
    /permission denied/,
  );
  await database.exec("reset role;");

  await database.exec("set role authenticated;");
  const collectionHealth = await database.query(`
    select
      latest_partition_status,
      latest_run_status,
      latest_collector_version,
      latest_successful_partition_status,
      latest_successful_period_end::text as latest_successful_period_end,
      to_char(
        latest_successful_completed_at at time zone 'UTC',
        'YYYY-MM-DD"T"HH24:MI:SS"Z"'
      ) as latest_successful_completed_at,
      complete_partitions::integer as complete_partitions,
      failed_partitions::integer as failed_partitions,
      unresolved_failures::integer as unresolved_failures,
      latest_failure_type,
      latest_failure_detail,
      methodology_version
    from api.get_collection_health_v2(200)
    where endpoint_id = '${endpointId}'
  `);
  await database.exec("reset role;");
  assert.deepEqual(collectionHealth.rows, [
    {
      latest_partition_status: "failed",
      latest_run_status: "failed",
      latest_collector_version: "test/retry",
      latest_successful_partition_status: "empty",
      latest_successful_period_end: "2026-08-04",
      latest_successful_completed_at: "2026-08-05T17:33:00Z",
      complete_partitions: 1,
      failed_partitions: 2,
      unresolved_failures: 1,
      latest_failure_type: "upstream_timeout",
      latest_failure_detail: "A fonte oficial excedeu o tempo de resposta.",
      methodology_version: "collection-health/1.2.0",
    },
  ]);

  await database.exec("set role authenticated;");
  const collectionFreshness = await database.query(`
    select
      endpoint_slug,
      freshness_policy_kind,
      freshness_expected_hours,
      freshness_grace_hours,
      freshness_status,
      (freshness_overdue_hours > 0) as freshness_overdue,
      methodology_version
    from api.get_collection_health_v3(200)
    where endpoint_slug in ('gazettes-api', 'freshness-current-test')
    order by endpoint_slug
  `);
  await database.exec("reset role;");
  assert.deepEqual(collectionFreshness.rows, [
    {
      endpoint_slug: "freshness-current-test",
      freshness_policy_kind: "scheduled",
      freshness_expected_hours: 24,
      freshness_grace_hours: 24,
      freshness_status: "current",
      freshness_overdue: false,
      methodology_version: "collection-health/1.3.0",
    },
    {
      endpoint_slug: "gazettes-api",
      freshness_policy_kind: "scheduled",
      freshness_expected_hours: 24,
      freshness_grace_hours: 24,
      freshness_status: "overdue",
      freshness_overdue: true,
      methodology_version: "collection-health/1.3.0",
    },
  ]);
  await database.exec(`
    delete from source.collection_partitions
    where source_endpoint_id = '00000000-0000-4000-8000-000000000417';
    delete from source.collection_runs
    where source_endpoint_id = '00000000-0000-4000-8000-000000000417';
    delete from source.source_endpoints
    where id = '00000000-0000-4000-8000-000000000417';
  `);

  const queridoDiarioBackfill = await database.query(`
    select row_to_json(health) as health
    from api.get_collection_health(200) as health
    where endpoint_id = '${endpointId}'
  `);
  assert.deepEqual(
    {
      backfill_horizon: queridoDiarioBackfill.rows[0].health.backfill_horizon,
      continuous_coverage_start:
        queridoDiarioBackfill.rows[0].health.continuous_coverage_start,
      continuous_coverage_end:
        queridoDiarioBackfill.rows[0].health.continuous_coverage_end,
      next_backfill_start:
        queridoDiarioBackfill.rows[0].health.next_backfill_start,
      next_backfill_end: queridoDiarioBackfill.rows[0].health.next_backfill_end,
      backfill_classified_days:
        queridoDiarioBackfill.rows[0].health.backfill_classified_days,
      backfill_total_days:
        queridoDiarioBackfill.rows[0].health.backfill_total_days,
      backfill_progress_percent:
        queridoDiarioBackfill.rows[0].health.backfill_progress_percent,
    },
    {
      backfill_horizon: "2021-01-01",
      continuous_coverage_start: "2026-07-24",
      continuous_coverage_end: "2026-08-04",
      next_backfill_start: "2026-07-17",
      next_backfill_end: "2026-07-23",
      backfill_classified_days: 12,
      backfill_total_days: 2042,
      backfill_progress_percent: 0.59,
    },
  );

  const healthFunctionColumns = await database.query(`
    select pg_get_function_result(
      'api.get_collection_health(integer)'::regprocedure
    ) as result
  `);
  assert.doesNotMatch(String(healthFunctionColumns.rows[0].result), /checkpoint|metrics/);

  const reviewQueue = await database.query(`
    select
      candidate_type,
      validation_status,
      result_payload ->> 'excerpt' as excerpt,
      assisted_payload,
      queue_reason,
      methodology_version
    from api.get_extraction_review_queue(20)
  `);
  assert.deepEqual(reviewQueue.rows, [
    {
      candidate_type: "nomeacao",
      validation_status: "needs_review",
      excerpt: "NOMEAR FULANO DE TAL",
      assisted_payload: {
        provider: "teste",
        summary: "Resumo de teste",
        clean_text: "Nomeação de teste",
      },
      queue_reason: "needs_human_verification",
       methodology_version: "extraction-review-queue/1.7.0",
    },
  ]);
  await assert.rejects(
    database.query(`
      select api.review_extraction_candidate(
        '00000000-0000-0000-0000-000000000602', 'approved', 'ok'
      )
    `),
    /justificativa é obrigatória/,
  );
  await assert.rejects(
    database.query(`
      select api.review_extraction_candidate(
        '00000000-0000-0000-0000-000000000602', 'maybe',
        'decisão inválida de teste'
      )
    `),
    /decisão deve ser approved ou rejected/,
  );
  const reviewDecision = await database.query(`
    select api.review_extraction_candidate(
      '00000000-0000-0000-0000-000000000602',
      'approved',
      'Confere com o trecho oficial; nomeação legítima de teste.'
    ) as review_id
  `);
  assert.match(String(reviewDecision.rows[0].review_id), /^[0-9a-f-]{36}$/);

  const queueAfterDecision = await database.query(`
    select count(*)::integer as count
    from api.get_extraction_review_queue(20)
  `);
  assert.equal(queueAfterDecision.rows[0].count, 0);

  await assert.rejects(
    database.query(`
      select api.review_extraction_candidate(
        '00000000-0000-0000-0000-000000000602', 'rejected',
        'tentativa de segunda decisão'
      )
    `),
    /já tem decisão vigente/,
  );

  const reviewAudit = await database.query(`
    select
      (select count(*)::integer from editorial.editorial_reviews
       where target_type = 'raw.extraction_results') as reviews,
      (select count(*)::integer from audit.audit_events
       where action = 'extraction_candidate_reviewed') as audit_rows,
      (select validation_status from raw.extraction_results
       where id = '00000000-0000-0000-0000-000000000602') as raw_status
  `);
  assert.deepEqual(reviewAudit.rows[0], {
    reviews: 1,
    audit_rows: 1,
    raw_status: "needs_review",
  });

  await database.exec(`
    select set_config('request.jwt.claim.sub', '${workloadUserId}', false);
  `);
  await assert.rejects(
    database.query(`
      select api.review_extraction_candidate(
        '00000000-0000-0000-0000-000000000602', 'approved',
        'não sou revisor e não deveria conseguir'
      )
    `),
    /acesso restrito a revisores ativos/,
  );

  await database.exec("set role anon;");
  const approvedActs = await database.query(`
    select
      act_type,
      person_name,
      gazette_date::text as gazette_date,
      gazette_url,
      excerpt,
      methodology_version
    from api.get_approved_gazette_acts(50)
  `);
  await database.exec("reset role;");
  assert.deepEqual(approvedActs.rows, [
    {
      act_type: "nomeacao",
      person_name: null,
      gazette_date: "2026-06-10",
      gazette_url: null,
      excerpt: "NOMEAR FULANO DE TAL",
      methodology_version: "approved-gazette-acts/1.6.0",
    },
  ]);

  const approvedActsDefinition = await database.query(`
    select pg_get_functiondef(procedure.oid) as definition
    from pg_proc as procedure
    join pg_namespace as namespace on namespace.oid = procedure.pronamespace
    where namespace.nspname = 'api'
      and procedure.proname = 'get_approved_gazette_acts'
  `);
  assert.equal(approvedActsDefinition.rows.length, 1);
  assert.doesNotMatch(
    approvedActsDefinition.rows[0].definition,
    /join\s+lateral/i,
    'atos aprovados não podem repetir subconsultas laterais por candidato',
  );
  assert.match(
    approvedActsDefinition.rows[0].definition,
    /latest_reviews\s+as\s+materialized/i,
    'atos aprovados devem resolver a decisão editorial vigente em conjunto',
  );

  const stateRepresentativesDefinition = await database.query(`
    select pg_get_functiondef(procedure.oid) as definition
    from pg_proc as procedure
    join pg_namespace as namespace on namespace.oid = procedure.pronamespace
    where namespace.nspname = 'api'
      and procedure.proname = 'get_state_representatives'
  `);
  assert.equal(stateRepresentativesDefinition.rows.length, 1);
  assert.doesNotMatch(
    stateRepresentativesDefinition.rows[0].definition,
    /join\s+lateral/i,
    'perfis estaduais não podem repetir a busca do perfil por parlamentar',
  );
  assert.match(
    stateRepresentativesDefinition.rows[0].definition,
    /latest_state_profiles\s+as\s+materialized/i,
    'perfis estaduais devem resolver o último retrato oficial em conjunto',
  );

  // Reversão: a decisão vigente muda, o candidato volta à fila e some do
  // público; o histórico acompanha a decisão vigente.
  await database.exec(`
    select set_config('request.jwt.claim.sub', '${reviewerUserId}', false);
  `);
  const historyBefore = await database.query(`
    select decision from api.get_extraction_review_history(50)
  `);
  assert.deepEqual(historyBefore.rows, [{ decision: "approved" }]);

  await database.query(`
    select api.withdraw_extraction_review(
      '00000000-0000-0000-0000-000000000602',
      'Aprovei por engano durante o teste; revertendo com rastro.'
    )
  `);

  const afterWithdrawal = await database.query(`
    select
      (select count(*)::integer from api.get_extraction_review_queue(20))
        as queue,
      (select count(*)::integer from api.get_extraction_review_history(50))
        as history,
      (select count(*)::integer from api.get_approved_gazette_acts(50))
        as public_acts
  `);
  assert.deepEqual(afterWithdrawal.rows[0], {
    queue: 1,
    history: 0,
    public_acts: 0,
  });

  await assert.rejects(
    database.query(`
      select api.withdraw_extraction_review(
        '00000000-0000-0000-0000-000000000602',
        'não há mais decisão vigente para reverter'
      )
    `),
    /não há decisão vigente para reverter/,
  );

  await database.query(`
    select api.review_extraction_candidate(
      '00000000-0000-0000-0000-000000000602',
      'rejected',
      'Segunda análise: é menção, não ato de nomeação.'
    )
  `);
  const afterSecondDecision = await database.query(`
    select
      (select count(*)::integer from api.get_extraction_review_queue(20))
        as queue,
      (select decision from api.get_extraction_review_history(50))
        as history_decision,
      (select count(*)::integer from api.get_approved_gazette_acts(50))
        as public_acts,
      (select count(*)::integer from editorial.editorial_reviews)
        as review_rows
  `);
  assert.deepEqual(afterSecondDecision.rows[0], {
    queue: 0,
    history_decision: "rejected",
    public_acts: 0,
    review_rows: 3,
  });
  await database.exec(`
    select set_config('request.jwt.claim.sub', '${workloadUserId}', false);
  `);

  const dailyCoverage = await database.query(`
    select
      day::text as day,
      attempted_by_recorded_window,
      preserved_editions::integer as preserved_editions,
      preserved_documents::integer as preserved_documents
    from source.querido_diario_daily_coverage
    where day = date '2026-06-10'
  `);
  assert.deepEqual(dailyCoverage.rows, [
    {
      day: "2026-06-10",
      attempted_by_recorded_window: false,
      preserved_editions: 1,
      preserved_documents: 0,
    },
  ]);

  const extractionPrivileges = await database.query(`
    select
      has_table_privilege(
        'collector_worker',
        'raw.document_pages',
        'INSERT'
      ) as pages_insert,
      has_table_privilege(
        'collector_worker',
        'raw.extraction_results',
        'INSERT'
      ) as results_insert,
      has_table_privilege(
        'collector_worker',
        'raw.extraction_results',
        'UPDATE'
      ) as results_update,
      has_table_privilege(
        'collector_worker',
        'raw.extraction_jobs',
        'DELETE'
      ) as jobs_delete
  `);
  assert.deepEqual(extractionPrivileges.rows[0], {
    pages_insert: true,
    results_insert: true,
    results_update: false,
    jobs_delete: false,
  });

  const coveragePrivileges = await database.query(`
    select
      has_table_privilege(
        'anon',
        'source.querido_diario_daily_coverage',
        'SELECT'
      ) as anon_can_read,
      has_table_privilege(
        'authenticated',
        'source.querido_diario_daily_coverage',
        'SELECT'
      ) as authenticated_can_read
  `);
  assert.deepEqual(coveragePrivileges.rows[0], {
    anon_can_read: false,
    authenticated_can_read: false,
  });

  const controlPlaneTables = await database.query(`
    select
      to_regclass('source.collection_partitions') is not null as partitions,
      to_regclass('source.collection_failures') is not null as failures,
      to_regclass('private.person_identifiers') is not null as identifiers,
      to_regclass('private.person_identifier_sources') is not null
        as identifier_sources,
      to_regclass('private.person_identifier_conflicts') is not null
        as identifier_conflicts,
      to_regclass('private.person_identifier_gaps') is not null
        as identifier_gaps,
      to_regclass('identity.person_source_links') is not null as person_source_links
  `);
  assert.deepEqual(controlPlaneTables.rows[0], {
    partitions: true,
    failures: true,
    identifiers: true,
    identifier_sources: true,
    identifier_conflicts: true,
    identifier_gaps: true,
    person_source_links: true,
  });

  const privateIdentityPrivileges = await database.query(`
    select
      has_schema_privilege('anon', 'private', 'USAGE') as anon_schema,
      has_schema_privilege('authenticated', 'private', 'USAGE') as auth_schema,
      has_table_privilege(
        'collector_worker', 'private.person_identifiers', 'SELECT'
      ) as collector_select,
      has_schema_privilege('identity_worker', 'private', 'USAGE')
        as identity_schema,
      has_table_privilege(
        'identity_worker', 'private.person_identifiers', 'SELECT'
      ) as identity_select,
      has_table_privilege(
        'identity_worker', 'private.person_identifiers', 'INSERT'
      ) as identity_insert,
      has_table_privilege(
        'identity_worker', 'private.person_identifiers', 'UPDATE'
      ) as identity_update,
      has_table_privilege(
        'identity_worker', 'private.person_identifier_sources', 'INSERT'
      ) as identity_source_insert,
      has_table_privilege(
        'identity_worker', 'private.person_identifier_conflicts', 'INSERT'
      ) as identity_conflict_insert,
      has_table_privilege(
        'identity_worker', 'private.person_identifier_gaps', 'INSERT'
      ) as identity_gap_insert,
      has_table_privilege(
        'identity_worker', 'identity.person_source_links', 'INSERT'
      ) as identity_link_insert,
      has_table_privilege(
        'identity_worker', 'hr.people', 'INSERT'
      ) as identity_person_insert,
      has_table_privilege(
        'identity_worker', 'raw.raw_records', 'SELECT'
      ) as identity_raw_select,
      has_table_privilege(
        'identity_worker', 'political.representative_tse_crosswalk', 'SELECT'
      ) as identity_crosswalk_select,
      has_table_privilege(
        'anon', 'private.person_identifier_sources', 'SELECT'
      ) as anon_source_select,
      has_table_privilege(
        'anon', 'private.person_identifier_gaps', 'SELECT'
      ) as anon_gap_select,
      has_table_privilege(
        'authenticated', 'identity.person_source_links', 'SELECT'
      ) as authenticated_link_select
  `);
  assert.deepEqual(privateIdentityPrivileges.rows[0], {
    anon_schema: false,
    auth_schema: false,
    collector_select: false,
    identity_schema: true,
    identity_select: true,
    identity_insert: true,
    identity_update: false,
    identity_source_insert: true,
    identity_conflict_insert: true,
    identity_gap_insert: true,
    identity_link_insert: true,
    identity_person_insert: true,
    identity_raw_select: true,
    identity_crosswalk_select: true,
    anon_source_select: false,
    anon_gap_select: false,
    authenticated_link_select: false,
  });

  const identityLoginBoundary = await database.query(`
    select
      role.rolcanlogin,
      role.rolsuper,
      role.rolcreatedb,
      role.rolcreaterole,
      role.rolreplication,
      role.rolbypassrls,
      role.rolconnlimit,
      pg_has_role('identity_registry', 'identity_worker', 'MEMBER') as worker_member,
      pg_has_role(
        'identity_registry', 'collector_worker', 'MEMBER'
      ) as collector_member
    from pg_catalog.pg_roles as role
    where role.rolname = 'identity_registry'
  `);
  assert.deepEqual(identityLoginBoundary.rows, [
    {
      rolcanlogin: false,
      rolsuper: false,
      rolcreatedb: false,
      rolcreaterole: false,
      rolreplication: false,
      rolbypassrls: false,
      rolconnlimit: 1,
      worker_member: true,
      collector_member: false,
    },
  ]);

  const identityOrigin = await database.query(`
    select id::text as id from raw.raw_records order by created_at limit 1
  `);
  const identityOriginId = identityOrigin.rows[0].id;
  const firstIdentity = await database.query(`
    select status, person_id::text as person_id
    from identity.register_tse_identity(
      'candidate:2024:123', 2024, 'https://cdn.tse.jus.br/source.zip',
      decode('01', 'hex'), decode(repeat('02', 12), 'hex'),
      decode(repeat('03', 16), 'hex'), '${"a".repeat(64)}',
      '${"b".repeat(64)}', '${"c".repeat(64)}', 1,
      'tse-candidate-registry/1.0.0', statement_timestamp(),
      'municipal', 'cm:vereador:123', 'Vereador', '${identityOriginId}',
      decode('04', 'hex'), decode(repeat('05', 12), 'hex'),
      decode(repeat('06', 16), 'hex'), '${"d".repeat(64)}', '4725',
      'PESSOA TESTE', 'pessoa teste', 'PESSOA'
    )
  `);
  assert.equal(firstIdentity.rows[0].status, "inserted");

  const replayedIdentity = await database.query(`
    select status, person_id::text as person_id
    from identity.register_tse_identity(
      'candidate:2024:123', 2024, 'https://cdn.tse.jus.br/source.zip',
      decode('01', 'hex'), decode(repeat('02', 12), 'hex'),
      decode(repeat('03', 16), 'hex'), '${"a".repeat(64)}',
      '${"b".repeat(64)}', '${"c".repeat(64)}', 1,
      'tse-candidate-registry/1.0.0', statement_timestamp(),
      'municipal', 'cm:vereador:123', 'Vereador', '${identityOriginId}',
      decode('04', 'hex'), decode(repeat('05', 12), 'hex'),
      decode(repeat('06', 16), 'hex'), '${"d".repeat(64)}', '4725',
      'PESSOA TESTE', 'pessoa teste', 'PESSOA'
    )
  `);
  assert.equal(replayedIdentity.rows[0].status, "unchanged");
  assert.equal(
    replayedIdentity.rows[0].person_id,
    firstIdentity.rows[0].person_id,
  );

  const conflictedIdentity = await database.query(`
    select status
    from identity.register_tse_identity(
      'candidate:2024:124', 2024, 'https://cdn.tse.jus.br/source.zip',
      decode('07', 'hex'), decode(repeat('08', 12), 'hex'),
      decode(repeat('09', 16), 'hex'), '${"e".repeat(64)}',
      '${"b".repeat(64)}', '${"c".repeat(64)}', 1,
      'tse-candidate-registry/1.0.0', statement_timestamp(),
      'municipal', 'cm:vereador:123', 'Vereador', '${identityOriginId}',
      decode('0a', 'hex'), decode(repeat('0b', 12), 'hex'),
      decode(repeat('0c', 16), 'hex'), '${"f".repeat(64)}', '9999',
      'PESSOA TESTE', 'pessoa teste', 'PESSOA'
    )
  `);
  assert.equal(conflictedIdentity.rows[0].status, "conflicted");
  const unavailableIdentity = await database.query(`
    select status
    from identity.register_tse_identifier_gap(
      'candidate:2024:125', 2024, 'https://cdn.tse.jus.br/source.zip',
      decode('0d', 'hex'), decode(repeat('0e', 12), 'hex'),
      decode(repeat('0f', 16), 'hex'), '${"1".repeat(64)}',
      '${"b".repeat(64)}', '${"c".repeat(64)}', 1,
      'tse-candidate-registry/1.1.0', statement_timestamp(),
      'municipal', 'cm:vereador:125', 'Vereador', '${identityOriginId}',
      'invalid_official_value'
    )
  `);
  assert.equal(unavailableIdentity.rows[0].status, "inserted");
  const replayedUnavailableIdentity = await database.query(`
    select status
    from identity.register_tse_identifier_gap(
      'candidate:2024:125', 2024, 'https://cdn.tse.jus.br/source.zip',
      decode('0d', 'hex'), decode(repeat('0e', 12), 'hex'),
      decode(repeat('0f', 16), 'hex'), '${"1".repeat(64)}',
      '${"b".repeat(64)}', '${"c".repeat(64)}', 1,
      'tse-candidate-registry/1.1.0', statement_timestamp(),
      'municipal', 'cm:vereador:125', 'Vereador', '${identityOriginId}',
      'invalid_official_value'
    )
  `);
  assert.equal(replayedUnavailableIdentity.rows[0].status, "unchanged");
  const notDisclosedIdentity = await database.query(`
    select status
    from identity.register_tse_identifier_gap(
      'candidate:2024:126', 2024, 'https://cdn.tse.jus.br/source.zip',
      decode('1d', 'hex'), decode(repeat('1e', 12), 'hex'),
      decode(repeat('1f', 16), 'hex'), '${"2".repeat(64)}',
      '${"b".repeat(64)}', '${"c".repeat(64)}', 1,
      'tse-candidate-registry/1.2.0', statement_timestamp(),
      'municipal', 'cm:vereador:126', 'Vereador', '${identityOriginId}',
      'not_disclosed_by_source'
    )
  `);
  assert.equal(notDisclosedIdentity.rows[0].status, "inserted");
  const privateIdentityCounts = await database.query(`
    select
      (select count(*)::integer from hr.people) as people,
      (select count(*)::integer from private.person_identifiers) as identifiers,
      (select count(*)::integer from identity.person_source_links) as links,
      (select count(*)::integer from private.person_identifier_sources) as sources,
      (select count(*)::integer from private.person_identifier_conflicts) as conflicts,
      (select count(*)::integer from private.person_identifier_gaps) as gaps
  `);
  assert.deepEqual(privateIdentityCounts.rows[0], {
    people: 1,
    identifiers: 1,
    links: 1,
    sources: 4,
    conflicts: 1,
    gaps: 2,
  });
  const canonicalIdentitySource = await database.query(`
    select source_kind
    from identity.person_source_links
    where source_external_id = 'cm:vereador:123'
  `);
  assert.deepEqual(canonicalIdentitySource.rows, [
    { source_kind: 'municipal_councillor' },
  ]);

  const privateIdentityRls = await database.query(`
    select relname, relrowsecurity, relforcerowsecurity
    from pg_catalog.pg_class
    join pg_catalog.pg_namespace on pg_namespace.oid = pg_class.relnamespace
    where pg_namespace.nspname in ('private', 'identity', 'hr')
      and relname in (
        'person_identifier_sources',
        'person_identifier_conflicts',
        'person_identifier_gaps',
        'person_source_links',
        'people'
      )
    order by relname
  `);
  assert.deepEqual(privateIdentityRls.rows, [
    { relname: 'people', relrowsecurity: true, relforcerowsecurity: true },
    {
      relname: 'person_identifier_conflicts',
      relrowsecurity: true,
      relforcerowsecurity: true,
    },
    {
      relname: 'person_identifier_gaps',
      relrowsecurity: true,
      relforcerowsecurity: true,
    },
    {
      relname: 'person_identifier_sources',
      relrowsecurity: true,
      relforcerowsecurity: true,
    },
    {
      relname: 'person_source_links',
      relrowsecurity: true,
      relforcerowsecurity: true,
    },
  ]);

  const controlPlanePrivileges = await database.query(`
    select
      has_table_privilege(
        'collector_worker', 'source.collection_partitions', 'INSERT'
      ) as partition_insert,
      has_table_privilege(
        'collector_worker', 'source.collection_failures', 'INSERT'
      ) as failure_insert,
      has_table_privilege(
        'anon', 'source.collection_partitions', 'SELECT'
      ) as anon_partition_select
  `);
  assert.deepEqual(controlPlanePrivileges.rows[0], {
    partition_insert: true,
    failure_insert: true,
    anon_partition_select: false,
  });

  const seeded = await database.query(`
    select
      (select count(*)::integer from source.data_sources) as sources,
      (select count(*)::integer from source.source_endpoints) as endpoints,
      (select count(*)::integer from storage.buckets where not public) as private_buckets
  `);
  assert.deepEqual(seeded.rows[0], {
    sources: 15,
    endpoints: 31,
    private_buckets: 1,
  });

  const rawArtifactBucket = await database.query(`
    select
      public,
      allowed_mime_types
    from storage.buckets
    where id = 'raw-artifacts'
  `);
  assert.deepEqual(rawArtifactBucket.rows, [
    {
      public: false,
      allowed_mime_types: [
        "application/json",
        "application/octet-stream",
        "application/pdf",
        "application/xml",
        "image/png",
        "text/html",
        "text/plain",
      ],
    },
  ]);

  const transferegovDownloadCatalog = await database.query(`
    select
      source.slug as source_slug,
      endpoint.slug as endpoint_slug,
      endpoint.base_url,
      endpoint.endpoint_kind,
      endpoint.config ->> 'parser_version' as parser_version,
      endpoint.config -> 'required_files' as required_files
    from source.data_sources as source
    join source.source_endpoints as endpoint
      on endpoint.data_source_id = source.id
    where source.slug = 'transferegov-downloads'
    order by endpoint.slug
  `);
  assert.deepEqual(transferegovDownloadCatalog.rows, [
    {
      source_slug: "transferegov-downloads",
      endpoint_slug: "dados-abertos-catalogo",
      base_url:
        "https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/",
      endpoint_kind: "file",
      parser_version: "transferegov-download-catalog/1.1.0",
      required_files: [
        "siconv_convenio.zip",
        "siconv_desembolso.zip",
        "siconv_emenda.zip",
        "siconv_empenho.zip",
        "siconv_pagamento.zip",
        "siconv_proponentes.zip",
        "siconv_proposta.zip",
        "siconv_termo_aditivo.zip",
      ],
    },
    {
      source_slug: "transferegov-downloads",
      endpoint_slug: "emendas-historicas",
      base_url:
        "https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/siconv_emenda.zip",
      endpoint_kind: "file",
      parser_version: "transferegov-historical-amendments/1.0.0",
      required_files: null,
    },
    {
      source_slug: "transferegov-downloads",
      endpoint_slug: "propostas-historicas",
      base_url:
        "https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/siconv_proposta.zip",
      endpoint_kind: "file",
      parser_version: "transferegov-historical-proposals/1.0.0",
      required_files: null,
    },
  ]);

  const transferegovCatalog = await database.query(`
    select source.slug as source_slug, endpoint.slug as endpoint_slug
    from source.data_sources as source
    join source.source_endpoints as endpoint
      on endpoint.data_source_id = source.id
    where source.slug = 'transferegov-parcerias'
    order by endpoint.slug
  `);
  assert.deepEqual(transferegovCatalog.rows, [
    {
      source_slug: "transferegov-parcerias",
      endpoint_slug: "distribuicoes-proposta",
    },
    {
      source_slug: "transferegov-parcerias",
      endpoint_slug: "documentos-habeis-parceria",
    },
    {
      source_slug: "transferegov-parcerias",
      endpoint_slug: "empenhos-parceria",
    },
    {
      source_slug: "transferegov-parcerias",
      endpoint_slug: "ordens-pagamento-documento",
    },
    {
      source_slug: "transferegov-parcerias",
      endpoint_slug: "parcerias-proposta",
    },
    {
      source_slug: "transferegov-parcerias",
      endpoint_slug: "propostas-barreiras",
    },
  ]);

  const transferegovWorkload = await database.query(`
    select
      slug,
      auth_user_id::text as auth_user_id,
      object_prefix,
      can_select,
      can_insert,
      status
    from audit.storage_workload_identities
    where slug = 'transferegov-parcerias-collector'
  `);
  assert.deepEqual(transferegovWorkload.rows, [
    {
      slug: "transferegov-parcerias-collector",
      auth_user_id: "c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a",
      object_prefix: "transferegov/parcerias/",
      can_select: true,
      can_insert: true,
      status: "active",
    },
  ]);

  await database.exec(`
    select set_config(
      'request.jwt.claim.sub',
      'c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a',
      false
    );
  `);
  const transferegovStorageAuthorization = await database.query(`
    select api.can_access_raw_artifact(
      'insert',
      'raw-artifacts',
      'transferegov/parcerias/propostas-barreiras/sha256/aa/file.json'
    ) as municipal_workload_can_insert
  `);
  assert.equal(
    transferegovStorageAuthorization.rows[0].municipal_workload_can_insert,
    true,
  );

  await database.exec(`
    update audit.storage_workload_identities
    set status = 'suspended', can_select = false, can_insert = false
    where slug = 'transferegov-parcerias-collector';
  `);
  const transferegovIdentityFixIndex = migrationNames.indexOf(
    "20260812200000_fix_transferegov_storage_identity.sql",
  );
  assert.notEqual(transferegovIdentityFixIndex, -1);
  await database.exec(migrations[transferegovIdentityFixIndex]);
  const suspendedTransferegovWorkload = await database.query(`
    select status, can_select, can_insert
    from audit.storage_workload_identities
    where slug = 'transferegov-parcerias-collector'
  `);
  assert.deepEqual(suspendedTransferegovWorkload.rows, [
    { status: "suspended", can_select: false, can_insert: false },
  ]);
  await database.exec(`
    update audit.storage_workload_identities
    set status = 'active', can_select = true, can_insert = true
    where slug = 'transferegov-parcerias-collector';
  `);

  const bahiaStateWorkload = await database.query(`
    select
      slug,
      auth_user_id::text as auth_user_id,
      object_prefix,
      can_select,
      can_insert,
      status
    from audit.storage_workload_identities
    where slug = 'bahia-state-amendments-collector'
  `);
  assert.deepEqual(bahiaStateWorkload.rows, [
    {
      slug: "bahia-state-amendments-collector",
      auth_user_id: "c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a",
      object_prefix: "bahia/emendas-estaduais/",
      can_select: true,
      can_insert: true,
      status: "active",
    },
  ]);

  const bahiaStateStorageAuthorization = await database.query(`
    select
      api.can_access_raw_artifact(
        'insert',
        'raw-artifacts',
        'bahia/emendas-estaduais/catalog/sha256/aa/file.json'
      ) as municipal_workload_can_insert,
      api.can_access_raw_artifact(
        'insert',
        'raw-artifacts',
        'pncp/file.json'
      ) as unrelated_prefix_stays_denied
  `);
  assert.deepEqual(bahiaStateStorageAuthorization.rows[0], {
    municipal_workload_can_insert: true,
    unrelated_prefix_stays_denied: false,
  });

  const bahiaSpecialTransferWorkload = await database.query(`
    select
      slug,
      auth_user_id::text as auth_user_id,
      object_prefix,
      can_select,
      can_insert,
      status
    from audit.storage_workload_identities
    where slug = 'bahia-special-transfers-collector'
  `);
  assert.deepEqual(bahiaSpecialTransferWorkload.rows, [
    {
      slug: "bahia-special-transfers-collector",
      auth_user_id: "c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a",
      object_prefix: "bahia/transferencias-especiais/",
      can_select: true,
      can_insert: true,
      status: "active",
    },
  ]);

  const bahiaSpecialTransferEndpoint = await database.query(`
    select
      endpoint.slug,
      endpoint.enabled,
      endpoint.config ->> 'raw_visibility' as raw_visibility,
      endpoint.config ->> 'normalization' as normalization
    from source.source_endpoints as endpoint
    join source.data_sources as source on source.id = endpoint.data_source_id
    where source.slug = 'bahia-open-data'
      and endpoint.slug = 'state-special-transfers'
  `);
  assert.deepEqual(bahiaSpecialTransferEndpoint.rows, [
    {
      slug: "state-special-transfers",
      enabled: true,
      raw_visibility: "private",
      normalization: "published_with_deterministic_author_reconciliation",
    },
  ]);

  const bahiaSpecialTransferStorageAuthorization = await database.query(`
    select
      api.can_access_raw_artifact(
        'insert',
        'raw-artifacts',
        'bahia/transferencias-especiais/archive/sha256/aa/file.zip'
      ) as municipal_workload_can_insert,
      api.can_access_raw_artifact(
        'insert',
        'raw-artifacts',
        'bahia/transferencias-especiais-typo/file.zip'
      ) as adjacent_prefix_stays_denied
  `);
  assert.deepEqual(bahiaSpecialTransferStorageAuthorization.rows[0], {
    municipal_workload_can_insert: true,
    adjacent_prefix_stays_denied: false,
  });

  const transferegovPrivatePrivileges = await database.query(`
    select
      has_table_privilege('anon', 'raw.raw_records', 'SELECT') as anon_raw,
      has_table_privilege(
        'authenticated', 'source.source_endpoints', 'SELECT'
      ) as authenticated_endpoints
  `);
  assert.deepEqual(transferegovPrivatePrivileges.rows[0], {
    anon_raw: false,
    authenticated_endpoints: false,
  });

  // Corredores por fonte: a mesma identidade pode receber um segundo
  // prefixo autorizado, sem ganhar acesso fora da lista fechada.
  await database.exec(`
    insert into audit.storage_workload_identities (
      slug, auth_user_id, bucket_id, object_prefix, status, activated_at
    ) values (
      'barreiras-diario-collector', '${workloadUserId}', 'raw-artifacts',
      'barreiras-diario/gazettes/', 'active', statement_timestamp()
    );
    select set_config('request.jwt.claim.sub', '${workloadUserId}', false);
  `);
  const corridorAuthorization = await database.query(`
    select
      api.can_access_raw_artifact(
        'insert', 'raw-artifacts',
        'barreiras-diario/gazettes/documents/sha256/aa/file.pdf'
      ) as direct_insert,
      api.can_access_raw_artifact(
        'insert', 'raw-artifacts',
        'querido-diario/gazettes/sha256/aa/file.json'
      ) as qd_insert_still_works,
      api.can_access_raw_artifact(
        'insert', 'raw-artifacts', 'pncp/file.json'
      ) as foreign_prefix_denied
  `);
  assert.deepEqual(corridorAuthorization.rows[0], {
    direct_insert: true,
    qd_insert_still_works: true,
    foreign_prefix_denied: false,
  });
  await assert.rejects(
    database.exec(`
      insert into audit.storage_workload_identities (
        slug, auth_user_id, bucket_id, object_prefix, status, activated_at
      ) values (
        'prefixo-invalido', '${workloadUserId}', 'raw-artifacts',
        'pncp/contratos/', 'active', statement_timestamp()
      );
    `),
    /object_prefix/,
  );

  console.log(
    "Migrations e seed executados: controle de coleta e acesso mínimo.",
  );
} finally {
  await database.close();
}
