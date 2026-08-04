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
  assert.equal(relations.rows[0].count, 45);

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
  assert.equal(rlsRelations.rows[0].count, 45);

  const originColumns = await database.query(`
    select count(*)::integer as count
    from information_schema.columns
    where column_name = 'origin_raw_record_id'
      and table_schema in ('org', 'hr', 'procurement', 'finance', 'analysis', 'editorial')
  `);
  assert.equal(originColumns.rows[0].count, 27);

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
  assert.equal(immutableTriggers.rows[0].count, 5);

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

  await database.exec(`
    insert into audit.reviewer_identities (
      auth_user_id, display_name, status, activated_at
    ) values (
      '${reviewerUserId}', 'Revisor de Teste', 'active', statement_timestamp()
    );
    select set_config('request.jwt.claim.sub', '${reviewerUserId}', false);
  `);
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
      methodology_version: "extraction-review-queue/1.6.0",
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
      methodology_version: "approved-gazette-acts/1.5.0",
    },
  ]);

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

  const seeded = await database.query(`
    select
      (select count(*)::integer from source.data_sources) as sources,
      (select count(*)::integer from source.source_endpoints) as endpoints,
      (select count(*)::integer from storage.buckets where not public) as private_buckets
  `);
  assert.deepEqual(seeded.rows[0], {
    sources: 9,
    endpoints: 15,
    private_buckets: 1,
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
    "Migrations e seed executados: 42 tabelas, origem e acesso mínimos.",
  );
} finally {
  await database.close();
}
