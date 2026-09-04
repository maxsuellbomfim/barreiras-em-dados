import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile, readdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { PGlite } from "@electric-sql/pglite";
import { pg_trgm } from "@electric-sql/pglite/contrib/pg_trgm";
import { pgcrypto } from "@electric-sql/pglite/contrib/pgcrypto";

const migrationsUrl = new URL("../../../supabase/migrations/", import.meta.url);
const migrationNames = (await readdir(fileURLToPath(migrationsUrl)))
  .filter((name) => name.endsWith(".sql"))
  .sort();
const migrationContents = await Promise.all(
  migrationNames.map((name) => readFile(fileURLToPath(new URL(name, migrationsUrl)), "utf8")),
);
const rankingMigrationIndex = migrationNames.indexOf(
  "20260812211202_parliamentary_transfer_rankings.sql",
);
assert.notEqual(rankingMigrationIndex, -1, "migration de ranking nao encontrada");
const baselineMigrations = migrationContents.slice(0, rankingMigrationIndex + 1);
const laterMigrations = migrationContents.slice(rankingMigrationIndex + 1);
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
  for (const migration of baselineMigrations) await database.exec(migration);

  const postgrestNotifications = [];
  const stopListening = await database.listen("pgrst", (payload) => {
    postgrestNotifications.push(payload);
  });
  let specialTransferStableViewBefore;
  let seededCurrentSnapshot;
  let seededEmptySnapshot;
  let seededPartialSnapshot;
  for (const [index, migration] of laterMigrations.entries()) {
    if (
      migrationNames[rankingMigrationIndex + 1 + index] ===
      "20260904032851_transferegov_active_snapshot_membership.sql"
    ) {
      await database.exec(`
        insert into source.collection_runs (
          id, source_endpoint_id, idempotency_key, collector_version, status
        ) values
        (
          '00000000-0000-0000-0000-000000008901',
          (select endpoint.id
           from source.source_endpoints endpoint
           join source.data_sources source on source.id = endpoint.data_source_id
           where source.slug = 'transferegov-parcerias'
             and endpoint.slug = 'propostas-barreiras'),
          'transferegov-pre-migration-seed-run', 'test/1', 'succeeded'
        ),
        (
          '00000000-0000-0000-0000-000000008904',
          (select endpoint.id
           from source.source_endpoints endpoint
           join source.data_sources source on source.id = endpoint.data_source_id
           where source.slug = 'transferegov-parcerias'
             and endpoint.slug = 'propostas-barreiras'),
          'transferegov-pre-migration-empty-run', 'test/1', 'succeeded'
        ),
        (
          '00000000-0000-0000-0000-000000008905',
          (select endpoint.id
           from source.source_endpoints endpoint
           join source.data_sources source on source.id = endpoint.data_source_id
           where source.slug = 'transferegov-parcerias'
             and endpoint.slug = 'propostas-barreiras'),
          'transferegov-pre-migration-partial-run', 'test/1', 'failed'
        ),
        (
          '00000000-0000-0000-0000-000000008910',
          (select endpoint.id
           from source.source_endpoints endpoint
           join source.data_sources source on source.id = endpoint.data_source_id
           where source.slug = 'transferegov-parcerias'
             and endpoint.slug = 'propostas-barreiras'),
          'transferegov-pre-migration-newer-good-run', 'test/1', 'succeeded'
        );
        insert into source.collection_partitions (
          source_endpoint_id, partition_key, period_start, period_end, status,
          observed_records, collection_run_id, checkpoint, last_attempted_at,
          completed_at
        ) values
        (
          (select endpoint.id
           from source.source_endpoints endpoint
           join source.data_sources source on source.id = endpoint.data_source_id
           where source.slug = 'transferegov-parcerias'
             and endpoint.slug = 'propostas-barreiras'),
          'fiscal-year:2024', '2024-01-01', '2024-12-31', 'complete', 1,
          '00000000-0000-0000-0000-000000008901',
          '{"fiscal_year":2024,"proposal_records":1}',
          '2026-08-12 16:00:00+00', '2026-08-12 16:00:01+00'
        ),
        (
          (select endpoint.id
           from source.source_endpoints endpoint
           join source.data_sources source on source.id = endpoint.data_source_id
           where source.slug = 'transferegov-parcerias'
             and endpoint.slug = 'propostas-barreiras'),
          'fiscal-year:2023', '2023-01-01', '2023-12-31', 'empty', 0,
          '00000000-0000-0000-0000-000000008904',
          '{"fiscal_year":2023,"proposal_records":0}',
          '2026-08-12 16:01:00+00', '2026-08-12 16:01:01+00'
        ),
        (
          (select endpoint.id
           from source.source_endpoints endpoint
           join source.data_sources source on source.id = endpoint.data_source_id
           where source.slug = 'transferegov-parcerias'
             and endpoint.slug = 'propostas-barreiras'),
          'fiscal-year:2022', '2022-01-01', '2022-12-31', 'partial', 1,
          '00000000-0000-0000-0000-000000008905',
          '{"fiscal_year":2022,"proposal_records":1}',
          '2026-08-12 16:02:00+00', null
        );
        insert into raw.raw_artifacts (
          id, collection_run_id, source_endpoint_id, idempotency_key,
          artifact_kind, source_url, retrieved_at, http_status, content_type,
          byte_size, sha256, object_key, collector_version, parser_version
        ) values
        (
          '00000000-0000-0000-0000-000000008902',
          '00000000-0000-0000-0000-000000008901',
          (select endpoint.id
           from source.source_endpoints endpoint
           join source.data_sources source on source.id = endpoint.data_source_id
           where source.slug = 'transferegov-parcerias'
             and endpoint.slug = 'propostas-barreiras'),
          'transferegov-pre-migration-seed-artifact', 'http_response',
          'https://api-publica.transferegov.gestao.gov.br/parcerias/proposta',
          '2026-08-12 16:00:00+00', 200, 'application/json', 1,
          '${"8".repeat(64)}', 'fixtures/transferegov-pre-migration.json',
          'test/1', 'test/1'
        ),
        (
          '00000000-0000-0000-0000-000000008908',
          '00000000-0000-0000-0000-000000008905',
          (select endpoint.id
           from source.source_endpoints endpoint
           join source.data_sources source on source.id = endpoint.data_source_id
           where source.slug = 'transferegov-parcerias'
             and endpoint.slug = 'propostas-barreiras'),
          'transferegov-pre-migration-failed-artifact', 'http_response',
          'https://api-publica.transferegov.gestao.gov.br/parcerias/proposta',
          '2026-08-12 16:02:00+00', 200, 'application/json', 1,
          '${"c".repeat(64)}', 'fixtures/transferegov-failed-partial.json',
          'test/1', 'test/1'
        ),
        (
          '00000000-0000-0000-0000-000000008911',
          '00000000-0000-0000-0000-000000008910',
          (select endpoint.id
           from source.source_endpoints endpoint
           join source.data_sources source on source.id = endpoint.data_source_id
           where source.slug = 'transferegov-parcerias'
             and endpoint.slug = 'propostas-barreiras'),
          'transferegov-pre-migration-newer-good-artifact', 'http_response',
          'https://api-publica.transferegov.gestao.gov.br/parcerias/proposta',
          '2026-08-12 16:03:00+00', 200, 'application/json', 1,
          '${"e".repeat(64)}', 'fixtures/transferegov-newer-good.json',
          'test/1', 'test/1'
        );
        insert into raw.raw_records (
          id, raw_artifact_id, source_record_key, record_type, record_index,
          payload, payload_sha256, parser_version, idempotency_key, collected_at
        ) values (
          '00000000-0000-0000-0000-000000008903',
          '00000000-0000-0000-0000-000000008902',
          'transferegov:proposta:seed-2024', 'transferegov_proposta', 0,
          '{"id_proposta":"8903","ano_proposta":2024}',
          '${"9".repeat(64)}', 'test/1',
          'transferegov-pre-migration-seed-record',
          '2026-08-12 16:00:00+00'
        ),
        (
          '00000000-0000-0000-0000-000000008906',
          '00000000-0000-0000-0000-000000008902',
          'transferegov:proposta:stale-2023', 'transferegov_proposta', 1,
          '{"id_proposta":"8906","ano_proposta":2023}',
          '${"a".repeat(64)}', 'test/1',
          'transferegov-pre-migration-stale-empty-record',
          '2026-08-12 16:00:00+00'
        ),
        (
          '00000000-0000-0000-0000-000000008907',
          '00000000-0000-0000-0000-000000008902',
          'transferegov:proposta:last-good-2022', 'transferegov_proposta', 2,
          '{"id_proposta":"8907","ano_proposta":2022}',
          '${"b".repeat(64)}', 'test/1',
          'transferegov-pre-migration-last-good-partial-record',
          '2026-08-12 16:00:00+00'
        ),
        (
          '00000000-0000-0000-0000-000000008909',
          '00000000-0000-0000-0000-000000008908',
          'transferegov:proposta:failed-2022', 'transferegov_proposta', 0,
          '{"id_proposta":"8909","ano_proposta":2022}',
          '${"d".repeat(64)}', 'test/1',
          'transferegov-pre-migration-failed-partial-record',
          '2026-08-12 16:02:00+00'
        ),
        (
          '00000000-0000-0000-0000-000000008912',
          '00000000-0000-0000-0000-000000008911',
          'transferegov:proposta:newer-good-2022', 'transferegov_proposta', 0,
          '{"id_proposta":"8912","ano_proposta":2022}',
          '${"f".repeat(64)}', 'test/1',
          'transferegov-pre-migration-newer-good-record',
          '2026-08-12 16:03:00+00'
        );
      `);
    }
    if (
      migrationNames[rankingMigrationIndex + 1 + index] ===
      "20260903170000_materialize_bahia_special_transfer_payments.sql"
    ) {
      specialTransferStableViewBefore = await database.query(`
        select c.oid::integer as view_oid
        from pg_class as c
        join pg_namespace as n on n.oid = c.relnamespace
        where n.nspname = 'territory'
          and c.relname = 'latest_bahia_special_transfer_payment_candidates'
          and c.relkind = 'v'
      `);
      assert.equal(specialTransferStableViewBefore.rows.length, 1);
    }
    await database.exec(migration);
    if (
      migrationNames[rankingMigrationIndex + 1 + index] ===
      "20260904032851_transferegov_active_snapshot_membership.sql"
    ) {
      seededCurrentSnapshot = await database.query(`
        select manifest.status, manifest.record_count,
          manifest.snapshot_fingerprint,
          member.raw_record_id::text as raw_record_id
        from source.transferegov_snapshot_manifests as manifest
        join source.transferegov_snapshot_records as member
          on member.snapshot_id = manifest.id
        where manifest.collection_run_id =
          '00000000-0000-0000-0000-000000008901'
          and manifest.fiscal_year = 2024
      `);
      seededEmptySnapshot = await database.query(`
        select manifest.status, manifest.record_count,
          manifest.snapshot_fingerprint,
          count(member.raw_record_id)::integer as member_count
        from source.transferegov_snapshot_manifests as manifest
        left join source.transferegov_snapshot_records as member
          on member.snapshot_id = manifest.id
        where manifest.collection_run_id =
          '00000000-0000-0000-0000-000000008904'
        group by manifest.id
      `);
      seededPartialSnapshot = await database.query(`
        select manifest.status, manifest.record_count,
          manifest.collection_run_id::text as collection_run_id,
          member.raw_record_id::text as raw_record_id
        from source.transferegov_snapshot_manifests as manifest
        join source.transferegov_snapshot_records as member
          on member.snapshot_id = manifest.id
        where manifest.fiscal_year = 2022
      `);
      await database.exec(`
        delete from source.transferegov_snapshot_records
        where snapshot_id in (
          select id from source.transferegov_snapshot_manifests
          where fiscal_year in (2022, 2023, 2024)
        );
        delete from source.transferegov_snapshot_manifests
        where fiscal_year in (2022, 2023, 2024);
        delete from source.collection_partitions
        where collection_run_id in (
          '00000000-0000-0000-0000-000000008901',
          '00000000-0000-0000-0000-000000008904',
          '00000000-0000-0000-0000-000000008905'
        );
      `);
    }
  }
  await new Promise((resolve) => setImmediate(resolve));
  await stopListening();
  assert.ok(
    postgrestNotifications.includes("reload schema"),
    "migrations posteriores ao ranking devem recarregar o schema do PostgREST",
  );

  assert.deepEqual(seededCurrentSnapshot?.rows, [{
    status: "active",
    record_count: 1,
    snapshot_fingerprint: createHash("sha256").update(
      `transferegov_proposta\x1ftransferegov:proposta:seed-2024\x1f${"9".repeat(64)}`,
      "utf8",
    ).digest("hex"),
    raw_record_id: "00000000-0000-0000-0000-000000008903",
  }]);
  assert.deepEqual(seededEmptySnapshot?.rows, [{
    status: "active",
    record_count: 0,
    snapshot_fingerprint: createHash("sha256").update("", "utf8").digest("hex"),
    member_count: 0,
  }]);
  assert.deepEqual(seededPartialSnapshot?.rows, [{
    status: "active",
    record_count: 1,
    collection_run_id: "00000000-0000-0000-0000-000000008910",
    raw_record_id: "00000000-0000-0000-0000-000000008912",
  }]);

  const territorySchema = await database.query(`
    select to_regnamespace('territory')::text as territory_schema
  `);
  assert.deepEqual(territorySchema.rows, [{ territory_schema: "territory" }]);

  const specialTransferStableViewAfter = await database.query(`
    select c.oid::integer as view_oid
    from pg_class as c
    join pg_namespace as n on n.oid = c.relnamespace
    where n.nspname = 'territory'
      and c.relname = 'latest_bahia_special_transfer_payment_candidates'
      and c.relkind = 'v'
  `);
  assert.deepEqual(
    specialTransferStableViewAfter.rows,
    specialTransferStableViewBefore.rows,
    "a view estável deve preservar o OID ao apontar para o snapshot",
  );

  const stateLoaStudyContract = await database.query(`
    select to_regprocedure(
      'api.get_public_bahia_state_loa_study(smallint,integer,integer)'
    )::text as state_loa_study_rpc
  `);
  assert.deepEqual(stateLoaStudyContract.rows, [{
    state_loa_study_rpc:
      "api.get_public_bahia_state_loa_study(smallint,integer,integer)",
  }]);

  const filteredStateLoaStudyContract = await database.query(`
    select to_regprocedure(
      'api.get_public_bahia_state_loa_study_filtered(smallint,integer,integer,text,text,text)'
    )::text as state_loa_study_filtered_rpc
  `);
  assert.deepEqual(filteredStateLoaStudyContract.rows, [{
    state_loa_study_filtered_rpc:
      "api.get_public_bahia_state_loa_study_filtered(smallint,integer,integer,text,text,text)",
  }]);

  const contracts = await database.query(`
    select
      to_regclass('territory.parliamentary_transfers')::text as transfer_projection,
      to_regclass('territory.federal_transfer_proposals')::text
        as historical_proposal_projection,
      to_regclass('territory.historical_parliamentary_amendments')::text
        as historical_amendment_projection,
      to_regclass('territory.federal_transfer_proposal_scope')::text
        as territorial_scope_projection,
      to_regclass('territory.reconciled_parliamentary_transfers')::text
        as reconciled_transfer_projection,
      to_regclass('territory.bahia_state_loa_execution_reconciliation')::text
        as state_loa_execution_reconciliation,
      to_regclass(
        'territory.bahia_state_loa_execution_reconciliation_snapshot'
      )::text as state_loa_execution_reconciliation_snapshot,
      to_regclass('political.parliamentary_transfer_author_crosswalk')::text
        as author_crosswalk,
      to_regclass('political.legislative_terms')::text as legislative_terms,
      to_regclass('raw.raw_records_transferegov_latest_idx')::text as latest_index,
      to_regclass('raw.raw_records_transferegov_proposal_idx')::text as proposal_index,
      to_regclass('raw.raw_records_transferegov_partnership_idx')::text as partnership_index,
      to_regclass('raw.raw_records_transferegov_document_idx')::text as document_index,
      to_regprocedure(
        'api.get_public_parliamentary_transfer_ranking(text,smallint,integer)'
      )::text as ranking_rpc,
      to_regprocedure(
        'api.get_public_parliamentary_transfers(smallint,text,integer)'
      )::text as detail_rpc,
      to_regprocedure(
        'api.get_public_parliamentary_transfer_coverage(smallint,smallint)'
      )::text as coverage_rpc,
      to_regprocedure(
        'api.get_public_federal_transfer_proposals(smallint,text,integer)'
      )::text as historical_proposal_rpc,
      to_regprocedure(
        'api.get_public_historical_parliamentary_amendments(smallint,text,integer)'
      )::text as historical_amendment_rpc,
      to_regprocedure(
        'api.get_public_historical_parliamentary_amendment_ranking(text,smallint,integer)'
      )::text as historical_amendment_ranking_rpc,
      to_regprocedure(
        'api.get_public_federal_transfer_scope_summary()'
      )::text as territorial_scope_rpc,
      to_regprocedure(
        'api.get_public_reconciled_parliamentary_transfers(smallint,text,integer)'
      )::text as reconciled_transfer_rpc,
      to_regprocedure(
        'api.get_public_reconciled_parliamentary_transfer_ranking(text,smallint,integer)'
      )::text as reconciled_ranking_rpc,
      to_regprocedure(
        'api.get_public_parliamentary_transfer_reconciliation_summary()'
      )::text as reconciliation_summary_rpc,
      to_regprocedure(
        'api.get_public_bahia_state_loa_execution(smallint,text,integer)'
      )::text as state_loa_execution_rpc,
      to_regprocedure(
        'api.get_public_bahia_state_loa_execution_summary(smallint)'
      )::text as state_loa_execution_summary_rpc,
      to_regprocedure(
        'api.get_public_bahia_state_loa_representative_contributions(integer)'
      )::text as state_loa_representative_contributions_rpc,
      to_regprocedure(
        'api.get_public_parliamentary_legislature_rankings(text,smallint,integer)'
      )::text as legislature_rankings_rpc,
      to_regprocedure(
        'api.get_public_parliamentary_legislature_year_coverage(text,smallint)'
      )::text as legislature_year_coverage_rpc,
      to_regprocedure(
        'territory.refresh_bahia_state_loa_execution_reconciliation_snapshot()'
      )::text as state_loa_execution_snapshot_refresh,
      has_schema_privilege('anon', 'territory', 'USAGE') as anon_territory_usage,
      has_function_privilege(
        'anon',
        'api.get_public_parliamentary_transfer_ranking(text,smallint,integer)',
        'EXECUTE'
      ) as anon_ranking_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_parliamentary_transfers(smallint,text,integer)',
        'EXECUTE'
      ) as anon_detail_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_parliamentary_transfer_coverage(smallint,smallint)',
        'EXECUTE'
      ) as anon_coverage_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_federal_transfer_proposals(smallint,text,integer)',
        'EXECUTE'
      ) as anon_historical_proposal_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_historical_parliamentary_amendments(smallint,text,integer)',
        'EXECUTE'
      ) as anon_historical_amendment_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_historical_parliamentary_amendment_ranking(text,smallint,integer)',
        'EXECUTE'
      ) as anon_historical_amendment_ranking_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_federal_transfer_scope_summary()',
        'EXECUTE'
      ) as anon_territorial_scope_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_reconciled_parliamentary_transfers(smallint,text,integer)',
        'EXECUTE'
      ) as anon_reconciled_transfer_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_reconciled_parliamentary_transfer_ranking(text,smallint,integer)',
        'EXECUTE'
      ) as anon_reconciled_ranking_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_parliamentary_transfer_reconciliation_summary()',
        'EXECUTE'
      ) as anon_reconciliation_summary_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_bahia_state_loa_execution(smallint,text,integer)',
        'EXECUTE'
      ) as anon_state_loa_execution_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_bahia_state_loa_execution_summary(smallint)',
        'EXECUTE'
      ) as anon_state_loa_execution_summary_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_bahia_state_loa_representative_contributions(integer)',
        'EXECUTE'
      ) as anon_state_loa_representative_contributions_rpc,
      has_table_privilege(
        'anon',
        'political.legislative_terms',
        'SELECT'
      ) as anon_legislative_terms_select,
      has_function_privilege(
        'anon',
        'api.get_public_parliamentary_legislature_rankings(text,smallint,integer)',
        'EXECUTE'
      ) as anon_legislature_rankings_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_parliamentary_legislature_year_coverage(text,smallint)',
        'EXECUTE'
      ) as anon_legislature_year_coverage_rpc,
      has_function_privilege(
        'anon',
        'territory.refresh_bahia_state_loa_execution_reconciliation_snapshot()',
        'EXECUTE'
      ) as anon_state_loa_execution_snapshot_refresh,
      has_function_privilege(
        'collector_worker',
        'territory.refresh_bahia_state_loa_execution_reconciliation_snapshot()',
        'EXECUTE'
      ) as worker_state_loa_execution_snapshot_refresh
  `);
  assert.deepEqual(contracts.rows, [{
    transfer_projection: "territory.parliamentary_transfers",
    historical_proposal_projection: "territory.federal_transfer_proposals",
    historical_amendment_projection:
      "territory.historical_parliamentary_amendments",
    territorial_scope_projection: "territory.federal_transfer_proposal_scope",
    reconciled_transfer_projection:
      "territory.reconciled_parliamentary_transfers",
    state_loa_execution_reconciliation:
      "territory.bahia_state_loa_execution_reconciliation",
    state_loa_execution_reconciliation_snapshot:
      "territory.bahia_state_loa_execution_reconciliation_snapshot",
    author_crosswalk: "political.parliamentary_transfer_author_crosswalk",
    legislative_terms: "political.legislative_terms",
    latest_index: "raw.raw_records_transferegov_latest_idx",
    proposal_index: "raw.raw_records_transferegov_proposal_idx",
    partnership_index: "raw.raw_records_transferegov_partnership_idx",
    document_index: "raw.raw_records_transferegov_document_idx",
    ranking_rpc:
      "api.get_public_parliamentary_transfer_ranking(text,smallint,integer)",
    detail_rpc: "api.get_public_parliamentary_transfers(smallint,text,integer)",
    coverage_rpc:
      "api.get_public_parliamentary_transfer_coverage(smallint,smallint)",
    historical_proposal_rpc:
      "api.get_public_federal_transfer_proposals(smallint,text,integer)",
    historical_amendment_rpc:
      "api.get_public_historical_parliamentary_amendments(smallint,text,integer)",
    historical_amendment_ranking_rpc:
      "api.get_public_historical_parliamentary_amendment_ranking(text,smallint,integer)",
    territorial_scope_rpc: "api.get_public_federal_transfer_scope_summary()",
    reconciled_transfer_rpc:
      "api.get_public_reconciled_parliamentary_transfers(smallint,text,integer)",
    reconciled_ranking_rpc:
      "api.get_public_reconciled_parliamentary_transfer_ranking(text,smallint,integer)",
    reconciliation_summary_rpc:
      "api.get_public_parliamentary_transfer_reconciliation_summary()",
    state_loa_execution_rpc:
      "api.get_public_bahia_state_loa_execution(smallint,text,integer)",
    state_loa_execution_summary_rpc:
      "api.get_public_bahia_state_loa_execution_summary(smallint)",
    state_loa_representative_contributions_rpc:
      "api.get_public_bahia_state_loa_representative_contributions(integer)",
    legislature_rankings_rpc:
      "api.get_public_parliamentary_legislature_rankings(text,smallint,integer)",
    legislature_year_coverage_rpc:
      "api.get_public_parliamentary_legislature_year_coverage(text,smallint)",
    state_loa_execution_snapshot_refresh:
      "territory.refresh_bahia_state_loa_execution_reconciliation_snapshot()",
    anon_territory_usage: false,
    anon_ranking_rpc: true,
    anon_detail_rpc: true,
    anon_coverage_rpc: true,
    anon_historical_proposal_rpc: true,
    anon_historical_amendment_rpc: true,
    anon_historical_amendment_ranking_rpc: true,
    anon_territorial_scope_rpc: true,
    anon_reconciled_transfer_rpc: true,
    anon_reconciled_ranking_rpc: true,
    anon_reconciliation_summary_rpc: true,
    anon_state_loa_execution_rpc: true,
    anon_state_loa_execution_summary_rpc: true,
    anon_state_loa_representative_contributions_rpc: true,
    anon_legislative_terms_select: false,
    anon_legislature_rankings_rpc: true,
    anon_legislature_year_coverage_rpc: true,
    anon_state_loa_execution_snapshot_refresh: false,
    worker_state_loa_execution_snapshot_refresh: true,
  }]);

  const currentSnapshotContracts = await database.query(`
    select
      to_regclass('source.transferegov_snapshot_manifests')::text
        as manifest_table,
      to_regclass('source.transferegov_snapshot_records')::text
        as membership_table,
      to_regprocedure(
        'source.stage_transferegov_snapshot(uuid,smallint,jsonb,text)'
      )::text as stage_rpc,
      has_function_privilege(
        'collector_worker',
        'source.stage_transferegov_snapshot(uuid,smallint,jsonb,text)',
        'EXECUTE'
      ) as worker_stage_execute,
      has_function_privilege(
        'anon',
        'source.stage_transferegov_snapshot(uuid,smallint,jsonb,text)',
        'EXECUTE'
      ) as anon_stage_execute,
      (select relrowsecurity
       from pg_class
       where oid = 'source.transferegov_snapshot_manifests'::regclass)
        as manifest_rls,
      (select relrowsecurity
       from pg_class
       where oid = 'source.transferegov_snapshot_records'::regclass)
        as membership_rls
  `);
  assert.deepEqual(currentSnapshotContracts.rows, [{
    manifest_table: "source.transferegov_snapshot_manifests",
    membership_table: "source.transferegov_snapshot_records",
    stage_rpc:
      "source.stage_transferegov_snapshot(uuid,smallint,jsonb,text)",
    worker_stage_execute: true,
    anon_stage_execute: false,
    manifest_rls: true,
    membership_rls: true,
  }]);

  const activeRecordDefinition = await database.query(`
    select pg_get_viewdef(
      'territory.latest_transferegov_records'::regclass,
      true
    ) as definition
  `);
  assert.match(
    activeRecordDefinition.rows[0].definition,
    /source\.transferegov_snapshot_records/,
  );
  assert.match(
    activeRecordDefinition.rows[0].definition,
    /source\.transferegov_snapshot_manifests/,
  );
  assert.doesNotMatch(activeRecordDefinition.rows[0].definition, /distinct on/i);

  const stateExecutionCoverageContracts = await database.query(`
    select
      to_regclass(
        'territory.bahia_state_execution_annual_coverage_snapshot'
      )::text as coverage_snapshot,
      to_regclass(
        'raw.extraction_jobs_bahia_state_execution_latest_idx'
      )::text as latest_job_index,
      to_regclass(
        'raw.raw_artifacts_bahia_state_execution_pending_idx'
      )::text as pending_artifact_index,
      to_regclass(
        'raw.raw_records_bahia_state_archive_member_idx'
      )::text as archive_member_index,
      to_regclass(
        'raw.extraction_jobs_bahia_state_artifact_idx'
      )::text as artifact_job_index,
      to_regprocedure(
        'territory.refresh_bahia_state_execution_annual_coverage_snapshot()'
      )::text as refresh_function,
      to_regprocedure(
        'api.get_public_bahia_state_execution_annual_coverage()'
      )::text as public_rpc
  `);
  assert.deepEqual(stateExecutionCoverageContracts.rows, [{
    coverage_snapshot:
      "territory.bahia_state_execution_annual_coverage_snapshot",
    latest_job_index: "raw.extraction_jobs_bahia_state_execution_latest_idx",
    pending_artifact_index:
      "raw.raw_artifacts_bahia_state_execution_pending_idx",
    archive_member_index: "raw.raw_records_bahia_state_archive_member_idx",
    artifact_job_index: "raw.extraction_jobs_bahia_state_artifact_idx",
    refresh_function:
      "territory.refresh_bahia_state_execution_annual_coverage_snapshot()",
    public_rpc: "api.get_public_bahia_state_execution_annual_coverage()",
  }]);

  const stateExecutionCoveragePrivileges = await database.query(`
    select
      has_function_privilege(
        'anon',
        'api.get_public_bahia_state_execution_annual_coverage()',
        'EXECUTE'
      ) as anon_public_rpc,
      has_function_privilege(
        'anon',
        'territory.refresh_bahia_state_execution_annual_coverage_snapshot()',
        'EXECUTE'
      ) as anon_refresh
  `);
  assert.deepEqual(stateExecutionCoveragePrivileges.rows, [{
    anon_public_rpc: true,
    anon_refresh: false,
  }]);

  const specialTransferContracts = await database.query(`
    select
      to_regclass(
        'political.parliamentary_author_code_crosswalk'
      )::text as author_code_crosswalk,
      to_regclass(
        'territory.bahia_special_transfer_payments'
      )::text as payment_projection,
      to_regclass(
        'territory.bahia_special_transfer_federal_links'
      )::text as federal_link_projection,
      to_regclass(
        'territory.latest_bahia_special_transfer_annual_coverage'
      )::text as annual_coverage_projection,
      to_regclass(
        'raw.extraction_results_bahia_special_transfer_annual_latest_idx'
      )::text as annual_coverage_latest_index,
      to_regprocedure(
        'api.get_public_bahia_special_transfer_payments(smallint,text,integer)'
      )::text as payment_rpc,
      to_regprocedure(
        'api.get_public_bahia_special_transfer_ranking(smallint,integer)'
      )::text as ranking_rpc,
      to_regprocedure(
        'api.get_public_bahia_special_transfer_payments(integer,smallint,text,integer)'
      )::text as paginated_payment_rpc,
      to_regprocedure(
        'api.get_public_bahia_special_transfer_ranking(integer,smallint,integer)'
      )::text as paginated_ranking_rpc,
      to_regprocedure(
        'api.get_public_bahia_special_transfer_annual_coverage()'
      )::text as annual_coverage_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_bahia_special_transfer_payments(smallint,text,integer)',
        'EXECUTE'
      ) as anon_payment_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_bahia_special_transfer_ranking(smallint,integer)',
        'EXECUTE'
      ) as anon_ranking_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_bahia_special_transfer_payments(integer,smallint,text,integer)',
        'EXECUTE'
      ) as anon_paginated_payment_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_bahia_special_transfer_ranking(integer,smallint,integer)',
        'EXECUTE'
      ) as anon_paginated_ranking_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_bahia_special_transfer_annual_coverage()',
        'EXECUTE'
      ) as anon_annual_coverage_rpc,
      has_table_privilege(
        'anon',
        'political.parliamentary_author_code_crosswalk',
        'SELECT'
      ) as anon_crosswalk_select
  `);
  assert.deepEqual(specialTransferContracts.rows, [{
    author_code_crosswalk: "political.parliamentary_author_code_crosswalk",
    payment_projection: "territory.bahia_special_transfer_payments",
    federal_link_projection:
      "territory.bahia_special_transfer_federal_links",
    annual_coverage_projection:
      "territory.latest_bahia_special_transfer_annual_coverage",
    annual_coverage_latest_index:
      "raw.extraction_results_bahia_special_transfer_annual_latest_idx",
    payment_rpc:
      "api.get_public_bahia_special_transfer_payments(smallint,text,integer)",
    ranking_rpc:
      "api.get_public_bahia_special_transfer_ranking(smallint,integer)",
    paginated_payment_rpc:
      "api.get_public_bahia_special_transfer_payments(integer,smallint,text,integer)",
    paginated_ranking_rpc:
      "api.get_public_bahia_special_transfer_ranking(integer,smallint,integer)",
    annual_coverage_rpc:
      "api.get_public_bahia_special_transfer_annual_coverage()",
    anon_payment_rpc: true,
    anon_ranking_rpc: true,
    anon_paginated_payment_rpc: true,
    anon_paginated_ranking_rpc: true,
    anon_annual_coverage_rpc: true,
    anon_crosswalk_select: false,
  }]);

  const currentCguDocumentAuthorCrosswalk = await database.query(`
    select source_author_code, source_author_name, official_author_name,
      representative_source_kind, representative_external_id,
      representative_profile_url, valid_from_year, valid_to_year,
      review_status, methodology_version
    from political.parliamentary_author_code_crosswalk
    where source_system = 'federal_amendment_author_code'
      and source_author_code in ('4319', '4460')
    order by source_author_code
  `);
  assert.deepEqual(currentCguDocumentAuthorCrosswalk.rows, [
    {
      source_author_code: "4319",
      source_author_name: "CAPITAO ALDEN",
      official_author_name: "Capitão Alden",
      representative_source_kind: "federal",
      representative_external_id: "220690",
      representative_profile_url:
        "https://www.camara.leg.br/deputados/220690",
      valid_from_year: 2023,
      valid_to_year: 2027,
      review_status: "approved",
      methodology_version:
        "parliamentary-author-code-crosswalk/1.1.0",
    },
    {
      source_author_code: "4460",
      source_author_name: "RICARDO MAIA",
      official_author_name: "Ricardo Maia",
      representative_source_kind: "federal",
      representative_external_id: "220694",
      representative_profile_url:
        "https://www.camara.leg.br/deputados/220694",
      valid_from_year: 2023,
      valid_to_year: 2027,
      review_status: "approved",
      methodology_version:
        "parliamentary-author-code-crosswalk/1.1.0",
    },
  ]);

  const completedStateAuthorCrosswalk = await database.query(`
    select author_key, representative_source_kind,
      representative_external_id, review_status
    from political.parliamentary_transfer_author_crosswalk
    where author_key in (
      'hassan', 'luciano simoes filho', 'marcone amaral'
    )
    order by author_key
  `);
  assert.deepEqual(completedStateAuthorCrosswalk.rows, [
    {
      author_key: "hassan",
      representative_source_kind: "state",
      representative_external_id: "932105",
      review_status: "approved",
    },
    {
      author_key: "luciano simoes filho",
      representative_source_kind: "state",
      representative_external_id: "921278",
      review_status: "approved",
    },
    {
      author_key: "marcone amaral",
      representative_source_kind: "state",
      representative_external_id: "935240",
      review_status: "approved",
    },
  ]);
  const completedFederalAuthorCrosswalk = await database.query(`
    select author_key, representative_source_kind,
      representative_external_id, review_status
    from political.parliamentary_transfer_author_crosswalk
    where author_key in ('claudio cajado', 'rogeria santos')
    order by author_key
  `);
  assert.deepEqual(completedFederalAuthorCrosswalk.rows, [
    {
      author_key: "claudio cajado",
      representative_source_kind: "federal",
      representative_external_id: "74537",
      review_status: "approved",
    },
    {
      author_key: "rogeria santos",
      representative_source_kind: "federal",
      representative_external_id: "220695",
      review_status: "approved",
    },
  ]);
  const marconeTseCrosswalk = await database.query(`
    select representative_external_id, candidate_id, review_status
    from political.representative_tse_crosswalk
    where source_kind = 'state'
      and representative_external_id = '935240'
      and election_year = 2022
      and office = 'Deputado Estadual'
  `);
  assert.deepEqual(marconeTseCrosswalk.rows, [{
    representative_external_id: "935240",
    candidate_id: "50001607304",
    review_status: "approved",
  }]);

  const stateLoaPublicFunctionDefinitions = await database.query(`
    select proname, pg_get_functiondef(procedure.oid) as definition
    from pg_proc as procedure
    join pg_namespace as namespace on namespace.oid = procedure.pronamespace
    where namespace.nspname = 'api'
      and procedure.proname in (
        'get_public_bahia_state_loa_execution',
        'get_public_bahia_state_loa_execution_summary',
        'get_public_bahia_state_loa_representative_contributions'
      )
    order by proname
  `);
  for (const row of stateLoaPublicFunctionDefinitions.rows) {
    assert.match(
      row.definition,
      /territory\.bahia_state_loa_execution_reconciliation_snapshot/,
      `${row.proname} deve ler a projecao materializada`,
    );
    assert.doesNotMatch(
      row.definition,
      /from territory\.bahia_state_loa_execution_reconciliation as reconciliation/,
      `${row.proname} nao pode recalcular JSON bruto em requisicao publica`,
    );
  }

  const legislatureRankingDefinition = await database.query(`
    select pg_get_functiondef(procedure.oid) as definition
    from pg_proc as procedure
    join pg_namespace as namespace on namespace.oid = procedure.pronamespace
    where namespace.nspname = 'api'
      and procedure.proname = 'get_public_parliamentary_legislature_rankings'
  `);
  assert.equal(legislatureRankingDefinition.rows.length, 1);
  assert.match(
    legislatureRankingDefinition.rows[0].definition,
    /territory\.bahia_state_loa_execution_reconciliation_snapshot/,
    "ranking por legislatura deve usar o snapshot estadual materializado",
  );
  assert.match(
    legislatureRankingDefinition.rows[0].definition,
    /territory\.reconciled_parliamentary_transfers/,
    "ranking federal deve usar a serie reconciliada",
  );
  assert.doesNotMatch(
    legislatureRankingDefinition.rows[0].definition,
    /raw\.(raw_records|extraction_results)/,
    "RPC publica nao pode recalcular registros brutos",
  );

  await database.exec(`
    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version, status
    ) values (
      '00000000-0000-0000-0000-000000009001',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'transferegov-parcerias'
         and endpoint.slug = 'propostas-barreiras'),
      'parliamentary-transfer-fixture-run', 'test/1', 'succeeded'
    );
    insert into source.collection_partitions (
      source_endpoint_id, partition_key, period_start, period_end, status,
      observed_records, collection_run_id, checkpoint, last_attempted_at,
      completed_at
    ) values
      (
        (select endpoint.id
         from source.source_endpoints endpoint
         join source.data_sources source on source.id = endpoint.data_source_id
         where source.slug = 'transferegov-parcerias'
           and endpoint.slug = 'propostas-barreiras'),
        'fiscal-year:2021', '2021-01-01', '2021-12-31', 'empty', 0,
        '00000000-0000-0000-0000-000000009001',
        '{"fiscal_year":2021,"proposal_records":0}',
        '2026-08-12 17:00:00+00', '2026-08-12 17:00:01+00'
      ),
      (
        (select endpoint.id
         from source.source_endpoints endpoint
         join source.data_sources source on source.id = endpoint.data_source_id
         where source.slug = 'transferegov-parcerias'
           and endpoint.slug = 'propostas-barreiras'),
        'fiscal-year:2025', '2025-01-01', '2025-12-31', 'complete', 10,
        '00000000-0000-0000-0000-000000009001',
        '{"fiscal_year":2025,"proposal_records":3}',
        '2026-08-12 18:00:00+00', '2026-08-12 18:00:01+00'
      ),
      (
        (select endpoint.id
         from source.source_endpoints endpoint
         join source.data_sources source on source.id = endpoint.data_source_id
         where source.slug = 'transferegov-parcerias'
           and endpoint.slug = 'propostas-barreiras'),
        'fiscal-year:2022', '2022-01-01', '2022-12-31', 'empty', 0,
        '00000000-0000-0000-0000-000000009001',
        '{"fiscal_year":2022,"proposal_records":0}',
        '2026-08-12 18:10:00+00', '2026-08-12 18:10:01+00'
      ),
      (
        (select endpoint.id
         from source.source_endpoints endpoint
         join source.data_sources source on source.id = endpoint.data_source_id
         where source.slug = 'transferegov-parcerias'
           and endpoint.slug = 'propostas-barreiras'),
        'fiscal-year:2026', '2026-01-01', '2026-12-31', 'failed', 0,
        '00000000-0000-0000-0000-000000009001',
        '{"fiscal_year":2026,"proposal_records":0}',
        '2026-08-12 18:20:00+00', null
      );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, idempotency_key, artifact_kind,
      source_url, retrieved_at, byte_size, sha256, object_key, collector_version
    ) values (
      '00000000-0000-0000-0000-000000009002',
      '00000000-0000-0000-0000-000000009001',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'transferegov-parcerias'
         and endpoint.slug = 'propostas-barreiras'),
      'parliamentary-transfer-fixture-artifact', 'http_response',
      'https://api-publica.transferegov.gestao.gov.br/parcerias/proposta?cd_ibge_recebedor=2903201',
      '2026-08-12 18:00:00+00', 1000, '${"a".repeat(64)}',
      'fixtures/transferegov.json', 'test/1'
    );
    insert into raw.raw_records (
      id, raw_artifact_id, source_record_key, record_type, record_index,
      payload, payload_sha256, parser_version, idempotency_key, collected_at
    ) values
      (
        '00000000-0000-0000-0000-000000009010',
        '00000000-0000-0000-0000-000000009002', 'transferegov:proposta:9274',
        'transferegov_proposta', 0,
        '{"id_proposta":9274,"ano_proposta":2025,"ds_objeto":"Incremento da media e alta complexidade","vl_total_planejamento_gastos":250000,"nm_ente_recebedor":"Fundo Municipal de Saude de Barreiras","situacao_proposta":"Aprovada"}',
        '${"b".repeat(64)}', 'test/1', 'parliamentary-record-0001',
        '2026-08-12 18:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009011',
        '00000000-0000-0000-0000-000000009002', 'transferegov:distribuicao:14886',
        'transferegov_distribuicao_recurso', 1,
        '{"id_distribuicao_recurso_proposta":14886,"id_proposta":9274,"in_tipo_distribuicao":"Emenda","in_tipo_emenda_parlamentar_proposta":"Individual","nm_parlamentar_proposta":"RICARDO MAIA","nr_emenda_proposta":"2025.4460.0002","valor_emenda":250000}',
        '${"c".repeat(64)}', 'test/1', 'parliamentary-record-0002',
        '2026-08-12 18:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009012',
        '00000000-0000-0000-0000-000000009002', 'transferegov:proposta:30854',
        'transferegov_proposta', 2,
        '{"id_proposta":30854,"ano_proposta":2025,"ds_objeto":"Incremento da media e alta complexidade","vl_total_planejamento_gastos":5000000,"nm_ente_recebedor":"Fundo Municipal de Saude de Barreiras","situacao_proposta":"Aprovada"}',
        '${"d".repeat(64)}', 'test/1', 'parliamentary-record-0003',
        '2026-08-12 18:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009013',
        '00000000-0000-0000-0000-000000009002', 'transferegov:distribuicao:43389',
        'transferegov_distribuicao_recurso', 3,
        '{"id_distribuicao_recurso_proposta":43389,"id_proposta":30854,"in_tipo_distribuicao":"Emenda","in_tipo_emenda_parlamentar_proposta":"Comissao","nm_parlamentar_proposta":"COMISSAO DA SAUDE","nr_emenda_proposta":"2025.5041.0002","valor_emenda":5000000}',
        '${"e".repeat(64)}', 'test/1', 'parliamentary-record-0004',
        '2026-08-12 18:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009014',
        '00000000-0000-0000-0000-000000009002', 'transferegov:distribuicao:43389',
        'transferegov_distribuicao_recurso', 4,
        '{"id_distribuicao_recurso_proposta":43389,"id_proposta":30854,"in_tipo_distribuicao":"Emenda","in_tipo_emenda_parlamentar_proposta":"Comissao","nm_parlamentar_proposta":"COMISSAO DA SAUDE","nr_emenda_proposta":"2025.5041.0002","valor_emenda":5000000}',
        '${"f".repeat(64)}', 'test/2', 'parliamentary-record-0005',
        '2026-08-12 18:05:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009015',
        '00000000-0000-0000-0000-000000009002', 'transferegov:parceria:30785',
        'transferegov_parceria', 5,
        '{"id_parceria":30785,"id_proposta":30854,"cd_parceria":"202500030009","in_situacao_parceria":"Aprovada"}',
        '${"1".repeat(64)}', 'test/1', 'parliamentary-record-0006',
        '2026-08-12 18:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009016',
        '00000000-0000-0000-0000-000000009002', 'transferegov:empenho:11245',
        'transferegov_empenho', 6,
        '{"id_empenho_parceria":11245,"id_parceria":30785,"numero_empenho":"2025NE493599","data_emissao":"2025-10-13","valor_empenho":5000000}',
        '${"2".repeat(64)}', 'test/1', 'parliamentary-record-0007',
        '2026-08-12 18:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009017',
        '00000000-0000-0000-0000-000000009002', 'transferegov:documento-habil:5941',
        'transferegov_documento_habil', 7,
        '{"id_documento_habil":5941,"id_parceria":30785,"nr_documento_habil":"2025TF860130","dt_emissao":"2025-10-13","vl_documento_habil":5000000}',
        '${"3".repeat(64)}', 'test/1', 'parliamentary-record-0008',
        '2026-08-12 18:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009018',
        '00000000-0000-0000-0000-000000009002', 'transferegov:ordem-pagamento:5932',
        'transferegov_ordem_pagamento', 8,
        '{"id_op":5932,"id_documento_habil":5941,"nr_ordem_pagamento":"2025OP053944","dt_emissao_op":"2025-10-24","vl_ordem_pagamento":5000000,"in_situacao_op":"Paga","nr_ordem_bancaria":"2025OB055607","dt_emissao_ordem_bancaria":"2025-10-24"}',
        '${"4".repeat(64)}', 'test/1', 'parliamentary-record-0009',
        '2026-08-12 18:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009019',
        '00000000-0000-0000-0000-000000009002', 'transferegov:proposta:40000',
        'transferegov_proposta', 9,
        '{"id_proposta":40000,"ano_proposta":2025,"ds_objeto":"Apoio a atencao primaria","vl_total_planejamento_gastos":100000,"nm_ente_recebedor":"Fundo Municipal de Saude de Barreiras","situacao_proposta":"Aprovada"}',
        '${"5".repeat(64)}', 'test/1', 'parliamentary-record-0010',
        '2026-08-12 18:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009020',
        '00000000-0000-0000-0000-000000009002', 'transferegov:distribuicao:50000',
        'transferegov_distribuicao_recurso', 10,
        '{"id_distribuicao_recurso_proposta":50000,"id_proposta":40000,"in_tipo_distribuicao":"Emenda","in_tipo_emenda_parlamentar_proposta":"Individual","nm_parlamentar_proposta":"Ricardo Maia","nr_emenda_proposta":"2025.4460.0099","valor_emenda":100000}',
        '${"6".repeat(64)}', 'test/1', 'parliamentary-record-0011',
        '2026-08-12 18:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009021',
        '00000000-0000-0000-0000-000000009002',
        'transferegov:distribuicao:59999',
        'transferegov_distribuicao_recurso', 11,
        '{"id_distribuicao_recurso_proposta":59999,"id_proposta":40000,"in_tipo_distribuicao":"Emenda","in_tipo_emenda_parlamentar_proposta":"Individual","nm_parlamentar_proposta":"REGISTRO RETIRADO","nr_emenda_proposta":"2025.0000.0000","valor_emenda":12345}',
        '${"7".repeat(64)}', 'test/1', 'parliamentary-record-stale',
        '2026-08-12 17:59:00+00'
      );
  `);

  const currentSnapshotRecords = [
    ["transferegov_distribuicao_recurso", "transferegov:distribuicao:14886", "c".repeat(64)],
    ["transferegov_distribuicao_recurso", "transferegov:distribuicao:43389", "f".repeat(64)],
    ["transferegov_distribuicao_recurso", "transferegov:distribuicao:50000", "6".repeat(64)],
    ["transferegov_documento_habil", "transferegov:documento-habil:5941", "3".repeat(64)],
    ["transferegov_empenho", "transferegov:empenho:11245", "2".repeat(64)],
    ["transferegov_ordem_pagamento", "transferegov:ordem-pagamento:5932", "4".repeat(64)],
    ["transferegov_parceria", "transferegov:parceria:30785", "1".repeat(64)],
    ["transferegov_proposta", "transferegov:proposta:30854", "d".repeat(64)],
    ["transferegov_proposta", "transferegov:proposta:40000", "5".repeat(64)],
    ["transferegov_proposta", "transferegov:proposta:9274", "b".repeat(64)],
  ].map(([record_type, source_record_key, payload_sha256]) => ({
    record_type,
    source_record_key,
    payload_sha256,
  }));
  const expectedCurrentSnapshotFingerprint = createHash("sha256")
    .update(currentSnapshotRecords.map((record) =>
      `${record.record_type}\x1f${record.source_record_key}\x1f${record.payload_sha256}`
    ).sort().join("\n"), "utf8")
    .digest("hex");
  await database.exec(`
    select source.stage_transferegov_snapshot(
      '00000000-0000-0000-0000-000000009001'::uuid,
      2021::smallint,
      '[]'::jsonb,
      '${createHash("sha256").update("").digest("hex")}'
    );
    select source.stage_transferegov_snapshot(
      '00000000-0000-0000-0000-000000009001'::uuid,
      2022::smallint,
      '[]'::jsonb,
      '${createHash("sha256").update("").digest("hex")}'
    );
    select source.stage_transferegov_snapshot(
      '00000000-0000-0000-0000-000000009001'::uuid,
      2025::smallint,
      '${JSON.stringify(currentSnapshotRecords)}'::jsonb,
      '${expectedCurrentSnapshotFingerprint}'
    );
  `);
  const currentSnapshotEvidence = await database.query(`
    select fiscal_year, coverage_status, record_count, snapshot_fingerprint,
           methodology_version
    from api.get_public_transferegov_current_snapshot_evidence()
    where fiscal_year in (2021, 2022, 2025, 2026)
    order by fiscal_year
  `);
  assert.deepEqual(currentSnapshotEvidence.rows, [
    {
      fiscal_year: 2021,
      coverage_status: "empty",
      record_count: 0,
      snapshot_fingerprint:
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      methodology_version: "transferegov-current-snapshot/1.1.0",
    },
    {
      fiscal_year: 2022,
      coverage_status: "empty",
      record_count: 0,
      snapshot_fingerprint:
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      methodology_version: "transferegov-current-snapshot/1.1.0",
    },
    {
      fiscal_year: 2025,
      coverage_status: "complete",
      record_count: 10,
      snapshot_fingerprint: expectedCurrentSnapshotFingerprint,
      methodology_version: "transferegov-current-snapshot/1.1.0",
    },
  ]);

  await database.exec(`
    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version, status
    ) values (
      '00000000-0000-0000-0000-000000009101',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'transferegov-downloads'
         and endpoint.slug = 'propostas-historicas'),
      'historical-proposal-fixture-run', 'test/1', 'succeeded'
    );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, idempotency_key, artifact_kind,
      source_url, retrieved_at, byte_size, sha256, object_key, collector_version
    ) values (
      '00000000-0000-0000-0000-000000009102',
      '00000000-0000-0000-0000-000000009101',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'transferegov-downloads'
         and endpoint.slug = 'propostas-historicas'),
      'historical-proposal-fixture-artifact', 'archive',
      'https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/siconv_proposta.zip',
      '2026-08-13 10:00:00+00', 205017763, '${"9".repeat(64)}',
      'fixtures/siconv_proposta.zip', 'test/1'
    );
    insert into raw.raw_records (
      id, raw_artifact_id, source_record_key, record_type, record_index,
      payload, payload_sha256, parser_version, idempotency_key, collected_at
    ) values
      (
        '00000000-0000-0000-0000-000000009110',
        '00000000-0000-0000-0000-000000009102',
        'transferegov:historical-proposal:9001',
        'transferegov_historical_proposal', 0,
        '{"id_proposta":"9001","numero_proposta":"000001/2021","ano_proposta":2021,"data_proposta":"15/06/2021","cod_municipio_ibge":"2903201","municipio_proponente":"BARREIRAS","proponente":"MUNICIPIO DE BARREIRAS","proponente_cnpj":"13654405000195","situacao_proposta":"PROPOSTA EM ANALISE","situacao_projeto_basico":"EM ANALISE","modalidade":"CONVENIO","objeto":"VERSAO ANTIGA","item_investimento":"INFRAESTRUTURA","orgao":"MINISTERIO DO DESENVOLVIMENTO","orgao_superior":"MINISTERIO DO DESENVOLVIMENTO","valor_global":"1250000.50","valor_repasse":"1200000.50","valor_contrapartida":"50000.00","agencia":"NAO PUBLICAR"}',
        '${"8".repeat(64)}', 'test/1', 'historical-record-0001',
        '2026-08-13 09:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009111',
        '00000000-0000-0000-0000-000000009102',
        'transferegov:historical-proposal:9001',
        'transferegov_historical_proposal', 1,
        '{"id_proposta":"9001","numero_proposta":"000001/2021","ano_proposta":2021,"data_proposta":"15/06/2021","cod_municipio_ibge":"2903201","municipio_proponente":"BARREIRAS","proponente":"MUNICIPIO DE BARREIRAS","proponente_cnpj":"13654405000195","situacao_proposta":"PROPOSTA APROVADA","situacao_projeto_basico":"APROVADO","modalidade":"CONVENIO","objeto":"CONSTRUIR EQUIPAMENTO PUBLICO","item_investimento":"INFRAESTRUTURA","orgao":"MINISTERIO DO DESENVOLVIMENTO","orgao_superior":"MINISTERIO DO DESENVOLVIMENTO","valor_global":"1250000.50","valor_repasse":"1200000.50","valor_contrapartida":"50000.00","conta":"NAO PUBLICAR"}',
        '${"7".repeat(64)}', 'test/2', 'historical-record-0002',
        '2026-08-13 10:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009112',
        '00000000-0000-0000-0000-000000009102',
        'transferegov:historical-proposal:9002',
        'transferegov_historical_proposal', 2,
        '{"id_proposta":"9002","numero_proposta":"000002/2021","ano_proposta":2021,"data_proposta":"16/06/2021","cod_municipio_ibge":"2903201","municipio_proponente":"BARREIRAS","proponente":"CONSORCIO MULTIFINALITARIO DO OESTE DA BAHIA","proponente_cnpj":"00000000000000","situacao_proposta":"PROPOSTA APROVADA","situacao_projeto_basico":"APROVADO","modalidade":"CONVENIO","objeto":"PAVIMENTACAO NO MUNICIPIO DE BARRA-BA","item_investimento":"INFRAESTRUTURA","orgao":"MINISTERIO DO DESENVOLVIMENTO","orgao_superior":"MINISTERIO DO DESENVOLVIMENTO","valor_global":"700000.00","valor_repasse":"700000.00","valor_contrapartida":"0.00"}',
        '${"6".repeat(64)}', 'test/1', 'historical-record-0003',
        '2026-08-13 10:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009113',
        '00000000-0000-0000-0000-000000009102',
        'transferegov:historical-proposal:9274',
        'transferegov_historical_proposal', 3,
        '{"id_proposta":"9274","numero_proposta":"000003/2025","ano_proposta":2025,"data_proposta":"20/05/2025","cod_municipio_ibge":"2903201","municipio_proponente":"BARREIRAS","proponente":"MUNICIPIO DE BARREIRAS","proponente_cnpj":"13654405000195","situacao_proposta":"PROPOSTA APROVADA","situacao_projeto_basico":"APROVADO","modalidade":"TRANSFERENCIA ESPECIAL","objeto":"APOIO A BARREIRAS","item_investimento":"CUSTEIO","orgao":"MINISTERIO DA SAUDE","orgao_superior":"MINISTERIO DA SAUDE","valor_global":"250000.00","valor_repasse":"250000.00","valor_contrapartida":"0.00"}',
        '${"5".repeat(64)}', 'test/1', 'historical-record-0004',
        '2026-08-13 10:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009114',
        '00000000-0000-0000-0000-000000009102',
        'transferegov:historical-proposal:40000',
        'transferegov_historical_proposal', 4,
        '{"id_proposta":"40000","numero_proposta":"000004/2025","ano_proposta":2025,"data_proposta":"21/05/2025","cod_municipio_ibge":"2903201","municipio_proponente":"BARREIRAS","proponente":"FUNDO MUNICIPAL DE SAUDE DE BARREIRAS","proponente_cnpj":"13654405000195","situacao_proposta":"PROPOSTA APROVADA","situacao_projeto_basico":"APROVADO","modalidade":"TRANSFERENCIA ESPECIAL","objeto":"APOIO A ATENCAO PRIMARIA EM BARREIRAS","item_investimento":"CUSTEIO","orgao":"MINISTERIO DA SAUDE","orgao_superior":"MINISTERIO DA SAUDE","valor_global":"99999.00","valor_repasse":"99999.00","valor_contrapartida":"0.00"}',
        '${"4".repeat(64)}', 'test/1', 'historical-record-0005',
        '2026-08-13 10:00:00+00'
      );
  `);

  await database.exec(`
    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version, status
    ) values (
      '00000000-0000-0000-0000-000000009201',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'transferegov-downloads'
         and endpoint.slug = 'emendas-historicas'),
      'historical-amendment-fixture-run', 'test/1', 'succeeded'
    );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, idempotency_key, artifact_kind,
      source_url, retrieved_at, byte_size, sha256, object_key, collector_version
    ) values (
      '00000000-0000-0000-0000-000000009202',
      '00000000-0000-0000-0000-000000009201',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'transferegov-downloads'
         and endpoint.slug = 'emendas-historicas'),
      'historical-amendment-fixture-artifact', 'archive',
      'https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/siconv_emenda.zip',
      '2026-08-13 11:00:00+00', 8306000, '${"5".repeat(64)}',
      'fixtures/siconv_emenda.zip', 'test/1'
    );
    insert into raw.raw_records (
      id, raw_artifact_id, source_record_key, record_type, record_index,
      payload, payload_sha256, parser_version, idempotency_key, collected_at
    ) values
      (
        '00000000-0000-0000-0000-000000009210',
        '00000000-0000-0000-0000-000000009202',
        'transferegov:historical-amendment:9001:11110001:person',
        'transferegov_historical_amendment', 0,
        '{"id_proposta":"9001","numero_emenda":"11110001","autor_nome":"AFONSO FLORENCE","tipo_parlamentar":"INDIVIDUAL","codigo_programa_emenda":"5300020210017","impositiva":true,"valor_repasse_emenda":"400000","valor_repasse_proposta_emenda":"900000","beneficiario_tipo":"cnpj","beneficiario_ultimos_4":"0195"}',
        '${"4".repeat(64)}', 'test/1', 'historical-amendment-record-0001',
        '2026-08-13 11:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009211',
        '00000000-0000-0000-0000-000000009202',
        'transferegov:historical-amendment:9001:11110002:person',
        'transferegov_historical_amendment', 1,
        '{"id_proposta":"9001","numero_emenda":"11110002","autor_nome":"AFONSO FLORENCE","tipo_parlamentar":"INDIVIDUAL","codigo_programa_emenda":"5300020210017","impositiva":true,"valor_repasse_emenda":"500000","valor_repasse_proposta_emenda":"900000","beneficiario_tipo":"cnpj","beneficiario_ultimos_4":"0195"}',
        '${"3".repeat(64)}', 'test/1', 'historical-amendment-record-0002',
        '2026-08-13 11:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009212',
        '00000000-0000-0000-0000-000000009202',
        'transferegov:historical-amendment:9001:50070003:commission',
        'transferegov_historical_amendment', 2,
        '{"id_proposta":"9001","numero_emenda":"50070003","autor_nome":"COM. TURISMO","tipo_parlamentar":"COMISSAO","codigo_programa_emenda":"5400020210017","impositiva":false,"valor_repasse_emenda":"300000","valor_repasse_proposta_emenda":"300000","beneficiario_tipo":"cnpj","beneficiario_ultimos_4":"0195"}',
        '${"2".repeat(64)}', 'test/1', 'historical-amendment-record-0003',
        '2026-08-13 11:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009213',
        '00000000-0000-0000-0000-000000009202',
        'transferegov:historical-amendment:9002:50070004:commission',
        'transferegov_historical_amendment', 3,
        '{"id_proposta":"9002","numero_emenda":"50070004","autor_nome":"COM. TURISMO","tipo_parlamentar":"COMISSAO","codigo_programa_emenda":"5400020210018","impositiva":false,"valor_repasse_emenda":"700000","valor_repasse_proposta_emenda":"700000","beneficiario_tipo":"cnpj","beneficiario_ultimos_4":"0000"}',
        '${"1".repeat(64)}', 'test/1', 'historical-amendment-record-0004',
        '2026-08-13 11:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009214',
        '00000000-0000-0000-0000-000000009202',
        'transferegov:historical-amendment:9274:2025.4460.0002:person',
        'transferegov_historical_amendment', 4,
        '{"id_proposta":"9274","numero_emenda":"2025.4460.0002","autor_nome":"RICARDO MAIA","tipo_parlamentar":"INDIVIDUAL","codigo_programa_emenda":"3600020250017","impositiva":true,"valor_repasse_emenda":"250000","valor_repasse_proposta_emenda":"250000","beneficiario_tipo":"cnpj","beneficiario_ultimos_4":"0195"}',
        '${"0".repeat(64)}', 'test/1', 'historical-amendment-record-0005',
        '2026-08-13 11:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009215',
        '00000000-0000-0000-0000-000000009202',
        'transferegov:historical-amendment:40000:2025.4460.0099:person',
        'transferegov_historical_amendment', 5,
        '{"id_proposta":"40000","numero_emenda":"2025.4460.0099","autor_nome":"RICARDO MAIA","tipo_parlamentar":"INDIVIDUAL","codigo_programa_emenda":"3600020250018","impositiva":true,"valor_repasse_emenda":"99999","valor_repasse_proposta_emenda":"99999","beneficiario_tipo":"cnpj","beneficiario_ultimos_4":"0195"}',
        '${"f".repeat(64)}', 'test/1', 'historical-amendment-record-0006',
        '2026-08-13 11:00:00+00'
      );
  `);

  await database.exec(`
    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version, status
    ) values (
      '00000000-0000-0000-0000-000000009301',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'bahia-seplan-budget'
         and endpoint.slug = 'state-loa-amendment-annexes'),
      'state-loa-public-fixture-run', 'test/1', 'succeeded'
    );
    insert into source.collection_partitions (
      source_endpoint_id, partition_key, period_start, period_end, status,
      observed_records, collection_run_id, checkpoint, block_reason,
      last_attempted_at, completed_at
    ) values
      (
        (select endpoint.id
         from source.source_endpoints endpoint
         join source.data_sources source on source.id = endpoint.data_source_id
         where source.slug = 'bahia-seplan-budget'
           and endpoint.slug = 'state-loa-amendment-annexes'),
        'loa-annex:2021', '2021-01-01', '2021-12-31', 'blocked', 0,
        '00000000-0000-0000-0000-000000009301',
        '{"fiscal_year":2021}', 'link oficial aponta para o ano errado',
        '2026-08-13 17:00:00+00', '2026-08-13 17:00:01+00'
      ),
      (
        (select endpoint.id
         from source.source_endpoints endpoint
         join source.data_sources source on source.id = endpoint.data_source_id
         where source.slug = 'bahia-seplan-budget'
           and endpoint.slug = 'state-loa-amendment-annexes'),
        'loa-annex:2022', '2022-01-01', '2022-12-31', 'complete', 1,
        '00000000-0000-0000-0000-000000009301',
        '{"fiscal_year":2022}', null,
        '2026-08-13 17:05:00+00', '2026-08-13 17:05:01+00'
      ),
      (
        (select endpoint.id
         from source.source_endpoints endpoint
         join source.data_sources source on source.id = endpoint.data_source_id
         where source.slug = 'bahia-seplan-budget'
           and endpoint.slug = 'state-loa-amendment-annexes'),
        'loa-annex:2024', '2024-01-01', '2024-12-31', 'complete', 1,
        '00000000-0000-0000-0000-000000009301',
        '{"fiscal_year":2024}', null,
        '2026-08-13 17:10:00+00', '2026-08-13 17:10:01+00'
      );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, idempotency_key, artifact_kind,
      source_url, retrieved_at, byte_size, sha256, object_key, collector_version
    ) values (
      '00000000-0000-0000-0000-000000009302',
      '00000000-0000-0000-0000-000000009301',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'bahia-seplan-budget'
         and endpoint.slug = 'state-loa-amendment-annexes'),
      'state-loa-public-fixture-artifact', 'document',
      'https://www.ba.gov.br/seplan/loa-fixture.pdf',
      '2026-08-13 18:00:00+00', 1000, '${"7".repeat(64)}',
      'fixtures/bahia-loa.pdf', 'test/1'
    );
    insert into raw.extraction_jobs (
      id, raw_artifact_id, job_type, idempotency_key, status
    ) values
      (
        '00000000-0000-0000-0000-000000009310',
        '00000000-0000-0000-0000-000000009302',
        'bahia_state_loa_authorized_amendments_v1',
        'state-loa-public-fixture-job-ok', 'succeeded'
      ),
      (
        '00000000-0000-0000-0000-000000009311',
        '00000000-0000-0000-0000-000000009302',
        'bahia_state_loa_authorized_amendments_v1',
        'state-loa-public-fixture-job-failed', 'failed'
      );
    insert into raw.extraction_results (
      id, extraction_job_id, candidate_type, extractor_version,
      validator_version, result_payload, validation_status, validation_errors,
      created_at
    ) values
      (
        '00000000-0000-0000-0000-000000009320',
        '00000000-0000-0000-0000-000000009310',
        'bahia_state_loa_authorized_amendment',
        'bahia-state-loa-barreiras/1.1.0',
        'bahia-state-loa-deterministic/1.0.0',
        '{"fiscal_year":2022,"municipality":"Barreiras","amendment_number":"101","author_external_code":null,"author_name":"Antônio Henrique Jr.","authorized_amount":"100000","official_description":"Saúde em Barreiras","annex_code":"III","budget_unit_code":"1001","agency_code":"10","action_code":"2001","page_number":10,"evidence_text":"BARREIRAS ANTONIO HENRIQUE JR 100000","financial_stage":"authorized","source_url":"https://www.ba.gov.br/seplan/loa-fixture.pdf","source_artifact_sha256":"${"7".repeat(64)}","evidence_sha256":"${"a".repeat(64)}"}',
        'valid', '[]', '2026-08-13 18:01:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009321',
        '00000000-0000-0000-0000-000000009310',
        'bahia_state_loa_authorized_amendment',
        'bahia-state-loa-barreiras/1.1.0',
        'bahia-state-loa-deterministic/1.0.0',
        '{"fiscal_year":2026,"municipality":"Barreiras","amendment_number":"102","author_external_code":"500069","author_name":"Antonio Henrique Júnior","authorized_amount":"200000","official_description":"Educação em Barreiras","annex_code":"I","budget_unit_code":"1002","agency_code":"11","action_code":"2002","page_number":11,"evidence_text":"BARREIRAS ANTONIO HENRIQUE JUNIOR 200000","financial_stage":"authorized","source_url":"https://www.ba.gov.br/seplan/loa-fixture.pdf","source_artifact_sha256":"${"7".repeat(64)}","evidence_sha256":"${"b".repeat(64)}"}',
        'valid', '[]', '2026-08-13 18:02:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009322',
        '00000000-0000-0000-0000-000000009310',
        'bahia_state_loa_authorized_amendment',
        'bahia-state-loa-barreiras/1.2.0',
        'bahia-state-loa-deterministic/1.0.0',
        '{"fiscal_year":2026,"municipality":"Barreiras","amendment_number":"103","author_external_code":"500144","author_name":"Marcone Amaral","authorized_amount":"500000","official_description":"Infraestrutura em Barreiras","annex_code":"I","budget_unit_code":"1003","agency_code":"12","action_code":"2003","page_number":12,"evidence_text":"BARREIRAS MARCONE AMARAL 500000","financial_stage":"authorized","source_url":"https://www.ba.gov.br/seplan/loa-fixture.pdf","source_artifact_sha256":"${"7".repeat(64)}","evidence_sha256":"${"c".repeat(64)}"}',
        'valid', '[]', '2026-08-13 18:03:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009323',
        '00000000-0000-0000-0000-000000009310',
        'bahia_state_loa_authorized_amendment',
        'bahia-state-loa-barreiras/1.1.0',
        'bahia-state-loa-deterministic/1.0.0',
        '{"fiscal_year":2026,"municipality":"Barreiras","amendment_number":"102","author_external_code":"500069","author_name":"Antonio Henrique Júnior","authorized_amount":"200000","official_description":"Educação em Barreiras","annex_code":"I","budget_unit_code":"1002","agency_code":"11","action_code":"2002","page_number":11,"evidence_text":"BARREIRAS ANTONIO HENRIQUE JUNIOR 200000","financial_stage":"authorized","source_url":"https://www.ba.gov.br/seplan/loa-fixture.pdf","source_artifact_sha256":"${"7".repeat(64)}","evidence_sha256":"${"b".repeat(64)}"}',
        'valid', '[]', '2026-08-13 18:04:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009324',
        '00000000-0000-0000-0000-000000009311',
        'bahia_state_loa_authorized_amendment',
        'bahia-state-loa-barreiras/1.1.0',
        'bahia-state-loa-deterministic/1.0.0',
        '{"fiscal_year":2026,"municipality":"Barreiras","amendment_number":"999","author_name":"Registro com job falho","authorized_amount":"999999","official_description":"Não publicar","page_number":99,"evidence_text":"NAO PUBLICAR","financial_stage":"authorized","source_url":"https://www.ba.gov.br/seplan/loa-fixture.pdf","source_artifact_sha256":"${"7".repeat(64)}","evidence_sha256":"${"d".repeat(64)}"}',
        'valid', '[]', '2026-08-13 18:05:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009325',
        '00000000-0000-0000-0000-000000009310',
        'bahia_state_loa_authorized_amendment',
        'bahia-state-loa-barreiras/1.1.0',
        'bahia-state-loa-deterministic/1.0.0',
        '{"fiscal_year":2023,"municipality":"Barreiras","amendment_number":"104","author_name":"Capitão Alden","authorized_amount":"700000","official_description":"Segurança em Barreiras","annex_code":"II","budget_unit_code":"1004","agency_code":"13","action_code":"2004","page_number":13,"evidence_text":"BARREIRAS CAPITAO ALDEN 700000","financial_stage":"authorized","source_url":"https://www.ba.gov.br/seplan/loa-fixture.pdf","source_artifact_sha256":"${"7".repeat(64)}","evidence_sha256":"${"e".repeat(64)}"}',
        'valid', '[]', '2026-08-13 18:06:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009326',
        '00000000-0000-0000-0000-000000009310',
        'bahia_state_loa_authorized_amendment',
        'bahia-state-loa-barreiras/1.1.0',
        'bahia-state-loa-deterministic/1.0.0',
        '{"fiscal_year":2026,"municipality":"Barreiras","amendment_number":"105","author_external_code":"500123","author_name":"Diego Castro","authorized_amount":"600000","official_description":"Saúde em Barreiras","annex_code":"II","budget_unit_code":"1005","agency_code":"14","action_code":"2005","page_number":14,"evidence_text":"BARREIRAS DIEGO CASTRO 600000","financial_stage":"authorized","source_url":"https://www.ba.gov.br/seplan/loa-fixture.pdf","source_artifact_sha256":"${"7".repeat(64)}","evidence_sha256":"${"f".repeat(64)}"}',
        'valid', '[]', '2026-08-13 18:07:00+00'
      );
  `);

  await database.exec(`
    insert into raw.extraction_jobs (
      id, raw_artifact_id, job_type, idempotency_key, status
    ) values (
      '00000000-0000-0000-0000-000000009330',
      '00000000-0000-0000-0000-000000009302',
      'bahia_state_loa_authorized_amendments_and_scope_v2',
      'state-loa-scope-fixture-job-ok', 'succeeded'
    );
    insert into raw.extraction_results (
      id, extraction_job_id, candidate_type, extractor_version,
      validator_version, result_payload, validation_status, validation_errors,
      created_at
    ) values
      (
        '00000000-0000-0000-0000-000000009331',
        '00000000-0000-0000-0000-000000009330',
        'bahia_state_loa_2026_scope_row',
        'bahia-state-loa-scope/1.0.0',
        'bahia-state-loa-deterministic/1.0.0',
        '{"fiscal_year":2026,"amendment_number":"102","author_external_code":"500069","author_name":"Antonio Henrique Junior","agency_code":"11","budget_unit_code":"1002","action_code":"2002","page_number":11,"evidence_text":"ESCOPO 102","evidence_sha256":"${"1".repeat(64)}","source_url":"https://www.ba.gov.br/seplan/loa-fixture.pdf","source_artifact_sha256":"${"7".repeat(64)}","visibility":"private_reconciliation_scope"}',
        'valid', '[]', '2026-08-14 09:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009332',
        '00000000-0000-0000-0000-000000009330',
        'bahia_state_loa_2026_scope_row',
        'bahia-state-loa-scope/1.0.0',
        'bahia-state-loa-deterministic/1.0.0',
        '{"fiscal_year":2026,"amendment_number":"103","author_external_code":"500144","author_name":"Marcone Amaral","agency_code":"12","budget_unit_code":"1003","action_code":"2003","page_number":12,"evidence_text":"ESCOPO 103 A","evidence_sha256":"${"2".repeat(64)}","source_url":"https://www.ba.gov.br/seplan/loa-fixture.pdf","source_artifact_sha256":"${"7".repeat(64)}","visibility":"private_reconciliation_scope"}',
        'valid', '[]', '2026-08-14 09:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009333',
        '00000000-0000-0000-0000-000000009330',
        'bahia_state_loa_2026_scope_row',
        'bahia-state-loa-scope/1.0.0',
        'bahia-state-loa-deterministic/1.0.0',
        '{"fiscal_year":2026,"amendment_number":"999","author_external_code":"500144","author_name":"Marcone Amaral","agency_code":"12","budget_unit_code":"1003","action_code":"2003","page_number":99,"evidence_text":"ESCOPO 103 B","evidence_sha256":"${"3".repeat(64)}","source_url":"https://www.ba.gov.br/seplan/loa-fixture.pdf","source_artifact_sha256":"${"7".repeat(64)}","visibility":"private_reconciliation_scope"}',
        'valid', '[]', '2026-08-14 09:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009334',
        '00000000-0000-0000-0000-000000009330',
        'bahia_state_loa_2026_scope_row',
        'bahia-state-loa-scope/1.0.0',
        'bahia-state-loa-deterministic/1.0.0',
        '{"fiscal_year":2026,"amendment_number":"105","author_external_code":"500123","author_name":"Diego Castro","agency_code":"14","budget_unit_code":"1005","action_code":"2005","page_number":14,"evidence_text":"ESCOPO 105","evidence_sha256":"${"4".repeat(64)}","source_url":"https://www.ba.gov.br/seplan/loa-fixture.pdf","source_artifact_sha256":"${"7".repeat(64)}","visibility":"private_reconciliation_scope"}',
        'valid', '[]', '2026-08-14 09:00:00+00'
      );

    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version, status
    ) values (
      '00000000-0000-0000-0000-000000009340',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'bahia-open-data'
         and endpoint.slug = 'state-parliamentary-amendments'),
      'state-execution-fixture-run', 'test/1', 'succeeded'
    );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, idempotency_key, artifact_kind,
      source_url, retrieved_at, byte_size, sha256, object_key, collector_version
    ) values (
      '00000000-0000-0000-0000-000000009341',
      '00000000-0000-0000-0000-000000009340',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'bahia-open-data'
         and endpoint.slug = 'state-parliamentary-amendments'),
      'state-execution-fixture-artifact', 'archive',
      'https://dados.ba.gov.br/emendas-fixture.zip',
      '2026-08-14 09:10:00+00', 1000, '${"8".repeat(64)}',
      'fixtures/bahia-execution.zip', 'test/1'
    );
    insert into raw.extraction_jobs (
      id, raw_artifact_id, job_type, idempotency_key, status
    ) values (
      '00000000-0000-0000-0000-000000009342',
      '00000000-0000-0000-0000-000000009341',
      'bahia_state_execution_aggregates_v1',
      'state-execution-fixture-job-ok', 'succeeded'
    );
    insert into raw.extraction_results (
      id, extraction_job_id, candidate_type, extractor_version,
      validator_version, result_payload, validation_status, validation_errors,
      created_at
    ) values
      (
        '00000000-0000-0000-0000-000000009343',
        '00000000-0000-0000-0000-000000009342',
        'bahia_state_execution_aggregate',
        'bahia-state-execution-aggregate/1.0.0',
        'bahia-state-execution-deterministic/1.0.0',
        '{"schema_name":"bahia-state-execution-aggregate","schema_version":"1.0.0","parser_version":"bahia-state-execution-aggregate/1.0.0","fiscal_year":2026,"author_external_code":"500069","author_name":"Antonio Henrique Junior","agency_code":"11","budget_unit_code":"1002","action_code":"2002","execution_code":"2026.1.1.1.1.2002.500069.1","initial_budget_amount":"200000.00","current_budget_amount":"190000.00","committed_amount":"150000.00","liquidated_amount":"100000.00","paid_amount":"90000.00","evidence_text":"EXECUCAO 102","evidence_sha256":"${"5".repeat(64)}","source_url":"https://dados.ba.gov.br/emendas-fixture.zip","source_artifact_sha256":"${"8".repeat(64)}","source_collected_at":"2026-08-14T09:10:00+00:00","territorial_scope":"not_available_in_execution_archive"}',
        'valid', '[]', '2026-08-14 09:11:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009344',
        '00000000-0000-0000-0000-000000009342',
        'bahia_state_execution_aggregate',
        'bahia-state-execution-aggregate/1.0.0',
        'bahia-state-execution-deterministic/1.0.0',
        '{"schema_name":"bahia-state-execution-aggregate","schema_version":"1.0.0","parser_version":"bahia-state-execution-aggregate/1.0.0","fiscal_year":2026,"author_external_code":"500123","author_name":"Diego Castro","agency_code":"14","budget_unit_code":"1005","action_code":"2005","execution_code":"2026.1.1.1.1.2005.500123.1","initial_budget_amount":"600000.00","current_budget_amount":"600000.00","committed_amount":"300000.00","liquidated_amount":"200000.00","paid_amount":"100000.00","evidence_text":"EXECUCAO 105 A","evidence_sha256":"${"6".repeat(64)}","source_url":"https://dados.ba.gov.br/emendas-fixture.zip","source_artifact_sha256":"${"8".repeat(64)}","source_collected_at":"2026-08-14T09:10:00+00:00","territorial_scope":"not_available_in_execution_archive"}',
        'valid', '[]', '2026-08-14 09:11:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009345',
        '00000000-0000-0000-0000-000000009342',
        'bahia_state_execution_aggregate',
        'bahia-state-execution-aggregate/1.0.0',
        'bahia-state-execution-deterministic/1.0.0',
        '{"schema_name":"bahia-state-execution-aggregate","schema_version":"1.0.0","parser_version":"bahia-state-execution-aggregate/1.0.0","fiscal_year":2026,"author_external_code":"500123","author_name":"Diego Castro","agency_code":"14","budget_unit_code":"1005","action_code":"2005","execution_code":"2026.1.1.1.1.2005.500123.2","initial_budget_amount":"100000.00","current_budget_amount":"100000.00","committed_amount":"50000.00","liquidated_amount":"40000.00","paid_amount":"30000.00","evidence_text":"EXECUCAO 105 B","evidence_sha256":"${"9".repeat(64)}","source_url":"https://dados.ba.gov.br/emendas-fixture.zip","source_artifact_sha256":"${"8".repeat(64)}","source_collected_at":"2026-08-14T09:10:00+00:00","territorial_scope":"not_available_in_execution_archive"}',
        'valid', '[]', '2026-08-14 09:11:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009346',
        '00000000-0000-0000-0000-000000009342',
        'bahia_state_execution_aggregate',
        'bahia-state-execution-aggregate/1.0.0',
        'bahia-state-execution-deterministic/1.0.0',
        '{"schema_name":"bahia-state-execution-aggregate","schema_version":"1.0.0","parser_version":"bahia-state-execution-aggregate/1.0.0","fiscal_year":2025,"author_external_code":"500777","author_name":"Deputada Exemplo","agency_code":"20","budget_unit_code":"2001","action_code":"3001","execution_code":"2025.1.1.1.1.3001.500777.1","initial_budget_amount":"100000.00","current_budget_amount":"100000.00","committed_amount":"80000.00","liquidated_amount":"70000.00","paid_amount":"60000.00","evidence_text":"EXECUCAO 2025","evidence_sha256":"${"7".repeat(64)}","source_url":"https://dados.ba.gov.br/emendas-fixture.zip","source_artifact_sha256":"${"8".repeat(64)}","source_collected_at":"2026-08-14T09:10:00+00:00","territorial_scope":"not_available_in_execution_archive"}',
        'valid', '[]', '2026-08-14 09:11:00+00'
      );
  `);

  // Production persistence refreshes the public snapshots only after the raw
  // extraction transaction is complete. Mirror that boundary here: migrations
  // run before these fixtures, so their initial seed is intentionally empty.
  const initialStateExecutionSnapshot = await database.query(`
    select territory.refresh_bahia_state_loa_execution_reconciliation_snapshot()
      as refreshed_rows
  `);
  assert.deepEqual(initialStateExecutionSnapshot.rows, [{ refreshed_rows: 5 }]);

  const snapshotBeforeCorruption = await database.query(`
    select * from territory.bahia_state_loa_amendment_snapshot
    order by origin_extraction_result_id
  `);
  assert.equal(snapshotBeforeCorruption.rows.length, 5);
  // A same-count corruption must fail just like a missing row. The failed
  // refresh must roll back its delete/insert and leave the last good copy intact.
  for (const triggerBody of [
    "new.authorized_amount := new.authorized_amount + 1; return new;",
    "return null;",
  ]) {
    await database.exec(`
      create function territory.test_corrupt_state_loa_snapshot()
      returns trigger language plpgsql as $$ begin ${triggerBody} end; $$;
      create trigger test_corrupt_state_loa_snapshot
        before insert on territory.bahia_state_loa_amendment_snapshot
        for each row execute function territory.test_corrupt_state_loa_snapshot();
    `);
    try {
      await assert.rejects(
        database.query(`
          select territory.refresh_bahia_state_loa_amendment_snapshot()
        `),
        /Snapshot da LOA estadual divergiu da fonte canonica/,
      );
      const snapshotAfterFailure = await database.query(`
        select * from territory.bahia_state_loa_amendment_snapshot
        order by origin_extraction_result_id
      `);
      assert.deepEqual(snapshotAfterFailure.rows, snapshotBeforeCorruption.rows);
    } finally {
      await database.exec(`
        drop trigger test_corrupt_state_loa_snapshot
          on territory.bahia_state_loa_amendment_snapshot;
        drop function territory.test_corrupt_state_loa_snapshot();
      `);
    }
  }

  const stateExecutionCoverage = await database.query(`
    select fiscal_year, source_aggregate_count, source_author_count,
      territorial_key_status, source_snapshot_status, methodology_version
    from api.get_public_bahia_state_execution_annual_coverage()
  `);
  assert.deepEqual(stateExecutionCoverage.rows, [
    {
      fiscal_year: 2026,
      source_aggregate_count: 3,
      source_author_count: 2,
      territorial_key_status: "territorial_key_unavailable_in_source",
      source_snapshot_status: "source_snapshot_observed",
      methodology_version: "bahia-state-execution-source-coverage/1.0.0",
    },
    {
      fiscal_year: 2025,
      source_aggregate_count: 1,
      source_author_count: 1,
      territorial_key_status: "territorial_key_unavailable_in_source",
      source_snapshot_status: "source_snapshot_observed",
      methodology_version: "bahia-state-execution-source-coverage/1.0.0",
    },
  ]);

  const stateExecutionReconciliation = await database.query(`
    select amendment_number, reconciliation_status,
      loa_scope_occurrences, execution_occurrences,
      committed_amount, liquidated_amount, paid_amount,
      execution_evidence_sha256
    from territory.bahia_state_loa_execution_reconciliation
    order by amendment_number
  `);
  assert.deepEqual(stateExecutionReconciliation.rows, [
    {
      amendment_number: "101",
      reconciliation_status: "blocked_scope_year_not_indexed",
      loa_scope_occurrences: 0,
      execution_occurrences: 0,
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      execution_evidence_sha256: null,
    },
    {
      amendment_number: "102",
      reconciliation_status: "matched_bidirectional_unique",
      loa_scope_occurrences: 1,
      execution_occurrences: 1,
      committed_amount: "150000.00",
      liquidated_amount: "100000.00",
      paid_amount: "90000.00",
      execution_evidence_sha256: "5".repeat(64),
    },
    {
      amendment_number: "103",
      reconciliation_status: "blocked_non_unique_loa_key",
      loa_scope_occurrences: 2,
      execution_occurrences: 0,
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      execution_evidence_sha256: null,
    },
    {
      amendment_number: "104",
      reconciliation_status: "blocked_scope_year_not_indexed",
      loa_scope_occurrences: 0,
      execution_occurrences: 0,
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      execution_evidence_sha256: null,
    },
    {
      amendment_number: "105",
      reconciliation_status: "blocked_non_unique_execution_key",
      loa_scope_occurrences: 1,
      execution_occurrences: 2,
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      execution_evidence_sha256: null,
    },
  ]);

  const historicalStateSourceCoverage = await database.query(`
    select fiscal_year, loa_status, amendment_count, authorized_amount,
      execution_status, matched_count, ambiguous_count, not_found_count,
      unavailable_scope_count, committed_amount, liquidated_amount, paid_amount,
      methodology_version
    from api.get_public_state_amendment_source_coverage()
    where fiscal_year = 2022
  `);
  assert.deepEqual(historicalStateSourceCoverage.rows, [{
    fiscal_year: 2022,
    loa_status: "observed",
    amendment_count: 1,
    authorized_amount: "100000.00",
    execution_status: "blocked_missing_official_key",
    matched_count: null,
    ambiguous_count: null,
    not_found_count: null,
    unavailable_scope_count: null,
    committed_amount: null,
    liquidated_amount: null,
    paid_amount: null,
    methodology_version: "state-amendment-source-coverage/1.1.0",
  }]);

  const refreshedStateExecutionSnapshot = await database.query(`
    select territory.refresh_bahia_state_loa_execution_reconciliation_snapshot()
      as refreshed_rows
  `);
  assert.deepEqual(refreshedStateExecutionSnapshot.rows, [{ refreshed_rows: 5 }]);
  const stateExecutionSnapshot = await database.query(`
    select amendment_number, reconciliation_status,
      committed_amount, liquidated_amount, paid_amount
    from territory.bahia_state_loa_execution_reconciliation_snapshot
    order by amendment_number
  `);
  assert.equal(stateExecutionSnapshot.rows.length, 5);
  assert.deepEqual(
    stateExecutionSnapshot.rows.find((row) => row.amendment_number === "102"),
    {
      amendment_number: "102",
      reconciliation_status: "matched_bidirectional_unique",
      committed_amount: "150000.00",
      liquidated_amount: "100000.00",
      paid_amount: "90000.00",
    },
  );

  const publicStateExecution = await database.query(`
    select amendment_number, execution_status,
      loa_scope_occurrences, execution_occurrences,
      authorized_amount, committed_amount, liquidated_amount, paid_amount,
      execution_source_url, execution_evidence_sha256, methodology_version
    from api.get_public_bahia_state_loa_execution(2026::smallint, null, 200)
    order by amendment_number
  `);
  assert.deepEqual(publicStateExecution.rows, [
    {
      amendment_number: "102",
      execution_status: "execution_confirmed",
      loa_scope_occurrences: 1,
      execution_occurrences: 1,
      authorized_amount: "200000.00",
      committed_amount: "150000.00",
      liquidated_amount: "100000.00",
      paid_amount: "90000.00",
      execution_source_url: "https://dados.ba.gov.br/emendas-fixture.zip",
      execution_evidence_sha256: "5".repeat(64),
      methodology_version: "bahia-state-loa-public-execution/1.1.0",
    },
    {
      amendment_number: "103",
      execution_status: "ambiguous_official_key",
      loa_scope_occurrences: 2,
      execution_occurrences: 0,
      authorized_amount: "500000.00",
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      execution_source_url: null,
      execution_evidence_sha256: null,
      methodology_version: "bahia-state-loa-public-execution/1.1.0",
    },
    {
      amendment_number: "105",
      execution_status: "ambiguous_official_key",
      loa_scope_occurrences: 1,
      execution_occurrences: 2,
      authorized_amount: "600000.00",
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      execution_source_url: null,
      execution_evidence_sha256: null,
      methodology_version: "bahia-state-loa-public-execution/1.1.0",
    },
  ]);

  const stateLoaStudyPage = await database.query(`
    select
      total_count,
      jsonb_array_length(amendment_items) as amendment_count,
      jsonb_array_length(execution_items) as execution_count,
      amendment_items -> 0 ->> 'amendment_number' as first_amendment,
      amendment_items -> 1 ->> 'amendment_number' as second_amendment,
      methodology_version
    from api.get_public_bahia_state_loa_study(2026::smallint, 2, 1)
  `);
  assert.deepEqual(stateLoaStudyPage.rows, [{
    total_count: 3,
    amendment_count: 2,
    execution_count: 2,
    first_amendment: "103",
    second_amendment: "102",
    methodology_version: "bahia-state-loa-study/1.0.0",
  }]);

  const filteredStateLoaStudy = await database.query(`
    select
      total_count,
      catalog_count,
      jsonb_array_length(amendment_items) as amendment_count,
      amendment_items -> 0 ->> 'amendment_number' as amendment_number,
      execution_items -> 0 ->> 'execution_status' as execution_status,
      available_authors,
      methodology_version
    from api.get_public_bahia_state_loa_study_filtered(
      2026::smallint,
      12,
      0,
      'antonio henrique junior',
      'execution_confirmed',
      'educacao barreiras'
    )
  `);
  assert.deepEqual(filteredStateLoaStudy.rows, [{
    total_count: 1,
    catalog_count: 3,
    amendment_count: 1,
    amendment_number: "102",
    execution_status: "execution_confirmed",
    available_authors: [
      { author_key: "antonio henrique junior", author_name: "Antonio Henrique Júnior" },
      { author_key: "diego castro", author_name: "Diego Castro" },
      { author_key: "marcone amaral", author_name: "Marcone Amaral" },
    ],
    methodology_version: "bahia-state-loa-study/1.1.0",
  }]);

  const emptyFilteredStateLoaStudy = await database.query(`
    select total_count, catalog_count,
      jsonb_array_length(amendment_items) as amendment_count
    from api.get_public_bahia_state_loa_study_filtered(
      2026::smallint, 12, 0, null, null, 'objeto inexistente'
    )
  `);
  assert.deepEqual(emptyFilteredStateLoaStudy.rows, [{
    total_count: 0,
    catalog_count: 3,
    amendment_count: 0,
  }]);

  const historicalStateExecution = await database.query(`
    select amendment_number, execution_status, committed_amount,
      liquidated_amount, paid_amount, execution_source_url,
      methodology_version
    from api.get_public_bahia_state_loa_execution(2022::smallint, null, 200)
    order by amendment_number
  `);
  assert.deepEqual(historicalStateExecution.rows, [{
    amendment_number: "101",
    execution_status: "official_link_key_unavailable",
    committed_amount: null,
    liquidated_amount: null,
    paid_amount: null,
    execution_source_url: null,
    methodology_version: "bahia-state-loa-public-execution/1.1.0",
  }]);

  const publicStateExecutionSummary = await database.query(`
    select fiscal_year, total_amendment_count, matched_amendment_count,
      ambiguous_amendment_count, not_found_amendment_count,
      unavailable_scope_count, authorized_total,
      matched_authorized_total, committed_total, liquidated_total, paid_total,
      methodology_version
    from api.get_public_bahia_state_loa_execution_summary(2026::smallint)
  `);
  assert.deepEqual(publicStateExecutionSummary.rows, [{
    fiscal_year: 2026,
    total_amendment_count: 3,
    matched_amendment_count: 1,
    ambiguous_amendment_count: 2,
    not_found_amendment_count: 0,
    unavailable_scope_count: 0,
    authorized_total: "1300000.00",
    matched_authorized_total: "200000.00",
    committed_total: "150000.00",
    liquidated_total: "100000.00",
    paid_total: "90000.00",
    methodology_version: "bahia-state-loa-public-execution-summary/1.0.0",
  }]);

  const stateRepresentativeContributions = await database.query(`
    select representative_source_kind, representative_external_id,
      author_key, author_name, fiscal_year, amendment_count,
      authorized_amount, matched_amendment_count, matched_authorized_amount,
      committed_amount, liquidated_amount, paid_amount,
      blocked_amendment_count, methodology_version
    from api.get_public_bahia_state_loa_representative_contributions(200)
    order by representative_source_kind, representative_external_id,
      fiscal_year desc
  `);
  assert.deepEqual(stateRepresentativeContributions.rows, [
    {
      representative_source_kind: "federal",
      representative_external_id: "220690",
      author_key: "capitao alden",
      author_name: "Capitão Alden",
      fiscal_year: 2023,
      amendment_count: 1,
      authorized_amount: "700000.00",
      matched_amendment_count: 0,
      matched_authorized_amount: null,
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      blocked_amendment_count: 1,
      methodology_version:
        "bahia-state-loa-representative-contributions/1.0.1",
    },
    {
      representative_source_kind: "state",
      representative_external_id: "921264",
      author_key: "antonio henrique junior",
      author_name: "Antonio Henrique Júnior",
      fiscal_year: 2026,
      amendment_count: 1,
      authorized_amount: "200000.00",
      matched_amendment_count: 1,
      matched_authorized_amount: "200000.00",
      committed_amount: "150000.00",
      liquidated_amount: "100000.00",
      paid_amount: "90000.00",
      blocked_amendment_count: 0,
      methodology_version:
        "bahia-state-loa-representative-contributions/1.0.1",
    },
    {
      representative_source_kind: "state",
      representative_external_id: "921264",
      author_key: "antonio henrique junior",
      author_name: "Antônio Henrique Jr.",
      fiscal_year: 2022,
      amendment_count: 1,
      authorized_amount: "100000.00",
      matched_amendment_count: 0,
      matched_authorized_amount: null,
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      blocked_amendment_count: 1,
      methodology_version:
        "bahia-state-loa-representative-contributions/1.0.1",
    },
    {
      representative_source_kind: "state",
      representative_external_id: "932099",
      author_key: "diego castro",
      author_name: "Diego Castro",
      fiscal_year: 2026,
      amendment_count: 1,
      authorized_amount: "600000.00",
      matched_amendment_count: 0,
      matched_authorized_amount: null,
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      blocked_amendment_count: 1,
      methodology_version:
        "bahia-state-loa-representative-contributions/1.0.1",
    },
    {
      representative_source_kind: "state",
      representative_external_id: "935240",
      author_key: "marcone amaral",
      author_name: "Marcone Amaral",
      fiscal_year: 2026,
      amendment_count: 1,
      authorized_amount: "500000.00",
      matched_amendment_count: 0,
      matched_authorized_amount: null,
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      blocked_amendment_count: 1,
      methodology_version:
        "bahia-state-loa-representative-contributions/1.0.1",
    },
  ]);

  const stateLoaDetails = await database.query(`
    select fiscal_year, amendment_number, author_name, authorized_amount,
      financial_stage, source_artifact_sha256, evidence_sha256,
      methodology_version
    from api.get_public_bahia_state_loa_amendments(null, null, 200)
  `);
  const stateLoaRanking = await database.query(`
    select rank_position, author_key, author_name, author_external_code,
      representative_source_kind, representative_external_id,
      representative_profile_url, association_status,
      amendment_count, authorized_amount, first_year, last_year,
      financial_stage, methodology_version
    from api.get_public_bahia_state_loa_amendment_ranking(null, 50)
  `);
  assert.deepEqual(stateLoaDetails.rows, [
    {
      fiscal_year: 2026,
      amendment_number: "105",
      author_name: "Diego Castro",
      authorized_amount: "600000.00",
      financial_stage: "authorized",
      source_artifact_sha256: "7".repeat(64),
      evidence_sha256: "f".repeat(64),
      methodology_version: "bahia-state-loa-amendments/1.0.0",
    },
    {
      fiscal_year: 2026,
      amendment_number: "103",
      author_name: "Marcone Amaral",
      authorized_amount: "500000.00",
      financial_stage: "authorized",
      source_artifact_sha256: "7".repeat(64),
      evidence_sha256: "c".repeat(64),
      methodology_version: "bahia-state-loa-amendments/1.0.0",
    },
    {
      fiscal_year: 2026,
      amendment_number: "102",
      author_name: "Antonio Henrique Júnior",
      authorized_amount: "200000.00",
      financial_stage: "authorized",
      source_artifact_sha256: "7".repeat(64),
      evidence_sha256: "b".repeat(64),
      methodology_version: "bahia-state-loa-amendments/1.0.0",
    },
    {
      fiscal_year: 2023,
      amendment_number: "104",
      author_name: "Capitão Alden",
      authorized_amount: "700000.00",
      financial_stage: "authorized",
      source_artifact_sha256: "7".repeat(64),
      evidence_sha256: "e".repeat(64),
      methodology_version: "bahia-state-loa-amendments/1.0.0",
    },
    {
      fiscal_year: 2022,
      amendment_number: "101",
      author_name: "Antônio Henrique Jr.",
      authorized_amount: "100000.00",
      financial_stage: "authorized",
      source_artifact_sha256: "7".repeat(64),
      evidence_sha256: "a".repeat(64),
      methodology_version: "bahia-state-loa-amendments/1.0.0",
    },
  ]);
  assert.deepEqual(stateLoaRanking.rows, [
    {
      rank_position: 1,
      author_key: "capitao alden",
      author_name: "Capitão Alden",
      author_external_code: null,
      representative_source_kind: "federal",
      representative_external_id: "220690",
      representative_profile_url:
        "https://www.camara.leg.br/deputados/220690",
      association_status: "approved_official_crosswalk",
      amendment_count: 1,
      authorized_amount: "700000.00",
      first_year: 2023,
      last_year: 2023,
      financial_stage: "authorized",
      methodology_version: "bahia-state-loa-amendment-ranking/1.2.0",
    },
    {
      rank_position: 2,
      author_key: "diego castro",
      author_name: "Diego Castro",
      author_external_code: "500123",
      representative_source_kind: "state",
      representative_external_id: "932099",
      representative_profile_url:
        "https://www.al.ba.gov.br/deputados/deputado-estadual/932099",
      association_status: "approved_official_crosswalk",
      amendment_count: 1,
      authorized_amount: "600000.00",
      first_year: 2026,
      last_year: 2026,
      financial_stage: "authorized",
      methodology_version: "bahia-state-loa-amendment-ranking/1.2.0",
    },
    {
      rank_position: 3,
      author_key: "marcone amaral",
      author_name: "Marcone Amaral",
      author_external_code: "500144",
      representative_source_kind: "state",
      representative_external_id: "935240",
      representative_profile_url:
        "https://www.al.ba.gov.br/deputados/deputado-estadual/935240",
      association_status: "approved_official_crosswalk",
      amendment_count: 1,
      authorized_amount: "500000.00",
      first_year: 2026,
      last_year: 2026,
      financial_stage: "authorized",
      methodology_version: "bahia-state-loa-amendment-ranking/1.2.0",
    },
    {
      rank_position: 4,
      author_key: "antonio henrique junior",
      author_name: "Antonio Henrique Júnior",
      author_external_code: "500069",
      representative_source_kind: "state",
      representative_external_id: "921264",
      representative_profile_url:
        "https://www.al.ba.gov.br/deputados/deputado-estadual/921264",
      association_status: "approved_official_crosswalk",
      amendment_count: 2,
      authorized_amount: "300000.00",
      first_year: 2022,
      last_year: 2026,
      financial_stage: "authorized",
      methodology_version: "bahia-state-loa-amendment-ranking/1.2.0",
    },
  ]);

  await database.exec("set role anon");
  const federalContributionProfile = await database.query(`
    select sphere, legislature_number, author_key, total_amendment_count,
      total_ranking_amount, row_position, fiscal_year, amendment_number,
      ranking_amount, execution_status, primary_source_url,
      methodology_version
    from api.get_public_parliamentary_legislature_contributions(
      'federal', 57::smallint, 'ricardo maia', 25, 0
    )
    order by row_position
  `);
  assert.deepEqual(federalContributionProfile.rows, [{
    sphere: "federal",
    legislature_number: 57,
    author_key: "ricardo maia",
    total_amendment_count: 1,
    total_ranking_amount: "250000.00",
    row_position: 1,
    fiscal_year: 2025,
    amendment_number: "2025.4460.0002",
    ranking_amount: "250000.00",
    execution_status: "matched_exact",
    primary_source_url:
      "https://api-publica.transferegov.gestao.gov.br/parcerias/proposta?cd_ibge_recebedor=2903201",
    methodology_version:
      "parliamentary-legislature-contributions/1.0.0",
  }]);

  const stateContributionProfile = await database.query(`
    select sphere, legislature_number, author_key, total_amendment_count,
      total_ranking_amount, total_committed_amount, total_liquidated_amount,
      total_paid_amount, row_position, fiscal_year, amendment_number,
      ranking_amount, execution_status, primary_source_url,
      methodology_version
    from api.get_public_parliamentary_legislature_contributions(
      'state', 20::smallint, 'antonio henrique junior', 25, 0
    )
    order by row_position
  `);
  assert.deepEqual(stateContributionProfile.rows, [{
    sphere: "state",
    legislature_number: 20,
    author_key: "antonio henrique junior",
    total_amendment_count: 1,
    total_ranking_amount: "200000.00",
    total_committed_amount: "150000.00",
    total_liquidated_amount: "100000.00",
    total_paid_amount: "90000.00",
    row_position: 1,
    fiscal_year: 2026,
    amendment_number: "102",
    ranking_amount: "200000.00",
    execution_status: "execution_confirmed",
    primary_source_url: "https://www.ba.gov.br/seplan/loa-fixture.pdf",
    methodology_version:
      "parliamentary-legislature-contributions/1.0.0",
  }]);

  const excludedTransitionContribution = await database.query(`
    select *
    from api.get_public_parliamentary_legislature_contributions(
      'state', 20::smallint, 'capitao alden', 25, 0
    )
  `);
  assert.equal(excludedTransitionContribution.rows.length, 0);

  await assert.rejects(
    database.query(`
      select * from api.get_public_parliamentary_legislature_contributions(
        'municipal', 20::smallint, 'autor', 25, 0
      )
    `),
    /esfera legislativa deve ser federal ou state/,
  );
  await assert.rejects(
    database.query(`
      select * from api.get_public_parliamentary_legislature_contributions(
        'state', 20::smallint, '', 25, 0
      )
    `),
    /autor legislativo invalido/,
  );
  await assert.rejects(
    database.query(`
      select * from api.get_public_parliamentary_legislature_contributions(
        'state', 20::smallint, 'autor', 101, 0
      )
    `),
    /limite de contribuicoes deve estar entre 1 e 100/,
  );
  const legislatureCoverage = await database.query(`
    select sphere, legislature_number, contribution_count, author_count,
      linked_author_count, unlinked_author_count,
      beneficiary_field_status, with_beneficiary_count,
      liquidated_field_status, with_liquidated_count,
      execution_confirmed_count, execution_unresolved_count,
      primary_evidence_count, methodology_version
    from api.get_public_parliamentary_legislature_coverage(null, null)
    order by case sphere when 'state' then 0 else 1 end,
      legislature_number desc
  `);
  assert.deepEqual(legislatureCoverage.rows, [
    {
      sphere: "state",
      legislature_number: 20,
      contribution_count: 3,
      author_count: 3,
      linked_author_count: 3,
      unlinked_author_count: 0,
      beneficiary_field_status: "not_published_in_source",
      with_beneficiary_count: null,
      liquidated_field_status: "published_by_source",
      with_liquidated_count: 1,
      execution_confirmed_count: 1,
      execution_unresolved_count: 2,
      primary_evidence_count: 3,
      methodology_version: "parliamentary-legislature-coverage/1.0.0",
    },
    {
      sphere: "state",
      legislature_number: 19,
      contribution_count: 1,
      author_count: 1,
      linked_author_count: 1,
      unlinked_author_count: 0,
      beneficiary_field_status: "not_published_in_source",
      with_beneficiary_count: null,
      liquidated_field_status: "published_by_source",
      with_liquidated_count: 0,
      execution_confirmed_count: 0,
      execution_unresolved_count: 1,
      primary_evidence_count: 1,
      methodology_version: "parliamentary-legislature-coverage/1.0.0",
    },
    {
      sphere: "federal",
      legislature_number: 57,
      contribution_count: 1,
      author_count: 1,
      linked_author_count: 1,
      unlinked_author_count: 0,
      beneficiary_field_status: "published_by_source",
      with_beneficiary_count: 1,
      liquidated_field_status: "not_published_in_source",
      with_liquidated_count: null,
      execution_confirmed_count: 1,
      execution_unresolved_count: 0,
      primary_evidence_count: 1,
      methodology_version: "parliamentary-legislature-coverage/1.0.0",
    },
    {
      sphere: "federal",
      legislature_number: 56,
      contribution_count: 2,
      author_count: 1,
      linked_author_count: 0,
      unlinked_author_count: 1,
      beneficiary_field_status: "published_by_source",
      with_beneficiary_count: 2,
      liquidated_field_status: "not_published_in_source",
      with_liquidated_count: null,
      execution_confirmed_count: 0,
      execution_unresolved_count: 2,
      primary_evidence_count: 2,
      methodology_version: "parliamentary-legislature-coverage/1.0.0",
    },
  ]);
  const legislatureYearCoverage = await database.query(`
    select
      count(*)::integer as expected_year_count,
      count(*) filter (where observation_status = 'observed')::integer
        as observed_year_count,
      count(*) filter (where observation_status = 'source_empty')::integer
        as source_empty_year_count,
      count(*) filter (where observation_status = 'collection_incomplete')::integer
        as collection_incomplete_year_count,
      count(*) filter (where observation_status = 'source_blocked')::integer
        as source_blocked_year_count,
      count(*) filter (where observation_status = 'collected_no_record')::integer
        as collected_no_record_year_count,
      count(*) filter (where observation_status = 'not_collected')::integer
        as not_collected_year_count,
      bool_and(
        (observation_status = 'observed' and contribution_count > 0)
        or (observation_status <> 'observed' and contribution_count = 0)
      ) as statuses_are_coherent,
      bool_and(author_count <= contribution_count) as authors_are_coherent,
      bool_and(primary_evidence_count <= contribution_count)
        as evidence_is_coherent
    from api.get_public_parliamentary_legislature_year_coverage(null, null)
  `);
  assert.deepEqual(legislatureYearCoverage.rows, [{
    expected_year_count: 12,
    observed_year_count: 4,
    source_empty_year_count: 1,
    collection_incomplete_year_count: 1,
    source_blocked_year_count: 1,
    collected_no_record_year_count: 1,
    not_collected_year_count: 4,
    statuses_are_coherent: true,
    authors_are_coherent: true,
    evidence_is_coherent: true,
  }]);
  await assert.rejects(
    database.query(`
      select * from api.get_public_parliamentary_legislature_coverage(
        'municipal', null
      )
    `),
    /esfera legislativa deve ser federal ou state/,
  );
  await assert.rejects(
    database.query(`
      select * from api.get_public_parliamentary_legislature_year_coverage(
        'municipal', null
      )
    `),
    /esfera legislativa deve ser federal ou state/,
  );
  const legislatureRankings = await database.query(`
    select sphere, legislature_number, rank_position, author_key,
      representative_source_kind, association_status, amendment_count,
      ranking_amount, committed_amount, liquidated_amount, paid_amount,
      first_year, last_year, ranking_amount_stage,
      excluded_transition_years::text as excluded_transition_years,
      methodology_version
    from api.get_public_parliamentary_legislature_rankings(null, null, 10)
    order by case sphere when 'state' then 0 else 1 end,
      legislature_number desc, rank_position
  `);
  assert.deepEqual(legislatureRankings.rows, [
    {
      sphere: "state",
      legislature_number: 20,
      rank_position: 1,
      author_key: "diego castro",
      representative_source_kind: "state",
      association_status: "approved_official_crosswalk",
      amendment_count: 1,
      ranking_amount: "600000.00",
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      first_year: 2026,
      last_year: 2026,
      ranking_amount_stage: "authorized",
      excluded_transition_years: "{2023}",
      methodology_version:
        "parliamentary-legislature-transfer-ranking/1.0.0",
    },
    {
      sphere: "state",
      legislature_number: 20,
      rank_position: 2,
      author_key: "marcone amaral",
      representative_source_kind: "state",
      association_status: "approved_official_crosswalk",
      amendment_count: 1,
      ranking_amount: "500000.00",
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      first_year: 2026,
      last_year: 2026,
      ranking_amount_stage: "authorized",
      excluded_transition_years: "{2023}",
      methodology_version:
        "parliamentary-legislature-transfer-ranking/1.0.0",
    },
    {
      sphere: "state",
      legislature_number: 20,
      rank_position: 3,
      author_key: "antonio henrique junior",
      representative_source_kind: "state",
      association_status: "approved_official_crosswalk",
      amendment_count: 1,
      ranking_amount: "200000.00",
      committed_amount: "150000.00",
      liquidated_amount: "100000.00",
      paid_amount: "90000.00",
      first_year: 2026,
      last_year: 2026,
      ranking_amount_stage: "authorized",
      excluded_transition_years: "{2023}",
      methodology_version:
        "parliamentary-legislature-transfer-ranking/1.0.0",
    },
    {
      sphere: "state",
      legislature_number: 19,
      rank_position: 1,
      author_key: "antonio henrique junior",
      representative_source_kind: "state",
      association_status: "approved_official_crosswalk",
      amendment_count: 1,
      ranking_amount: "100000.00",
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      first_year: 2022,
      last_year: 2022,
      ranking_amount_stage: "authorized",
      excluded_transition_years: "{2023}",
      methodology_version:
        "parliamentary-legislature-transfer-ranking/1.0.0",
    },
    {
      sphere: "federal",
      legislature_number: 57,
      rank_position: 1,
      author_key: "ricardo maia",
      representative_source_kind: "federal",
      association_status: "approved_official_crosswalk",
      amendment_count: 1,
      ranking_amount: "250000.00",
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      first_year: 2025,
      last_year: 2025,
      ranking_amount_stage: "destination",
      excluded_transition_years: "{2023}",
      methodology_version:
        "parliamentary-legislature-transfer-ranking/1.0.0",
    },
    {
      sphere: "federal",
      legislature_number: 56,
      rank_position: 1,
      author_key: "afonso florence",
      representative_source_kind: null,
      association_status: "not_linked",
      amendment_count: 2,
      ranking_amount: "900000.00",
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      first_year: 2021,
      last_year: 2021,
      ranking_amount_stage: "destination",
      excluded_transition_years: "{2023}",
      methodology_version:
        "parliamentary-legislature-transfer-ranking/1.0.0",
    },
  ]);
  assert.equal(
    legislatureRankings.rows.some((row) =>
      row.first_year === 2023 || row.last_year === 2023
    ),
    false,
    "2023 nao pode ser atribuido a uma legislatura sem data individual da emenda",
  );
  const people = await database.query(`
    select author_name, author_kind, representative_source_kind,
      representative_external_id, representative_profile_url,
      association_status, amendment_count, destination_amount,
      committed_amount, paid_amount, fully_paid_amendment_count,
      methodology_version
    from api.get_public_parliamentary_transfer_ranking('person', 2025::smallint, 50)
  `);
  const collectives = await database.query(`
    select author_name, author_kind, representative_source_kind,
      representative_external_id, representative_profile_url,
      association_status, amendment_count, destination_amount,
      committed_amount, paid_amount, fully_paid_amendment_count,
      methodology_version
    from api.get_public_parliamentary_transfer_ranking('collective', 2025::smallint, 50)
  `);
  const transfers = await database.query(`
    select amendment_number, author_name, author_kind, destination_amount,
      committed_amount, paid_amount, bank_order_number,
      stage_attribution_status, source_url, artifact_sha256,
      methodology_version
    from api.get_public_parliamentary_transfers(2025::smallint, null, 100)
    order by destination_amount desc
  `);
  const coverage = await database.query(`
    select fiscal_year, coverage_status, proposal_count,
      published_amendment_count,
      to_char(
        last_attempted_at at time zone 'UTC',
        'YYYY-MM-DD"T"HH24:MI:SS"Z"'
      ) as last_attempted_at,
      methodology_version
    from api.get_public_parliamentary_transfer_coverage(
      2021::smallint,
      2025::smallint
    )
    where fiscal_year in (2021, 2022, 2025)
    order by fiscal_year
  `);
  const historicalProposals = await database.query(`
    select proposal_id, proposal_number, fiscal_year, proposal_date_text,
      proposal_status, basic_project_status, modality, object_description,
      investment_item, proponent_name, federal_body_name,
      superior_federal_body_name, global_amount, requested_transfer_amount,
      counterpart_amount, authorship_status, financial_stage,
      source_url, artifact_sha256, methodology_version
    from api.get_public_federal_transfer_proposals(
      2021::smallint,
      'PROPOSTA APROVADA',
      100
    )
  `);
  const historicalAmendments = await database.query(`
    select proposal_id, fiscal_year, amendment_number, author_name,
      author_kind, is_mandatory, destination_amount, beneficiary_name,
      object_description, financial_stage, source_url, artifact_sha256,
      methodology_version
    from api.get_public_historical_parliamentary_amendments(
      2021::smallint,
      null,
      100
    )
    order by destination_amount desc
  `);
  const historicalPeople = await database.query(`
    select rank_position, author_name, author_kind, amendment_count,
      proposal_count, destination_amount, first_year, last_year,
      financial_stage, methodology_version
    from api.get_public_historical_parliamentary_amendment_ranking(
      'person',
      2021::smallint,
      50
    )
  `);
  const historicalCollectives = await database.query(`
    select rank_position, author_name, author_kind, amendment_count,
      proposal_count, destination_amount, first_year, last_year,
      financial_stage, methodology_version
    from api.get_public_historical_parliamentary_amendment_ranking(
      'collective',
      2021::smallint,
      50
    )
  `);
  const territorialScope = await database.query(`
    select candidate_proposal_count, included_proposal_count,
      excluded_regional_proposal_count, candidate_amendment_count,
      included_amendment_count, excluded_regional_amendment_count,
      excluded_regional_destination_amount, methodology_version
    from api.get_public_federal_transfer_scope_summary()
  `);
  const reconciledTransfers = await database.query(`
    select proposal_id, amendment_number, author_name, author_kind,
      reconciliation_status, destination_amount, current_destination_amount,
      historical_destination_amount, committed_amount, paid_amount,
      current_source_url, historical_source_url, methodology_version
    from api.get_public_reconciled_parliamentary_transfers(
      2025::smallint,
      null,
      100
    )
    order by proposal_id, amendment_number
  `);
  const reconciledPeople = await database.query(`
    select rank_position, author_name, author_kind,
      representative_external_id, association_status, amendment_count,
      proposal_count, destination_amount, committed_amount, paid_amount,
      methodology_version
    from api.get_public_reconciled_parliamentary_transfer_ranking(
      'person',
      null,
      50
    )
  `);
  const reconciliationSummary = await database.query(`
    select current_source_row_count, historical_source_row_count,
      consolidated_row_count, exact_match_count, current_only_count,
      historical_only_count, conflict_count, rankable_row_count,
      published_destination_amount, methodology_version
    from api.get_public_parliamentary_transfer_reconciliation_summary()
  `);
  await database.exec("reset role");

  assert.deepEqual(people.rows, [{
    author_name: "RICARDO MAIA",
    author_kind: "person",
    representative_source_kind: "federal",
    representative_external_id: "220694",
    representative_profile_url: "https://www.camara.leg.br/deputados/220694",
    association_status: "approved_official_crosswalk",
    amendment_count: 2,
    destination_amount: "350000.00",
    committed_amount: null,
    paid_amount: null,
    fully_paid_amendment_count: 0,
    methodology_version: "parliamentary-transfer-ranking/1.1.0",
  }]);
  assert.deepEqual(collectives.rows, [{
    author_name: "COMISSAO DA SAUDE",
    author_kind: "commission",
    representative_source_kind: null,
    representative_external_id: null,
    representative_profile_url: null,
    association_status: "not_applicable_collective",
    amendment_count: 1,
    destination_amount: "5000000.00",
    committed_amount: "5000000.00",
    paid_amount: "5000000.00",
    fully_paid_amendment_count: 1,
    methodology_version: "parliamentary-transfer-ranking/1.1.0",
  }]);
  assert.deepEqual(transfers.rows, [
    {
      amendment_number: "2025.5041.0002",
      author_name: "COMISSAO DA SAUDE",
      author_kind: "commission",
      destination_amount: "5000000.00",
      committed_amount: "5000000.00",
      paid_amount: "5000000.00",
      bank_order_number: "2025OB055607",
      stage_attribution_status: "exact_single_distribution",
      source_url:
        "https://api-publica.transferegov.gestao.gov.br/parcerias/proposta?cd_ibge_recebedor=2903201",
      artifact_sha256: "a".repeat(64),
      methodology_version: "parliamentary-transfers/1.0.0",
    },
    {
      amendment_number: "2025.4460.0002",
      author_name: "RICARDO MAIA",
      author_kind: "person",
      destination_amount: "250000.00",
      committed_amount: null,
      paid_amount: null,
      bank_order_number: null,
      stage_attribution_status: "exact_single_distribution",
      source_url:
        "https://api-publica.transferegov.gestao.gov.br/parcerias/proposta?cd_ibge_recebedor=2903201",
      artifact_sha256: "a".repeat(64),
      methodology_version: "parliamentary-transfers/1.0.0",
    },
    {
      amendment_number: "2025.4460.0099",
      author_name: "Ricardo Maia",
      author_kind: "person",
      destination_amount: "100000.00",
      committed_amount: null,
      paid_amount: null,
      bank_order_number: null,
      stage_attribution_status: "exact_single_distribution",
      source_url:
        "https://api-publica.transferegov.gestao.gov.br/parcerias/proposta?cd_ibge_recebedor=2903201",
      artifact_sha256: "a".repeat(64),
      methodology_version: "parliamentary-transfers/1.0.0",
    },
  ]);
  assert.equal(
    JSON.stringify(transfers.rows).includes("REGISTRO RETIRADO"),
    false,
    "um registro bruto ausente do snapshot ativo não pode continuar publicado",
  );
  assert.deepEqual(coverage.rows, [
    {
      fiscal_year: 2021,
      coverage_status: "empty",
      proposal_count: 0,
      published_amendment_count: 0,
      last_attempted_at: "2026-08-12T17:00:00Z",
      methodology_version: "parliamentary-transfer-coverage/1.0.0",
    },
    {
      fiscal_year: 2022,
      coverage_status: "empty",
      proposal_count: 0,
      published_amendment_count: 0,
      last_attempted_at: "2026-08-12T18:10:00Z",
      methodology_version: "parliamentary-transfer-coverage/1.0.0",
    },
    {
      fiscal_year: 2025,
      coverage_status: "complete",
      proposal_count: 3,
      published_amendment_count: 3,
      last_attempted_at: "2026-08-12T18:00:00Z",
      methodology_version: "parliamentary-transfer-coverage/1.0.0",
    },
  ]);
  assert.deepEqual(historicalProposals.rows, [{
    proposal_id: "9001",
    proposal_number: "000001/2021",
    fiscal_year: 2021,
    proposal_date_text: "15/06/2021",
    proposal_status: "PROPOSTA APROVADA",
    basic_project_status: "APROVADO",
    modality: "CONVENIO",
    object_description: "CONSTRUIR EQUIPAMENTO PUBLICO",
    investment_item: "INFRAESTRUTURA",
    proponent_name: "MUNICIPIO DE BARREIRAS",
    federal_body_name: "MINISTERIO DO DESENVOLVIMENTO",
    superior_federal_body_name: "MINISTERIO DO DESENVOLVIMENTO",
    global_amount: "1250000.50",
    requested_transfer_amount: "1200000.50",
    counterpart_amount: "50000.00",
    authorship_status: "not_available_in_proposal_source",
    financial_stage: "proposal_registered",
    source_url:
      "https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/siconv_proposta.zip",
    artifact_sha256: "9".repeat(64),
    methodology_version: "federal-transfer-proposals/1.0.0",
  }]);
  assert.deepEqual(historicalAmendments.rows, [
    {
      proposal_id: "9001",
      fiscal_year: 2021,
      amendment_number: "11110002",
      author_name: "AFONSO FLORENCE",
      author_kind: "person",
      is_mandatory: true,
      destination_amount: "500000.00",
      beneficiary_name: "MUNICIPIO DE BARREIRAS",
      object_description: "CONSTRUIR EQUIPAMENTO PUBLICO",
      financial_stage: "destination_identified_payment_not_verified",
      source_url:
        "https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/siconv_emenda.zip",
      artifact_sha256: "5".repeat(64),
      methodology_version: "historical-parliamentary-amendments/1.0.0",
    },
    {
      proposal_id: "9001",
      fiscal_year: 2021,
      amendment_number: "11110001",
      author_name: "AFONSO FLORENCE",
      author_kind: "person",
      is_mandatory: true,
      destination_amount: "400000.00",
      beneficiary_name: "MUNICIPIO DE BARREIRAS",
      object_description: "CONSTRUIR EQUIPAMENTO PUBLICO",
      financial_stage: "destination_identified_payment_not_verified",
      source_url:
        "https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/siconv_emenda.zip",
      artifact_sha256: "5".repeat(64),
      methodology_version: "historical-parliamentary-amendments/1.0.0",
    },
    {
      proposal_id: "9001",
      fiscal_year: 2021,
      amendment_number: "50070003",
      author_name: "COM. TURISMO",
      author_kind: "commission",
      is_mandatory: false,
      destination_amount: "300000.00",
      beneficiary_name: "MUNICIPIO DE BARREIRAS",
      object_description: "CONSTRUIR EQUIPAMENTO PUBLICO",
      financial_stage: "destination_identified_payment_not_verified",
      source_url:
        "https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/siconv_emenda.zip",
      artifact_sha256: "5".repeat(64),
      methodology_version: "historical-parliamentary-amendments/1.0.0",
    },
  ]);
  assert.deepEqual(historicalPeople.rows, [{
    rank_position: 1,
    author_name: "AFONSO FLORENCE",
    author_kind: "person",
    amendment_count: 2,
    proposal_count: 1,
    destination_amount: "900000.00",
    first_year: 2021,
    last_year: 2021,
    financial_stage: "destination_identified_payment_not_verified",
    methodology_version:
      "historical-parliamentary-amendment-ranking/1.0.0",
  }]);
  assert.deepEqual(historicalCollectives.rows, [{
    rank_position: 1,
    author_name: "COM. TURISMO",
    author_kind: "commission",
    amendment_count: 1,
    proposal_count: 1,
    destination_amount: "300000.00",
    first_year: 2021,
    last_year: 2021,
    financial_stage: "destination_identified_payment_not_verified",
    methodology_version:
      "historical-parliamentary-amendment-ranking/1.0.0",
  }]);
  assert.deepEqual(territorialScope.rows, [{
    candidate_proposal_count: 4,
    included_proposal_count: 3,
    excluded_regional_proposal_count: 1,
    candidate_amendment_count: 6,
    included_amendment_count: 5,
    excluded_regional_amendment_count: 1,
    excluded_regional_destination_amount: "700000.00",
    methodology_version: "federal-transfer-territorial-scope/1.0.0",
  }]);
  assert.deepEqual(reconciledTransfers.rows, [
    {
      proposal_id: "30854",
      amendment_number: "2025.5041.0002",
      author_name: "COMISSAO DA SAUDE",
      author_kind: "commission",
      reconciliation_status: "current_only",
      destination_amount: "5000000.00",
      current_destination_amount: "5000000.00",
      historical_destination_amount: null,
      committed_amount: "5000000.00",
      paid_amount: "5000000.00",
      current_source_url:
        "https://api-publica.transferegov.gestao.gov.br/parcerias/proposta?cd_ibge_recebedor=2903201",
      historical_source_url: null,
      methodology_version: "reconciled-parliamentary-transfers/1.0.0",
    },
    {
      proposal_id: "40000",
      amendment_number: "2025.4460.0099",
      author_name: "RICARDO MAIA",
      author_kind: "person",
      reconciliation_status: "conflict_source_divergence",
      destination_amount: null,
      current_destination_amount: "100000.00",
      historical_destination_amount: "99999.00",
      committed_amount: null,
      paid_amount: null,
      current_source_url:
        "https://api-publica.transferegov.gestao.gov.br/parcerias/proposta?cd_ibge_recebedor=2903201",
      historical_source_url:
        "https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/siconv_emenda.zip",
      methodology_version: "reconciled-parliamentary-transfers/1.0.0",
    },
    {
      proposal_id: "9274",
      amendment_number: "2025.4460.0002",
      author_name: "RICARDO MAIA",
      author_kind: "person",
      reconciliation_status: "matched_exact",
      destination_amount: "250000.00",
      current_destination_amount: "250000.00",
      historical_destination_amount: "250000.00",
      committed_amount: null,
      paid_amount: null,
      current_source_url:
        "https://api-publica.transferegov.gestao.gov.br/parcerias/proposta?cd_ibge_recebedor=2903201",
      historical_source_url:
        "https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/siconv_emenda.zip",
      methodology_version: "reconciled-parliamentary-transfers/1.0.0",
    },
  ]);
  assert.deepEqual(reconciledPeople.rows, [
    {
      rank_position: 1,
      author_name: "AFONSO FLORENCE",
      author_kind: "person",
      representative_external_id: null,
      association_status: "not_linked",
      amendment_count: 2,
      proposal_count: 1,
      destination_amount: "900000.00",
      committed_amount: null,
      paid_amount: null,
      methodology_version:
        "reconciled-parliamentary-transfer-ranking/1.0.0",
    },
    {
      rank_position: 2,
      author_name: "RICARDO MAIA",
      author_kind: "person",
      representative_external_id: "220694",
      association_status: "approved_official_crosswalk",
      amendment_count: 1,
      proposal_count: 1,
      destination_amount: "250000.00",
      committed_amount: null,
      paid_amount: null,
      methodology_version:
        "reconciled-parliamentary-transfer-ranking/1.0.0",
    },
  ]);
  assert.deepEqual(reconciliationSummary.rows, [{
    current_source_row_count: 3,
    historical_source_row_count: 5,
    consolidated_row_count: 6,
    exact_match_count: 1,
    current_only_count: 1,
    historical_only_count: 3,
    conflict_count: 1,
    rankable_row_count: 5,
    published_destination_amount: "6450000.00",
    methodology_version: "parliamentary-transfer-reconciliation/1.0.0",
  }]);

  const cguContracts = await database.query(`
    select
      to_regclass('territory.latest_cgu_federal_amendment_executions')::text
        as cgu_latest_projection,
      to_regclass('territory.cgu_federal_amendment_executions')::text
        as cgu_execution_projection,
      to_regclass('territory.cgu_transferegov_amendment_links')::text
        as cgu_link_projection,
      to_regprocedure(
        'api.get_public_cgu_federal_amendment_executions(smallint,text,integer)'
      )::text as cgu_execution_rpc,
      to_regprocedure(
        'api.get_public_cgu_federal_amendment_ranking(text,smallint,integer)'
      )::text as cgu_ranking_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_cgu_federal_amendment_executions(smallint,text,integer)',
        'EXECUTE'
      ) as anon_cgu_execution_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_cgu_federal_amendment_ranking(text,smallint,integer)',
        'EXECUTE'
      ) as anon_cgu_ranking_rpc
  `);
  assert.deepEqual(cguContracts.rows, [{
    cgu_latest_projection: "territory.latest_cgu_federal_amendment_executions",
    cgu_execution_projection: "territory.cgu_federal_amendment_executions",
    cgu_link_projection: "territory.cgu_transferegov_amendment_links",
    cgu_execution_rpc:
      "api.get_public_cgu_federal_amendment_executions(smallint,text,integer)",
    cgu_ranking_rpc:
      "api.get_public_cgu_federal_amendment_ranking(text,smallint,integer)",
    anon_cgu_execution_rpc: true,
    anon_cgu_ranking_rpc: true,
  }]);

  await database.exec(`
    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version, status
    ) values (
      '00000000-0000-0000-0000-000000009401',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'cgu-portal-transparencia'
         and endpoint.slug = 'federal-amendments-open-data'),
      'cgu-federal-amendment-fixture-run', 'test/1', 'succeeded'
    );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, idempotency_key, artifact_kind,
      source_url, retrieved_at, byte_size, sha256, object_key, collector_version
    ) values (
      '00000000-0000-0000-0000-000000009402',
      '00000000-0000-0000-0000-000000009401',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'cgu-portal-transparencia'
         and endpoint.slug = 'federal-amendments-open-data'),
      'cgu-federal-amendment-fixture-artifact', 'archive',
      'https://dadosabertos-download.cgu.gov.br/PortalDaTransparencia/saida/emendas-parlamentares/EmendasParlamentares.zip',
      '2026-08-16 12:00:00+00', 32110890, '${"ce".repeat(32)}',
      'cgu/emendas-federais/fixture.zip', 'test/1'
    );
    insert into raw.raw_records (
      id, raw_artifact_id, source_record_key, record_type, record_index,
      payload, payload_sha256, parser_version, idempotency_key, collected_at
    ) values
      (
        '00000000-0000-0000-0000-000000009410',
        '00000000-0000-0000-0000-000000009402',
        'cgu:federal-amendment:2023:202340720005:fixture',
        'cgu_federal_amendment_execution', 0,
        '{"fiscal_year":2023,"amendment_code":"202340720005","amendment_number":"0005","amendment_type":"Emenda Individual - Transferências com Finalidade Definida","author_code":"4072","author_name":"TITO","locality":"BARREIRAS - BA","municipality_ibge":"2903201","municipality_name":"BARREIRAS","state_ibge":"2900000","state_name":"BAHIA","region_name":"Nordeste","function_code":"05","function_name":"Defesa nacional","subfunction_code":"153","subfunction_name":"Defesa terrestre","program_code":"6012","program_name":"DEFESA NACIONAL","action_code":"219D","action_name":"ADEQUACAO DE ATIVOS","budget_plan_code":"0000","budget_plan_name":"DESPESAS DIVERSAS","committed_amount":"199925.68","liquidated_amount":"0.00","paid_amount":"0.00","outstanding_registered_amount":"0.00","outstanding_cancelled_amount":"0.00","outstanding_paid_amount":"0.00","source_row_number":75382}',
        '${"d1".repeat(32)}', 'cgu-federal-amendments/1.0.0',
        'cgu-fixture-record-0001-stale', '2026-08-15 12:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009411',
        '00000000-0000-0000-0000-000000009402',
        'cgu:federal-amendment:2023:202340720005:fixture',
        'cgu_federal_amendment_execution', 1,
        '{"fiscal_year":2023,"amendment_code":"202340720005","amendment_number":"0005","amendment_type":"Emenda Individual - Transferências com Finalidade Definida","author_code":"4072","author_name":"TITO","locality":"BARREIRAS - BA","municipality_ibge":"2903201","municipality_name":"BARREIRAS","state_ibge":"2900000","state_name":"BAHIA","region_name":"Nordeste","function_code":"05","function_name":"Defesa nacional","subfunction_code":"153","subfunction_name":"Defesa terrestre","program_code":"6012","program_name":"DEFESA NACIONAL","action_code":"219D","action_name":"ADEQUACAO DE ATIVOS","budget_plan_code":"0000","budget_plan_name":"DESPESAS DIVERSAS","committed_amount":"199925.68","liquidated_amount":"199925.68","paid_amount":"199925.68","outstanding_registered_amount":"0.00","outstanding_cancelled_amount":"0.00","outstanding_paid_amount":"0.00","source_row_number":75382}',
        '${"d2".repeat(32)}', 'cgu-federal-amendments/1.0.0',
        'cgu-fixture-record-0001', '2026-08-16 12:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009412',
        '00000000-0000-0000-0000-000000009402',
        'cgu:federal-amendment:2022:202240720004:fixture',
        'cgu_federal_amendment_execution', 2,
        '{"fiscal_year":2022,"amendment_code":"202240720004","amendment_number":"0004","amendment_type":"Emenda Individual - Transferências com Finalidade Definida","author_code":"4072","author_name":"TITO","locality":"BARREIRAS - BA","municipality_ibge":"2903201","municipality_name":"BARREIRAS","state_ibge":"2900000","state_name":"BAHIA","region_name":"Nordeste","function_code":"06","function_name":"Segurança pública","subfunction_code":"181","subfunction_name":"Policiamento","program_code":"5016","program_name":"SEGURANCA PUBLICA","action_code":"154T","action_name":"CONSTRUCAO DE UNIDADES DA PRF","budget_plan_code":"0000","budget_plan_name":"DESPESAS DIVERSAS","committed_amount":"500000.00","liquidated_amount":"500000.00","paid_amount":"88306.04","outstanding_registered_amount":"411693.96","outstanding_cancelled_amount":"0.00","outstanding_paid_amount":"411693.96","source_row_number":69236}',
        '${"d3".repeat(32)}', 'cgu-federal-amendments/1.0.0',
        'cgu-fixture-record-0002', '2026-08-16 12:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009413',
        '00000000-0000-0000-0000-000000009402',
        'cgu:federal-amendment:2021:202111110001:fixture',
        'cgu_federal_amendment_execution', 3,
        '{"fiscal_year":2021,"amendment_code":"202111110001","amendment_number":"0001","amendment_type":"Emenda Individual - Transferências com Finalidade Definida","author_code":"1111","author_name":"AFONSO FLORENCE","locality":"BARREIRAS - BA","municipality_ibge":"2903201","municipality_name":"BARREIRAS","state_ibge":"2900000","state_name":"BAHIA","region_name":"Nordeste","function_code":"15","function_name":"Urbanismo","subfunction_code":"451","subfunction_name":"infra-estrutura urbana","program_code":"2054","program_name":"PLANEJAMENTO URBANO","action_code":"1D73","action_name":"APOIO A POLITICA DE DESENVOLVIMENTO URBANO","budget_plan_code":"0000","budget_plan_name":"DESPESAS DIVERSAS","committed_amount":"400000.00","liquidated_amount":"0.00","paid_amount":"0.00","outstanding_registered_amount":"400000.00","outstanding_cancelled_amount":"0.00","outstanding_paid_amount":"400000.00","source_row_number":57000}',
        '${"d4".repeat(32)}', 'cgu-federal-amendments/1.0.0',
        'cgu-fixture-record-0003', '2026-08-16 12:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009414',
        '00000000-0000-0000-0000-000000009402',
        'cgu:federal-amendment:2021:202171060005:fixture',
        'cgu_federal_amendment_execution', 4,
        '{"fiscal_year":2021,"amendment_code":"202171060005","amendment_number":"0005","amendment_type":"Emenda de Bancada","author_code":"7106","author_name":"BANCADA DA BAHIA","locality":"BARREIRAS - BA","municipality_ibge":"2903201","municipality_name":"BARREIRAS","state_ibge":"2900000","state_name":"BAHIA","region_name":"Nordeste","function_code":"26","function_name":"Transporte","subfunction_code":"781","subfunction_name":"Transporte aéreo","program_code":"3004","program_name":"AVIACAO CIVIL","action_code":"14UB","action_name":"REFORMA DE AEROPORTOS REGIONAIS","budget_plan_code":"0000","budget_plan_name":"DESPESAS DIVERSAS","committed_amount":"3013986.00","liquidated_amount":"89899.44","paid_amount":"89899.44","outstanding_registered_amount":"5848173.12","outstanding_cancelled_amount":"0.00","outstanding_paid_amount":"2924086.56","source_row_number":57444}',
        '${"d5".repeat(32)}', 'cgu-federal-amendments/1.0.0',
        'cgu-fixture-record-0004', '2026-08-16 12:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009415',
        '00000000-0000-0000-0000-000000009402',
        'cgu:federal-amendment:2014:Sem informação:fixture',
        'cgu_federal_amendment_execution', 5,
        '{"fiscal_year":2014,"amendment_code":"Sem informação","amendment_number":"S/I","amendment_type":"Emenda Individual - Transferências com Finalidade Definida","author_code":"S/I","author_name":"Sem informação","locality":"BARREIRAS - BA","municipality_ibge":"2903201","municipality_name":"BARREIRAS","state_ibge":"2900000","state_name":"BAHIA","region_name":"Nordeste","function_code":"15","function_name":"Urbanismo","subfunction_code":"451","subfunction_name":"infra-estrutura urbana","program_code":"2054","program_name":"PLANEJAMENTO URBANO","action_code":"1D73","action_name":"APOIO A POLITICA DE DESENVOLVIMENTO URBANO","budget_plan_code":"0000","budget_plan_name":"APOIO - DESPESAS DIVERSAS","committed_amount":"1976600.00","liquidated_amount":"0.00","paid_amount":"0.00","outstanding_registered_amount":"0.00","outstanding_cancelled_amount":"228103.60","outstanding_paid_amount":"1748496.40","source_row_number":1308}',
        '${"d6".repeat(32)}', 'cgu-federal-amendments/1.0.0',
        'cgu-fixture-record-0005', '2026-08-16 12:00:00+00'
      );
  `);

  const cguExecutions = await database.query(`
    select
      fiscal_year,
      amendment_code,
      author_name,
      author_kind,
      author_identified,
      paid_amount,
      effective_paid_amount,
      transferegov_link_status,
      transferegov_reconciliation_key
    from api.get_public_cgu_federal_amendment_executions(null, null, 100)
  `);
  assert.deepEqual(cguExecutions.rows, [
    {
      fiscal_year: 2023,
      amendment_code: "202340720005",
      author_name: "TITO",
      author_kind: "person",
      author_identified: true,
      paid_amount: "199925.68",
      effective_paid_amount: "199925.68",
      transferegov_link_status: "not_found_in_transferegov",
      transferegov_reconciliation_key: null,
    },
    {
      fiscal_year: 2022,
      amendment_code: "202240720004",
      author_name: "TITO",
      author_kind: "person",
      author_identified: true,
      paid_amount: "88306.04",
      effective_paid_amount: "500000.00",
      transferegov_link_status: "not_found_in_transferegov",
      transferegov_reconciliation_key: null,
    },
    {
      fiscal_year: 2021,
      amendment_code: "202171060005",
      author_name: "BANCADA DA BAHIA",
      author_kind: "bench",
      author_identified: true,
      paid_amount: "89899.44",
      effective_paid_amount: "3013986.00",
      transferegov_link_status: "not_found_in_transferegov",
      transferegov_reconciliation_key: null,
    },
    {
      fiscal_year: 2021,
      amendment_code: "202111110001",
      author_name: "AFONSO FLORENCE",
      author_kind: "person",
      author_identified: true,
      paid_amount: "0.00",
      effective_paid_amount: "400000.00",
      transferegov_link_status: "matched_transferegov_unique",
      transferegov_reconciliation_key: "official:9001:11110001",
    },
    {
      fiscal_year: 2014,
      amendment_code: "Sem informação",
      author_name: "Sem informação",
      author_kind: "person",
      author_identified: false,
      paid_amount: "0.00",
      effective_paid_amount: "1748496.40",
      transferegov_link_status: "code_unavailable",
      transferegov_reconciliation_key: null,
    },
  ]);

  const cguPersonRanking = await database.query(`
    select
      rank_position,
      author_kind,
      author_name,
      amendment_count,
      committed_amount,
      effective_paid_amount,
      first_year,
      last_year,
      ranking_amount_stage,
      methodology_version
    from api.get_public_cgu_federal_amendment_ranking('person', null, 50)
  `);
  assert.deepEqual(cguPersonRanking.rows, [
    {
      rank_position: 1,
      author_kind: "person",
      author_name: "TITO",
      amendment_count: 2,
      committed_amount: "699925.68",
      effective_paid_amount: "699925.68",
      first_year: 2022,
      last_year: 2023,
      ranking_amount_stage: "committed",
      methodology_version: "cgu-federal-amendment-ranking/1.0.0",
    },
    {
      rank_position: 2,
      author_kind: "person",
      author_name: "AFONSO FLORENCE",
      amendment_count: 1,
      committed_amount: "400000.00",
      effective_paid_amount: "400000.00",
      first_year: 2021,
      last_year: 2021,
      ranking_amount_stage: "committed",
      methodology_version: "cgu-federal-amendment-ranking/1.0.0",
    },
  ]);

  const cguCollectiveRanking = await database.query(`
    select author_name, author_kind, committed_amount, effective_paid_amount
    from api.get_public_cgu_federal_amendment_ranking('collective', null, 50)
  `);
  assert.deepEqual(cguCollectiveRanking.rows, [
    {
      author_name: "BANCADA DA BAHIA",
      author_kind: "bench",
      committed_amount: "3013986.00",
      effective_paid_amount: "3013986.00",
    },
  ]);

  const cguFilteredRanking = await database.query(`
    select author_name
    from api.get_public_cgu_federal_amendment_ranking('person', 2021::smallint, 50)
  `);
  assert.deepEqual(cguFilteredRanking.rows, [
    { author_name: "AFONSO FLORENCE" },
  ]);

  const cguLegislatureRanking = await database.query(`
    select
      legislature_number,
      author_scope,
      rank_position,
      author_name,
      amendment_count,
      committed_amount,
      effective_paid_amount,
      first_year,
      last_year
    from api.get_public_cgu_federal_amendment_legislature_ranking(10)
  `);
  assert.deepEqual(
    cguLegislatureRanking.rows,
    [],
    "o ranking por legislatura não reutiliza o retrato agregado da CGU",
  );
  const cguLegislatureRankingDefinition = await database.query(`
    select pg_get_functiondef(procedure.oid) as definition
    from pg_proc as procedure
    join pg_namespace as namespace on namespace.oid = procedure.pronamespace
    where namespace.nspname = 'api'
      and procedure.proname = 'get_public_cgu_federal_amendment_legislature_ranking'
  `);
  assert.equal(cguLegislatureRankingDefinition.rows.length, 1);
  assert.doesNotMatch(
    cguLegislatureRankingDefinition.rows[0].definition,
    /reconciled_parliamentary_transfers|destination_amount/,
    "a serie CGU por legislatura nao pode misturar valores do Transferegov",
  );
  assert.doesNotMatch(
    cguLegislatureRankingDefinition.rows[0].definition,
    /cgu_federal_amendment_executions/,
    "o ranking por legislatura nao pode voltar ao retrato agregado antigo",
  );
  assert.match(
    cguLegislatureRankingDefinition.rows[0].definition,
    /cgu_federal_amendment_documents/,
    "o ranking por legislatura deve usar somente a serie documental",
  );

  await database.exec(`
    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version, status
    ) values (
      '00000000-0000-0000-0000-000000009501',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'bahia-open-data'
         and endpoint.slug = 'state-special-transfers'),
      'bahia-special-transfer-fixture-run', 'test/1', 'succeeded'
    );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, idempotency_key, artifact_kind,
      source_url, retrieved_at, byte_size, sha256, object_key,
      collector_version, content_type
    ) values (
      '00000000-0000-0000-0000-000000009502',
      '00000000-0000-0000-0000-000000009501',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'bahia-open-data'
         and endpoint.slug = 'state-special-transfers'),
      'bahia-special-transfer-fixture-artifact', 'archive',
      'https://dados.ba.gov.br/dataset/f2ecd7fa-24ce-4be2-80d5-08e2c11e3e1c/resource/809f9b7d-c252-482d-9c92-f2169d48c29c/download/transferenciasespeciais.zip',
      '2026-08-21 05:00:00+00', 554925, '${"95".repeat(32)}',
      'bahia/transferencias-especiais/fixture.zip', 'test/1',
      'application/zip'
    );
    insert into raw.extraction_jobs (
      id, raw_artifact_id, job_type, idempotency_key, status, attempt_count
    ) values (
      '00000000-0000-0000-0000-000000009503',
      '00000000-0000-0000-0000-000000009502',
      'bahia_special_transfer_payment_extraction',
      'bahia-special-transfer-fixture-job', 'succeeded', 1
    );
    insert into raw.extraction_results (
      id, extraction_job_id, candidate_type, extractor_version,
      validator_version, result_payload, validation_status
    ) values
      (
        '00000000-0000-0000-0000-000000009510',
        '00000000-0000-0000-0000-000000009503',
        'bahia_special_transfer_payment_candidate',
        'bahia-special-transfer-payment/1.0.0',
        'bahia-special-transfer-territorial-deterministic/1.0.0',
        '{"schema_name":"bahia-special-transfer-payment-candidate","schema_version":"1.0.0","fiscal_year":2022,"amendment_number":"40720003","amendment_year":2021,"author_name":"Tito","agency_name":"Secretaria estadual","agency_code":"SEAGRI","budget_unit_name":"Unidade estadual","budget_unit_code":"UO1","action_name":"Apoio hidrico","expense_code":"2022.1.1.1.1.1.1.1.1","execution_code":"2022.1.1.1.1.1.1.1.1","liquidation_codes":["L1"],"payment_id":"123456789012345678","payment_number":"P1","payment_date":"2022-10-05","payment_amount":"594841.25","gcv_amount":null,"payment_status":"Sim","object_text":"Pecas para pocos em Barreiras","payment_url":"https://www.transparencia.ba.gov.br/pagamento/1","territorial_scope":"payment_object_literal_barreiras","evidence_text":"evidencia 1","evidence_sha256":"${"a1".repeat(32)}","parser_version":"bahia-special-transfer-payment/1.0.0","source_url":"https://dados.ba.gov.br/transferencias-especiais","source_artifact_sha256":"${"95".repeat(32)}","source_collected_at":"2026-08-21T05:00:00+00:00"}',
        'valid'
      ),
      (
        '00000000-0000-0000-0000-000000009511',
        '00000000-0000-0000-0000-000000009503',
        'bahia_special_transfer_payment_candidate',
        'bahia-special-transfer-payment/1.0.0',
        'bahia-special-transfer-territorial-deterministic/1.0.0',
        '{"schema_name":"bahia-special-transfer-payment-candidate","schema_version":"1.0.0","fiscal_year":2022,"amendment_number":"40720005","amendment_year":2021,"author_name":"Tito","agency_name":"Secretaria estadual","agency_code":"SEAGRI","budget_unit_name":"Unidade estadual","budget_unit_code":"UO1","action_name":"Apoio hidrico","expense_code":"2022.1.1.1.1.1.1.1.2","execution_code":"2022.1.1.1.1.1.1.1.2","liquidation_codes":["L2"],"payment_id":"123456789012345679","payment_number":"P2","payment_date":"2022-11-17","payment_amount":"75300.00","gcv_amount":null,"payment_status":"Sim","object_text":"Equipamentos para pocos em Barreiras","payment_url":"https://www.transparencia.ba.gov.br/pagamento/2","territorial_scope":"payment_object_literal_barreiras","evidence_text":"evidencia 2","evidence_sha256":"${"a2".repeat(32)}","parser_version":"bahia-special-transfer-payment/1.0.0","source_url":"https://dados.ba.gov.br/transferencias-especiais","source_artifact_sha256":"${"95".repeat(32)}","source_collected_at":"2026-08-21T05:00:00+00:00"}',
        'valid'
      ),
      (
        '00000000-0000-0000-0000-000000009512',
        '00000000-0000-0000-0000-000000009503',
        'bahia_special_transfer_payment_candidate',
        'bahia-special-transfer-payment/1.0.0',
        'bahia-special-transfer-territorial-deterministic/1.0.0',
        '{"schema_name":"bahia-special-transfer-payment-candidate","schema_version":"1.0.0","fiscal_year":2022,"amendment_number":"40720005","amendment_year":2021,"author_name":"Tito","agency_name":"Secretaria estadual","agency_code":"SEAGRI","budget_unit_name":"Unidade estadual","budget_unit_code":"UO1","action_name":"Apoio hidrico","expense_code":"2022.1.1.1.1.1.1.1.3","execution_code":"2022.1.1.1.1.1.1.1.3","liquidation_codes":["L3"],"payment_id":"123456789012345680","payment_number":"P3","payment_date":"2022-11-17","payment_amount":"86763.50","gcv_amount":null,"payment_status":"Sim","object_text":"Equipamentos para pocos em Barreiras","payment_url":"https://www.transparencia.ba.gov.br/pagamento/3","territorial_scope":"payment_object_literal_barreiras","evidence_text":"evidencia 3","evidence_sha256":"${"a3".repeat(32)}","parser_version":"bahia-special-transfer-payment/1.0.0","source_url":"https://dados.ba.gov.br/transferencias-especiais","source_artifact_sha256":"${"95".repeat(32)}","source_collected_at":"2026-08-21T05:00:00+00:00"}',
        'valid'
      ),
      (
        '00000000-0000-0000-0000-000000009513',
        '00000000-0000-0000-0000-000000009503',
        'bahia_special_transfer_annual_coverage',
        'bahia-special-transfer-payment/1.0.0',
        'bahia-special-transfer-territorial-deterministic/1.0.0',
        '{"schema_name":"bahia-special-transfer-annual-coverage","schema_version":"1.0.0","coverage_start_year":2021,"coverage_end_year":2026,"years":[{"fiscal_year":2022,"source_payment_count":4176,"territorial_payment_count":3}],"territorial_scope":"payment_object_literal_barreiras","source_url":"https://dados.ba.gov.br/dataset/transferencias-especiais","source_artifact_sha256":"${"95".repeat(32)}","source_collected_at":"2026-08-21T05:00:00+00:00","parser_version":"bahia-special-transfer-payment/1.0.0"}',
        'valid'
      );

    insert into raw.raw_records (
      id, raw_artifact_id, source_record_key, record_type, record_index,
      payload, payload_sha256, parser_version, idempotency_key, collected_at
    ) values (
      '00000000-0000-0000-0000-000000009416',
      '00000000-0000-0000-0000-000000009402',
      'cgu:federal-amendment:2021:202140720003:fixture',
      'cgu_federal_amendment_execution', 6,
      '{"fiscal_year":2021,"amendment_code":"202140720003","amendment_number":"0003","amendment_type":"Emenda Individual - Transferencias com Finalidade Definida","author_code":"4072","author_name":"TITO","locality":"BARREIRAS - BA","municipality_ibge":"2903201","municipality_name":"BARREIRAS","state_ibge":"2900000","state_name":"BAHIA","region_name":"Nordeste","function_code":"20","function_name":"Agricultura","subfunction_code":"544","subfunction_name":"Recursos hidricos","program_code":"2208","program_name":"Desenvolvimento regional","action_code":"20ZV","action_name":"Apoio hidrico","budget_plan_code":"0000","budget_plan_name":"Despesas diversas","committed_amount":"594841.25","liquidated_amount":"594841.25","paid_amount":"594841.25","outstanding_registered_amount":"0.00","outstanding_cancelled_amount":"0.00","outstanding_paid_amount":"0.00","source_row_number":57001}',
      '${"d7".repeat(32)}', 'cgu-federal-amendments/1.0.0',
      'cgu-fixture-record-0006', '2026-08-21 05:00:00+00'
    );
  `);

  await database.exec("set role collector_worker");
  const initialSpecialTransferRefresh = await database.query(`
    select territory.refresh_bahia_special_transfer_payment_snapshot()
      as refreshed_rows
  `);
  assert.deepEqual(initialSpecialTransferRefresh.rows, [{ refreshed_rows: 3 }]);
  await database.exec("reset role");

  const initialSpecialTransferSnapshotAudit = await database.query(`
    select after_state, metadata
    from audit.audit_events
    where action = 'source_snapshot.refreshed'
      and target_type = 'territory.bahia_special_transfer_payment_snapshot'
    order by occurred_at desc, id desc
    limit 1
  `);
  const initialSnapshotState =
    initialSpecialTransferSnapshotAudit.rows[0].after_state;
  assert.match(initialSnapshotState.semantic_content_sha256, /^[0-9a-f]{64}$/);
  assert.match(initialSnapshotState.lineage_content_sha256, /^[0-9a-f]{64}$/);
  assert.equal(
    initialSnapshotState.content_sha256,
    initialSnapshotState.lineage_content_sha256,
  );

  await database.exec(`
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, idempotency_key, artifact_kind,
      source_url, retrieved_at, byte_size, sha256, object_key,
      collector_version, content_type
    )
    select
      '00000000-0000-0000-0000-000000009516',
      collection_run_id, source_endpoint_id,
      'bahia-special-transfer-fixture-artifact-refreshed', artifact_kind,
      source_url, '2026-08-22 05:00:00+00', byte_size, '${"96".repeat(32)}',
      'bahia/transferencias-especiais/fixture-refreshed.zip',
      collector_version, content_type
    from raw.raw_artifacts
    where id = '00000000-0000-0000-0000-000000009502';

    insert into raw.extraction_jobs (
      id, raw_artifact_id, job_type, idempotency_key, status, attempt_count
    ) values (
      '00000000-0000-0000-0000-000000009517',
      '00000000-0000-0000-0000-000000009516',
      'bahia_special_transfer_payment_extraction',
      'bahia-special-transfer-fixture-job-refreshed', 'succeeded', 1
    );

    insert into raw.extraction_results (
      id, extraction_job_id, candidate_type, extractor_version,
      validator_version, result_payload, validation_status
    )
    select
      case id
        when '00000000-0000-0000-0000-000000009510'
          then '00000000-0000-0000-0000-000000009520'::uuid
        when '00000000-0000-0000-0000-000000009511'
          then '00000000-0000-0000-0000-000000009521'::uuid
        else '00000000-0000-0000-0000-000000009522'::uuid
      end,
      '00000000-0000-0000-0000-000000009517',
      candidate_type, extractor_version, validator_version,
      jsonb_set(
        jsonb_set(
          result_payload,
          '{source_artifact_sha256}',
          to_jsonb('${"96".repeat(32)}'::text)
        ),
        '{source_collected_at}',
        to_jsonb('2026-08-22T05:00:00+00:00'::text)
      ),
      validation_status
    from raw.extraction_results
    where id in (
      '00000000-0000-0000-0000-000000009510',
      '00000000-0000-0000-0000-000000009511',
      '00000000-0000-0000-0000-000000009512'
    );
  `);
  await database.exec("set role collector_worker");
  await database.query(
    "select territory.refresh_bahia_special_transfer_payment_snapshot()",
  );
  await database.exec("reset role");

  const refreshedSpecialTransferSnapshotAudit = await database.query(`
    select after_state
    from audit.audit_events
    where action = 'source_snapshot.refreshed'
      and target_type = 'territory.bahia_special_transfer_payment_snapshot'
    order by occurred_at desc, id desc
    limit 1
  `);
  const refreshedSnapshotState =
    refreshedSpecialTransferSnapshotAudit.rows[0].after_state;
  assert.equal(
    refreshedSnapshotState.semantic_content_sha256,
    initialSnapshotState.semantic_content_sha256,
    "nova preservacao sem mudanca factual deve manter o hash semantico",
  );
  assert.notEqual(
    refreshedSnapshotState.lineage_content_sha256,
    initialSnapshotState.lineage_content_sha256,
    "a nova cadeia de custodia deve renovar o hash integral",
  );
  assert.equal(
    refreshedSnapshotState.content_sha256,
    refreshedSnapshotState.lineage_content_sha256,
  );

  const specialTransferSnapshotParity = await database.query(`
    with live as (
      select * from territory.latest_bahia_special_transfer_payment_candidates_live
    ), snapshot as (
      select * from territory.bahia_special_transfer_payment_snapshot
    ), stable as (
      select * from territory.latest_bahia_special_transfer_payment_candidates
    )
    select
      (select count(*)::integer from live) as live_count,
      (select count(*)::integer from snapshot) as snapshot_count,
      (select count(*)::integer from stable) as stable_count,
      (select count(*)::integer from (
        (select * from live except select * from snapshot)
        union all
        (select * from snapshot except select * from live)
      ) as differences) as difference_count
  `);
  assert.deepEqual(specialTransferSnapshotParity.rows, [{
    live_count: 3,
    snapshot_count: 3,
    stable_count: 3,
    difference_count: 0,
  }]);

  const specialTransferSnapshotPrivileges = await database.query(`
    select
      has_table_privilege(
        'anon',
        'territory.bahia_special_transfer_payment_snapshot',
        'SELECT'
      ) as anon_snapshot_select,
      has_table_privilege(
        'collector_worker',
        'territory.bahia_special_transfer_payment_snapshot',
        'SELECT'
      ) as worker_snapshot_select,
      has_function_privilege(
        'anon',
        'territory.refresh_bahia_special_transfer_payment_snapshot()',
        'EXECUTE'
      ) as anon_refresh,
      has_function_privilege(
        'collector_worker',
        'territory.refresh_bahia_special_transfer_payment_snapshot()',
        'EXECUTE'
      ) as worker_refresh
  `);
  assert.deepEqual(specialTransferSnapshotPrivileges.rows, [{
    anon_snapshot_select: false,
    worker_snapshot_select: false,
    anon_refresh: false,
    worker_refresh: true,
  }]);

  const specialTransferPayments = await database.query(`
    select amendment_number, official_author_name,
      representative_external_id, payment_date, payment_amount,
      financial_stage, federal_link_status, aggregation_policy
    from api.get_public_bahia_special_transfer_payments(null, null, 100)
  `);
  assert.deepEqual(specialTransferPayments.rows, [
    {
      amendment_number: "40720005",
      official_author_name: "Carlos Tito Marques Cordeiro",
      representative_external_id: "197438",
      payment_date: new Date("2022-11-17T00:00:00.000Z"),
      payment_amount: "86763.50",
      financial_stage: "paid_by_bahia_state",
      federal_link_status: "not_found_in_cgu",
      aggregation_policy: "single_source_no_cross_source_sum",
    },
    {
      amendment_number: "40720005",
      official_author_name: "Carlos Tito Marques Cordeiro",
      representative_external_id: "197438",
      payment_date: new Date("2022-11-17T00:00:00.000Z"),
      payment_amount: "75300.00",
      financial_stage: "paid_by_bahia_state",
      federal_link_status: "not_found_in_cgu",
      aggregation_policy: "single_source_no_cross_source_sum",
    },
    {
      amendment_number: "40720003",
      official_author_name: "Carlos Tito Marques Cordeiro",
      representative_external_id: "197438",
      payment_date: new Date("2022-10-05T00:00:00.000Z"),
      payment_amount: "594841.25",
      financial_stage: "paid_by_bahia_state",
      federal_link_status: "matched_cgu_unique",
      aggregation_policy: "single_source_no_cross_source_sum",
    },
  ]);

  const paginatedSpecialTransferPayments = await database.query(`
    select amendment_number, payment_amount
    from api.get_public_bahia_special_transfer_payments(2, null, null, 2)
  `);
  assert.deepEqual(paginatedSpecialTransferPayments.rows, [{
    amendment_number: "40720003",
    payment_amount: "594841.25",
  }]);

  const specialTransferRanking = await database.query(`
    select rank_position, official_author_name, representative_external_id,
      payment_count, amendment_count, paid_amount, first_payment_date,
      last_payment_date, ranking_amount_stage, aggregation_policy
    from api.get_public_bahia_special_transfer_ranking(null, 10)
  `);
  assert.deepEqual(specialTransferRanking.rows, [{
    rank_position: 1,
    official_author_name: "Carlos Tito Marques Cordeiro",
    representative_external_id: "197438",
    payment_count: 3,
    amendment_count: 2,
    paid_amount: "756904.75",
    first_payment_date: new Date("2022-10-05T00:00:00.000Z"),
    last_payment_date: new Date("2022-11-17T00:00:00.000Z"),
    ranking_amount_stage: "paid_by_bahia_state",
    aggregation_policy: "single_source_no_cross_source_sum",
  }]);

  const specialTransferAnnualCoverage = await database.query(`
    select fiscal_year, source_payment_count, territorial_payment_count,
      territorial_status, source_snapshot_status, territorial_scope,
      source_url, source_artifact_sha256, methodology_version
    from api.get_public_bahia_special_transfer_annual_coverage()
  `);
  assert.deepEqual(specialTransferAnnualCoverage.rows, [{
    fiscal_year: 2022,
    source_payment_count: 4176,
    territorial_payment_count: 3,
    territorial_status: "territorial_records_observed",
    source_snapshot_status: "source_snapshot_processed",
    territorial_scope: "payment_object_literal_barreiras",
    source_url: "https://dados.ba.gov.br/dataset/transferencias-especiais",
    source_artifact_sha256: "95".repeat(32),
    methodology_version: "bahia-special-transfer-annual-coverage/1.0.0",
  }]);

  assert.equal(JSON.stringify(specialTransferPayments.rows).includes("cpf"), false);
  assert.equal(JSON.stringify(specialTransferPayments.rows).includes("cnpj"), false);
  assert.equal(JSON.stringify(specialTransferPayments.rows).includes("creditor"), false);

  await database.exec(`
    insert into raw.extraction_jobs (
      id, raw_artifact_id, job_type, idempotency_key, status, attempt_count
    ) values (
      '00000000-0000-0000-0000-000000009514',
      '00000000-0000-0000-0000-000000009502',
      'bahia_special_transfer_payment_extraction',
      'bahia-special-transfer-fixture-job-refresh', 'succeeded', 1
    );
    insert into raw.extraction_results (
      id, extraction_job_id, candidate_type, extractor_version,
      validator_version, result_payload, validation_status
    )
    select
      '00000000-0000-0000-0000-000000009515',
      '00000000-0000-0000-0000-000000009514',
      candidate_type, extractor_version, validator_version,
      jsonb_set(
        jsonb_set(result_payload, '{payment_amount}', '86763.51'::jsonb),
        '{source_collected_at}',
        to_jsonb('2026-08-23T05:00:00+00:00'::text)
      ),
      validation_status
    from raw.extraction_results
    where id = '00000000-0000-0000-0000-000000009512';
  `);
  await database.exec("set role collector_worker");
  await database.query(
    "select territory.refresh_bahia_special_transfer_payment_snapshot()",
  );
  await database.exec("reset role");
  const refreshedSpecialTransferPayment = await database.query(`
    select payment_amount
    from territory.bahia_special_transfer_payment_snapshot
    where payment_id = '123456789012345680'
  `);
  assert.deepEqual(refreshedSpecialTransferPayment.rows, [{
    payment_amount: "86763.51",
  }]);

  const specialTransferSnapshotBeforeCorruption = await database.query(`
    select *
    from territory.bahia_special_transfer_payment_snapshot
    order by payment_id
  `);
  await database.exec(`
    create function territory.test_corrupt_special_transfer_snapshot()
    returns trigger language plpgsql
    as $$
    begin
      if new.payment_id = '123456789012345678' then
        new.payment_amount := new.payment_amount + 1;
      end if;
      return new;
    end;
    $$;
    create trigger test_corrupt_special_transfer_snapshot
      before insert on territory.bahia_special_transfer_payment_snapshot
      for each row execute function
        territory.test_corrupt_special_transfer_snapshot();
  `);
  await database.exec("set role collector_worker");
  await assert.rejects(
    database.query(
      "select territory.refresh_bahia_special_transfer_payment_snapshot()",
    ),
    /divergiu da fonte canonica/,
  );
  await database.exec("reset role");
  const snapshotAfterSameCountCorruption = await database.query(`
    select *
    from territory.bahia_special_transfer_payment_snapshot
    order by payment_id
  `);
  assert.deepEqual(
    snapshotAfterSameCountCorruption.rows,
    specialTransferSnapshotBeforeCorruption.rows,
  );
  await database.exec(`
    drop trigger test_corrupt_special_transfer_snapshot
      on territory.bahia_special_transfer_payment_snapshot;
    drop function territory.test_corrupt_special_transfer_snapshot();
    create function territory.test_drop_special_transfer_snapshot()
    returns trigger language plpgsql
    as $$
    begin
      if new.payment_id = '123456789012345678' then
        return null;
      end if;
      return new;
    end;
    $$;
    create trigger test_drop_special_transfer_snapshot
      before insert on territory.bahia_special_transfer_payment_snapshot
      for each row execute function
        territory.test_drop_special_transfer_snapshot();
  `);
  await database.exec("set role collector_worker");
  await assert.rejects(
    database.query(
      "select territory.refresh_bahia_special_transfer_payment_snapshot()",
    ),
    /divergiu da fonte canonica/,
  );
  await database.exec("reset role");
  const snapshotAfterLostRow = await database.query(`
    select *
    from territory.bahia_special_transfer_payment_snapshot
    order by payment_id
  `);
  assert.deepEqual(
    snapshotAfterLostRow.rows,
    specialTransferSnapshotBeforeCorruption.rows,
  );
  await database.exec(`
    drop trigger test_drop_special_transfer_snapshot
      on territory.bahia_special_transfer_payment_snapshot;
    drop function territory.test_drop_special_transfer_snapshot();
  `);

  await database.exec(`
    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version, status
    ) values (
      '00000000-0000-0000-0000-000000009801',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'cgu-portal-transparencia'
         and endpoint.slug = 'federal-amendment-documents-open-data'),
      'cgu-document-fixture-run', 'test/1', 'succeeded'
    );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, idempotency_key, artifact_kind,
      source_url, retrieved_at, byte_size, sha256, object_key,
      collector_version, content_type
    ) values (
      '00000000-0000-0000-0000-000000009802',
      '00000000-0000-0000-0000-000000009801',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'cgu-portal-transparencia'
         and endpoint.slug = 'federal-amendment-documents-open-data'),
      'cgu-document-fixture-artifact', 'archive',
      'https://dadosabertos-download.cgu.gov.br/PortalDaTransparencia/saida/emendas-parlamentares-documentos/2024_EmendasParlamentaresPorDocumento.zip',
      '2026-08-21 20:00:00+00', 15625915, '${"98".repeat(32)}',
      'cgu/emendas-federais/documentos/2024/fixture.zip', 'test/1',
      'application/zip'
    ), (
      '00000000-0000-0000-0000-000000009803',
      '00000000-0000-0000-0000-000000009801',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'cgu-portal-transparencia'
         and endpoint.slug = 'federal-amendment-documents-open-data'),
      'cgu-document-fixture-artifact-2022', 'archive',
      'https://dadosabertos-download.cgu.gov.br/PortalDaTransparencia/saida/emendas-parlamentares-documentos/2022_EmendasParlamentaresPorDocumento.zip',
      '2026-08-21 20:00:00+00', 12500000, '${"97".repeat(32)}',
      'cgu/emendas-federais/documentos/2022/fixture.zip', 'test/1',
      'application/zip'
    );
    insert into raw.raw_records (
      id, raw_artifact_id, source_record_key, record_type, record_index,
      payload, payload_sha256, parser_version, idempotency_key, collected_at
    ) values
      (
        '00000000-0000-0000-0000-000000009810',
        '00000000-0000-0000-0000-000000009802',
        'cgu:federal-amendment-document:2024:202450410002:fixture-1',
        'cgu_federal_amendment_document', 0,
        '{"archive_year":2024,"amendment_year":2024,"amendment_code":"202450410002","amendment_number":"0002","amendment_type":"Emenda de Comissão","author_code":"5041","author_name":"COM. DA SAUDE","document_date":"2024-06-12","document_code":"257001000012024NE400001","expense_stage":"commitment","expense_stage_source":"Empenho","committed_amount":"5000000.00","paid_amount":"0.00","beneficiary_name":"FUNDO MUNICIPAL DE SAUDE DE BARREIRAS","beneficiary_type":"FUNDO PUBLICO","beneficiary_municipality":"BARREIRAS","locality":"BARREIRAS - BA","municipality_ibge":"2903201","agency_name":"MINISTERIO DA SAUDE","superior_agency_name":"MINISTERIO DA SAUDE","function_name":"SAUDE","subfunction_name":"ASSISTENCIA HOSPITALAR","program_name":"ATENCAO ESPECIALIZADA","action_name":"CUSTEIO DA SAUDE","citizen_language":"Apoio ao custeio da saude","document_line_fingerprint":"${"81".repeat(32)}","source_row_number":100}',
        '${"81".repeat(32)}', 'cgu-federal-amendment-documents/1.0.0',
        'cgu-document-fixture-record-1', '2026-08-21 20:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009811',
        '00000000-0000-0000-0000-000000009802',
        'cgu:federal-amendment-document:2024:202450410002:fixture-2',
        'cgu_federal_amendment_document', 1,
        '{"archive_year":2024,"amendment_year":2024,"amendment_code":"202450410002","amendment_number":"0002","amendment_type":"Emenda de Comissão","author_code":"5041","author_name":"COM. DA SAUDE","document_date":"2024-06-24","document_code":"257001000012024OB018682","expense_stage":"payment","expense_stage_source":"Pagamento","committed_amount":"0.00","paid_amount":"7500000.00","beneficiary_name":"FUNDO MUNICIPAL DE SAUDE DE BARREIRAS","beneficiary_type":"FUNDO PUBLICO","beneficiary_municipality":"BARREIRAS","locality":"BARREIRAS - BA","municipality_ibge":"2903201","agency_name":"MINISTERIO DA SAUDE","superior_agency_name":"MINISTERIO DA SAUDE","function_name":"SAUDE","subfunction_name":"ASSISTENCIA HOSPITALAR","program_name":"ATENCAO ESPECIALIZADA","action_name":"CUSTEIO DA SAUDE","citizen_language":"Apoio ao custeio da saude","document_line_fingerprint":"${"82".repeat(32)}","source_row_number":101}',
        '${"82".repeat(32)}', 'cgu-federal-amendment-documents/1.0.0',
        'cgu-document-fixture-record-2', '2026-08-21 20:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009812',
        '00000000-0000-0000-0000-000000009802',
        'cgu:federal-amendment-document:2024:202450410002:fixture-3',
        'cgu_federal_amendment_document', 2,
        '{"archive_year":2024,"amendment_year":2024,"amendment_code":"202450410002","amendment_number":"0002","amendment_type":"Emenda de Comissão","author_code":"5041","author_name":"COM. DA SAUDE","document_date":"2024-06-24","document_code":"257001000012024OB018682","expense_stage":"payment","expense_stage_source":"Pagamento","committed_amount":"0.00","paid_amount":"2500000.00","beneficiary_name":"FUNDO MUNICIPAL DE SAUDE DE BARREIRAS","beneficiary_type":"FUNDO PUBLICO","beneficiary_municipality":"BARREIRAS","locality":"BARREIRAS - BA","municipality_ibge":"2903201","agency_name":"MINISTERIO DA SAUDE","superior_agency_name":"MINISTERIO DA SAUDE","function_name":"SAUDE","subfunction_name":"ASSISTENCIA HOSPITALAR","program_name":"ATENCAO ESPECIALIZADA","action_name":"CUSTEIO DA SAUDE","citizen_language":"Apoio ao custeio da saude","document_line_fingerprint":"${"83".repeat(32)}","source_row_number":102}',
        '${"83".repeat(32)}', 'cgu-federal-amendment-documents/1.0.0',
        'cgu-document-fixture-record-3', '2026-08-21 20:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009813',
        '00000000-0000-0000-0000-000000009803',
        'cgu:federal-amendment-document:2022:202240720001:fixture-1',
        'cgu_federal_amendment_document', 0,
        '{"archive_year":2022,"amendment_year":2022,"amendment_code":"202240720001","amendment_number":"0001","amendment_type":"Emenda Individual","author_code":"4072","author_name":"TITO","document_date":"2022-08-10","document_code":"257001000012022NE400001","expense_stage":"commitment","expense_stage_source":"Empenho","committed_amount":"500000.00","paid_amount":"0.00","beneficiary_name":"FUNDO MUNICIPAL DE SAUDE DE BARREIRAS","beneficiary_type":"FUNDO PUBLICO","beneficiary_municipality":"BARREIRAS","locality":"BARREIRAS - BA","municipality_ibge":"2903201","agency_name":"MINISTERIO DA SAUDE","superior_agency_name":"MINISTERIO DA SAUDE","function_name":"SAUDE","subfunction_name":"ATENCAO BASICA","program_name":"ATENCAO PRIMARIA","action_name":"CUSTEIO DA SAUDE","citizen_language":"Apoio ao custeio da saude","document_line_fingerprint":"${"84".repeat(32)}","source_row_number":200}',
        '${"84".repeat(32)}', 'cgu-federal-amendment-documents/1.0.0',
        'cgu-document-fixture-record-4', '2026-08-21 20:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009814',
        '00000000-0000-0000-0000-000000009803',
        'cgu:federal-amendment-document:2022:202240720001:fixture-2',
        'cgu_federal_amendment_document', 1,
        '{"archive_year":2022,"amendment_year":2022,"amendment_code":"202240720001","amendment_number":"0001","amendment_type":"Emenda Individual","author_code":"4072","author_name":"TITO","document_date":"2022-10-05","document_code":"257001000012022OB018682","expense_stage":"payment","expense_stage_source":"Pagamento","committed_amount":"0.00","paid_amount":"480000.00","beneficiary_name":"FUNDO MUNICIPAL DE SAUDE DE BARREIRAS","beneficiary_type":"FUNDO PUBLICO","beneficiary_municipality":"BARREIRAS","locality":"BARREIRAS - BA","municipality_ibge":"2903201","agency_name":"MINISTERIO DA SAUDE","superior_agency_name":"MINISTERIO DA SAUDE","function_name":"SAUDE","subfunction_name":"ATENCAO BASICA","program_name":"ATENCAO PRIMARIA","action_name":"CUSTEIO DA SAUDE","citizen_language":"Apoio ao custeio da saude","document_line_fingerprint":"${"85".repeat(32)}","source_row_number":201}',
        '${"85".repeat(32)}', 'cgu-federal-amendment-documents/1.0.0',
        'cgu-document-fixture-record-5', '2026-08-21 20:00:00+00'
      );
  `);

  const cguDocumentContracts = await database.query(`
    select
      to_regclass('territory.cgu_federal_amendment_documents')::text
        as document_projection,
      to_regprocedure(
        'api.get_public_cgu_federal_amendment_documents(smallint,text,integer)'
      )::text as document_rpc,
      to_regprocedure(
        'api.get_public_cgu_federal_amendment_document_ranking(smallint,integer)'
      )::text as ranking_rpc
  `);
  assert.deepEqual(cguDocumentContracts.rows, [{
    document_projection: "territory.cgu_federal_amendment_documents",
    document_rpc:
      "api.get_public_cgu_federal_amendment_documents(smallint,text,integer)",
    ranking_rpc:
      "api.get_public_cgu_federal_amendment_document_ranking(smallint,integer)",
  }]);
  const cguDocumentRanking = await database.query(`
    select author_name, amendment_count, document_count,
      committed_amount, paid_amount, aggregation_policy
    from api.get_public_cgu_federal_amendment_document_ranking(
      2024::smallint, 10
    )
  `);
  assert.deepEqual(cguDocumentRanking.rows, [{
    author_name: "COM. DA SAUDE",
    amendment_count: 1,
    document_count: 2,
    committed_amount: "5000000.00",
    paid_amount: "10000000.00",
    aggregation_policy: "single_document_source_no_cross_source_sum",
  }]);

  const cguDocumentLegislatureRanking = await database.query(`
    select legislature_number, author_scope, rank_position, author_name,
      author_code, representative_source_kind, representative_external_id,
      representative_profile_url, association_status, amendment_count,
      committed_amount, effective_paid_amount, first_year, last_year,
      methodology_version
    from api.get_public_cgu_federal_amendment_legislature_ranking(10)
  `);
  assert.deepEqual(cguDocumentLegislatureRanking.rows, [
    {
      legislature_number: 57,
      author_scope: "collective",
      rank_position: 1,
      author_name: "COM. DA SAUDE",
      author_code: "5041",
      representative_source_kind: null,
      representative_external_id: null,
      representative_profile_url: null,
      association_status: "not_linked",
      amendment_count: 1,
      committed_amount: "5000000.00",
      effective_paid_amount: "10000000.00",
      first_year: 2024,
      last_year: 2024,
      methodology_version:
        "cgu-federal-amendment-legislature-ranking/2.0.0",
    },
    {
      legislature_number: 56,
      author_scope: "person",
      rank_position: 1,
      author_name: "TITO",
      author_code: "4072",
      representative_source_kind: "federal",
      representative_external_id: "197438",
      representative_profile_url:
        "https://www.camara.leg.br/deputados/197438",
      association_status: "approved_official_author_code_crosswalk",
      amendment_count: 1,
      committed_amount: "500000.00",
      effective_paid_amount: "480000.00",
      first_year: 2022,
      last_year: 2022,
      methodology_version:
        "cgu-federal-amendment-legislature-ranking/2.0.0",
    },
  ]);

  const reducedSnapshotRecords = [currentSnapshotRecords.find(
    (record) => record.source_record_key === "transferegov:proposta:40000",
  )];
  const reducedSnapshotFingerprint = createHash("sha256")
    .update(reducedSnapshotRecords.map((record) =>
      `${record.record_type}\x1f${record.source_record_key}\x1f${record.payload_sha256}`
    ).join("\n"), "utf8")
    .digest("hex");
  await database.exec(`
    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version, status
    ) values (
      '00000000-0000-0000-0000-000000009003',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'transferegov-parcerias'
         and endpoint.slug = 'propostas-barreiras'),
      'transferegov-snapshot-failed-fixture', 'test/1', 'running'
    );
  `);
  await assert.rejects(
    database.query(`
      select source.stage_transferegov_snapshot(
        '00000000-0000-0000-0000-000000009003'::uuid,
        2024::smallint,
        '${JSON.stringify(reducedSnapshotRecords)}'::jsonb,
        '${reducedSnapshotFingerprint}'
      )
    `),
    /exercicio fiscal informado/i,
  );
  await database.exec(`
    select source.stage_transferegov_snapshot(
      '00000000-0000-0000-0000-000000009003'::uuid,
      2025::smallint,
      '${JSON.stringify(reducedSnapshotRecords)}'::jsonb,
      '${reducedSnapshotFingerprint}'
    );
  `);
  let snapshotTransitions = await database.query(`
    select status, count(*)::integer as snapshots
    from source.transferegov_snapshot_manifests
    where fiscal_year = 2025
    group by status
    order by status
  `);
  assert.deepEqual(snapshotTransitions.rows, [
    { status: "active", snapshots: 1 },
    { status: "pending", snapshots: 1 },
  ]);
  assert.equal(
    (await database.query(
      "select count(*)::integer as records from territory.latest_transferegov_records",
    )).rows[0].records,
    10,
  );
  await database.exec(`
    update source.collection_runs
    set status = 'failed'
    where id = '00000000-0000-0000-0000-000000009003';
    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version, status
    ) values (
      '00000000-0000-0000-0000-000000009004',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'transferegov-parcerias'
         and endpoint.slug = 'propostas-barreiras'),
      'transferegov-snapshot-success-fixture', 'test/1', 'running'
    );
    select source.stage_transferegov_snapshot(
      '00000000-0000-0000-0000-000000009004'::uuid,
      2025::smallint,
      '${JSON.stringify(reducedSnapshotRecords)}'::jsonb,
      '${reducedSnapshotFingerprint}'
    );
    update source.collection_runs
    set status = 'succeeded'
    where id = '00000000-0000-0000-0000-000000009004';
  `);
  snapshotTransitions = await database.query(`
    select status, count(*)::integer as snapshots
    from source.transferegov_snapshot_manifests
    where fiscal_year = 2025
    group by status
    order by status
  `);
  assert.deepEqual(snapshotTransitions.rows, [
    { status: "abandoned", snapshots: 1 },
    { status: "active", snapshots: 1 },
    { status: "superseded", snapshots: 1 },
  ]);
  assert.equal(
    (await database.query(
      "select count(*)::integer as records from territory.latest_transferegov_records",
    )).rows[0].records,
    1,
  );

  await database.exec("set role anon");
  const anonCguDocumentLegislatureRanking = await database.query(`
    select legislature_number, author_name, representative_profile_url,
      committed_amount, effective_paid_amount, methodology_version
    from api.get_public_cgu_federal_amendment_legislature_ranking(10)
  `);
  assert.equal(anonCguDocumentLegislatureRanking.rows.length, 2);
  assert.equal(
    JSON.stringify(anonCguDocumentLegislatureRanking.rows).includes("cpf"),
    false,
  );
  await assert.rejects(
    database.query("select * from territory.parliamentary_transfers"),
    /permission denied/,
  );
  await assert.rejects(
    database.query("select * from political.parliamentary_transfer_author_crosswalk"),
    /permission denied/,
  );
  await assert.rejects(
    database.query("select * from political.legislative_terms"),
    /permission denied/,
  );
  await assert.rejects(
    database.query(
      "select * from political.parliamentary_author_code_crosswalk",
    ),
    /permission denied/,
  );
  await assert.rejects(
    database.query("select * from territory.bahia_special_transfer_payments"),
    /permission denied/,
  );
  await assert.rejects(
    database.query(
      "select * from territory.latest_bahia_special_transfer_annual_coverage",
    ),
    /permission denied/,
  );
  await assert.rejects(
    database.query(
      "select * from territory.cgu_federal_amendment_documents",
    ),
    /permission denied/,
  );
  await assert.rejects(
    database.query("select * from source.collection_partitions"),
    /permission denied/,
  );
  await assert.rejects(
    database.query(
      "select * from api.get_public_parliamentary_transfer_ranking('all', 2025::smallint, 50)",
    ),
    /author_scope deve ser person ou collective/,
  );
  await assert.rejects(
    database.query(
      "select * from api.get_public_parliamentary_legislature_rankings('municipal', null, 10)",
    ),
    /esfera legislativa deve ser federal ou state/,
  );
  await assert.rejects(
    database.query(
      "select * from api.get_public_parliamentary_legislature_rankings(null, null, 11)",
    ),
    /limite por legislatura deve estar entre 1 e 10/,
  );
  await assert.rejects(
    database.query(
      "select * from api.get_public_parliamentary_transfer_coverage(2025::smallint, 2024::smallint)",
    ),
    /intervalo fiscal invalido/,
  );
  await assert.rejects(
    database.query(
      "select * from api.get_public_federal_transfer_proposals(null, null, 201)",
    ),
    /limite de propostas invalido/,
  );
  await assert.rejects(
    database.query("select * from territory.federal_transfer_proposals"),
    /permission denied/,
  );
  await assert.rejects(
    database.query("select * from territory.federal_transfer_proposal_scope"),
    /permission denied/,
  );
  await assert.rejects(
    database.query("select * from territory.historical_parliamentary_amendments"),
    /permission denied/,
  );
  await assert.rejects(
    database.query("select * from territory.reconciled_parliamentary_transfers"),
    /permission denied/,
  );
  await assert.rejects(
    database.query("select * from territory.bahia_state_loa_amendments"),
    /permission denied/,
  );
  await assert.rejects(
    database.query(
      "select * from territory.bahia_state_loa_execution_reconciliation",
    ),
    /permission denied/,
  );
  await assert.rejects(
    database.query(
      "select * from territory.bahia_state_loa_execution_reconciliation_snapshot",
    ),
    /permission denied/,
  );
  await assert.rejects(
    database.query(
      "select * from territory.bahia_state_execution_annual_coverage_snapshot",
    ),
    /permission denied/,
  );
  await assert.rejects(
    database.query(
      "select territory.refresh_bahia_state_execution_annual_coverage_snapshot()",
    ),
    /permission denied/,
  );
  await assert.rejects(
    database.query(
      "select territory.refresh_bahia_state_loa_execution_reconciliation_snapshot()",
    ),
    /permission denied/,
  );
  await assert.rejects(
    database.query(
      "select * from api.get_public_bahia_state_loa_amendments(null, null, 201)",
    ),
    /limite de emendas estaduais da LOA invalido/,
  );
  await assert.rejects(
    database.query(
      "select * from api.get_public_bahia_state_loa_execution(2026::smallint, null, 201)",
    ),
    /limite da execucao estadual da LOA invalido/,
  );
  await assert.rejects(
    database.query(
      "select * from api.get_public_bahia_state_loa_study(2026::smallint, 26, 0)",
    ),
    /page_size do estudo estadual deve estar entre 1 e 25/,
  );
  await assert.rejects(
    database.query(
      "select * from api.get_public_bahia_state_loa_representative_contributions(201)",
    ),
    /limite das contribuicoes estaduais por representante invalido/,
  );
  await assert.rejects(
    database.query(
      "select * from api.get_public_historical_parliamentary_amendment_ranking('all', null, 50)",
    ),
    /author_scope deve ser person ou collective/,
  );
  await assert.rejects(
    database.query(
      "select * from api.get_public_historical_parliamentary_amendments(null, null, 201)",
    ),
    /limite de emendas historicas invalido/,
  );
  await assert.rejects(
    database.query(
      "select * from territory.cgu_federal_amendment_executions",
    ),
    /permission denied/,
  );
  await assert.rejects(
    database.query(
      "select * from territory.cgu_transferegov_amendment_links",
    ),
    /permission denied/,
  );
  await assert.rejects(
    database.query(
      "select * from territory.latest_cgu_federal_amendment_executions",
    ),
    /permission denied/,
  );
  await assert.rejects(
    database.query(
      "select * from api.get_public_cgu_federal_amendment_executions(null, null, 201)",
    ),
    /limite de emendas federais da CGU invalido/,
  );
  await assert.rejects(
    database.query(
      "select * from api.get_public_cgu_federal_amendment_ranking('all', null, 50)",
    ),
    /author_scope deve ser person ou collective/,
  );
  await database.exec("reset role");

  assert.equal(JSON.stringify(transfers.rows).includes("cpf"), false);
  assert.equal(JSON.stringify(transfers.rows).includes("solicitante"), false);
  assert.equal(JSON.stringify(historicalProposals.rows).includes("cnpj"), false);
  assert.equal(JSON.stringify(historicalProposals.rows).includes("conta"), false);
  assert.equal(JSON.stringify(historicalProposals.rows).includes("agencia"), false);
  assert.equal(JSON.stringify(historicalAmendments.rows).includes("cnpj"), false);
  assert.equal(JSON.stringify(historicalAmendments.rows).includes("ultimos_4"), false);
  console.log(
    "Emendas: autoria, estagios financeiros, deduplicacao e limites publicos verificados.",
  );
} finally {
  await database.close();
}
