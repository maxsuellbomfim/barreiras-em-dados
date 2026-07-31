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
  for (const migration of migrations) {
    await database.exec(migration);
  }

  const relations = await database.query(`
    select count(*)::integer as count
    from pg_catalog.pg_tables
    where schemaname in (
      'source', 'raw', 'org', 'hr', 'procurement', 'finance',
      'evidence', 'analysis', 'editorial', 'audit'
    )
  `);
  assert.equal(relations.rows[0].count, 39);

  const originColumns = await database.query(`
    select count(*)::integer as count
    from information_schema.columns
    where column_name = 'origin_raw_record_id'
      and table_schema in ('org', 'hr', 'procurement', 'finance', 'analysis', 'editorial')
  `);
  assert.equal(originColumns.rows[0].count, 25);

  const nullableOrigins = await database.query(`
    select count(*)::integer as count
    from information_schema.columns
    where column_name = 'origin_raw_record_id'
      and is_nullable <> 'NO'
  `);
  assert.equal(nullableOrigins.rows[0].count, 0);

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

  await database.exec(`
    create schema storage;
    create table storage.buckets (
      id text primary key,
      name text not null,
      public boolean not null default false,
      file_size_limit bigint,
      allowed_mime_types text[]
    );
  `);
  await database.exec(seed);
  await database.exec(seed);

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
      byte_size, sha256, object_key, collector_version
    ) values (
      '${artifactId}', '${runId}', '${endpointId}', '${"2".repeat(64)}',
      'http_response', 'https://api.queridodiario.ok.org.br/gazettes',
      now(), 200, 'application/json', 2, '${"3".repeat(64)}',
      'querido-diario/gazettes/sha256/33/${"3".repeat(64)}.json',
      'test/1'
    );

    insert into raw.raw_records (
      raw_artifact_id, source_record_key, record_type, record_index, payload,
      payload_sha256, parser_version, idempotency_key, collected_at
    ) values (
      '${artifactId}', 'gazette:1', 'querido_diario_gazette', 0, '{"v":1}',
      '${"4".repeat(64)}', 'parser/1', '${"5".repeat(64)}', now()
    ) on conflict (idempotency_key) do nothing;

    insert into raw.raw_records (
      raw_artifact_id, source_record_key, record_type, record_index, payload,
      payload_sha256, parser_version, idempotency_key, collected_at
    ) values (
      '${artifactId}', 'gazette:1', 'querido_diario_gazette', 0, '{"v":2}',
      '${"6".repeat(64)}', 'parser/2', '${"7".repeat(64)}', now()
    ) on conflict (idempotency_key) do nothing;

    insert into raw.raw_records (
      raw_artifact_id, source_record_key, record_type, record_index, payload,
      payload_sha256, parser_version, idempotency_key, collected_at
    ) values (
      '${artifactId}', 'gazette:1', 'querido_diario_gazette', 0, '{"v":2}',
      '${"6".repeat(64)}', 'parser/2', '${"7".repeat(64)}', now()
    ) on conflict (idempotency_key) do nothing;
  `);
  const replay = await database.query(`
    select
      (select count(*)::integer from raw.raw_artifacts) as artifacts,
      (select count(*)::integer from raw.raw_records) as records
  `);
  assert.deepEqual(replay.rows[0], { artifacts: 1, records: 2 });

  await assert.rejects(
    database.exec(`
      update raw.raw_artifacts
      set content_type = 'text/plain'
      where id = '${artifactId}'
    `),
    /immutable relation/,
  );

  const seeded = await database.query(`
    select
      (select count(*)::integer from source.data_sources) as sources,
      (select count(*)::integer from source.source_endpoints) as endpoints,
      (select count(*)::integer from storage.buckets where not public) as private_buckets
  `);
  assert.deepEqual(seeded.rows[0], {
    sources: 3,
    endpoints: 3,
    private_buckets: 1,
  });

  console.log(
    "Migration e seed executados em PostgreSQL embutido: 39 tabelas, origem obrigatória.",
  );
} finally {
  await database.close();
}
