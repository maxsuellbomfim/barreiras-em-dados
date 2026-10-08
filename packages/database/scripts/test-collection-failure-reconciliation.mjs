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
assert.ok(
  migrationNames.some((name) => name.endsWith("_collection_failure_reconciliation.sql")),
  "migration de reconciliação de falhas ausente",
);

const database = new PGlite({ extensions: { pgcrypto, pg_trgm } });
try {
  await database.exec(`
    create role anon nologin;
    create role authenticated nologin;
    create role authenticator nologin;
    create role service_role nologin bypassrls;
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
      id text primary key, name text not null, public boolean not null default false,
      file_size_limit bigint, allowed_mime_types text[]
    );
    create table storage.objects (
      id uuid primary key, bucket_id text not null references storage.buckets(id),
      name text not null, unique(bucket_id, name)
    );
    alter table storage.objects enable row level security;
    grant usage on schema storage to authenticated;
    grant select, insert, update, delete on storage.objects to authenticated;
  `);
  for (const name of migrationNames) {
    const migration = await readFile(fileURLToPath(new URL(name, migrationsUrl)), "utf8");
    await database.exec(migration);
  }

  // As migrations só semeiam endpoints quando a fonte já existe.
  await database.exec(`
    insert into source.data_sources (slug, name, authority_level, homepage_url)
    values ('querido-diario', 'Querido Diário', 'secondary', 'https://queridodiario.ok.org.br'),
           ('barreiras-diario-oficial', 'Diário Oficial de Barreiras', 'official', 'https://barreiras.ba.gov.br')
    on conflict (slug) do nothing;
    insert into source.source_endpoints (data_source_id, slug, endpoint_kind, base_url)
    select d.id, e.slug, 'api', 'https://example.org'
    from (values ('querido-diario', 'gazettes-api'),
                 ('barreiras-diario-oficial', 'catalogo-publicacoes')) as e(source, slug)
    join source.data_sources d on d.slug = e.source
    where not exists (
      select 1 from source.source_endpoints x where x.data_source_id = d.id and x.slug = e.slug
    );
  `);
  const endpoints = await database.query(`
    select
      (select e.id from source.source_endpoints e join source.data_sources d on d.id = e.data_source_id
        where d.slug = 'querido-diario' and e.slug = 'gazettes-api') as qd,
      (select e.id from source.source_endpoints e join source.data_sources d on d.id = e.data_source_id
        where d.slug = 'barreiras-diario-oficial' and e.slug = 'catalogo-publicacoes') as catalog
  `);
  const { qd, catalog } = endpoints.rows[0];
  assert.ok(qd && catalog, "endpoints semeados ausentes");

  let sequence = 0;
  const run = (endpoint, status, at, version = "test/1") => {
    sequence += 1;
    const id = `00000000-0000-4000-9000-${String(sequence).padStart(12, "0")}`;
    return {
      id,
      sql: `insert into source.collection_runs (id, source_endpoint_id, idempotency_key,
        collector_version, parser_version, status, attempt_count, started_at, completed_at)
        values ('${id}', '${endpoint}', '${String(sequence).padStart(64, "a")}', '${version}',
        'parser/1', '${status}', 1, '${at}', '${at}');`,
    };
  };
  // Erro de invocação: o coletor recusou os próprios argumentos, sem chamar a fonte.
  const valueError = (endpoint, runId, key, at) =>
    `insert into source.collection_failures (collection_run_id, source_endpoint_id, partition_key,
      status, error_type, error_detail, attempt_count, retryable, next_retry_at, failed_at)
      values ('${runId}', '${endpoint}', '${key}', 'open', 'ValueError',
      'limit deve estar entre 1 e 5.', 1, false, null, '${at}');`;
  const partition = (endpoint, key, start, end, status, runId, at) =>
    `insert into source.collection_partitions (source_endpoint_id, partition_key, period_start,
      period_end, status, observed_records, collection_run_id, last_attempted_at, completed_at)
      values ('${endpoint}', '${key}', '${start}', '${end}', '${status}', 0, '${runId}', '${at}',
      ${status === "failed" ? "null" : `'${at}'`})
      on conflict (source_endpoint_id, partition_key) do update
      set status = excluded.status, collection_run_id = excluded.collection_run_id,
          completed_at = excluded.completed_at;`;
  const failure = (endpoint, runId, key, at, status = "retry_scheduled") =>
    `insert into source.collection_failures (collection_run_id, source_endpoint_id, partition_key,
      status, error_type, error_detail, attempt_count, retryable, next_retry_at, failed_at)
      values ('${runId}', '${endpoint}', '${key}', '${status}', 'Teste', 'Falha de teste.', 1,
      ${status === "retry_scheduled"}, ${status === "retry_scheduled" ? `'${at}'::timestamptz + interval '1 hour'` : "null"}, '${at}');`;

  const statements = [];
  const add = (built) => {
    statements.push(built.sql);
    return built.id;
  };

  // Regra 1: a mesma partição volta completa depois da falha.
  const sameFailed = add(run(catalog, "retry_scheduled", "2026-09-01T10:00:00Z"));
  statements.push(partition(catalog, "catalog-window:2026-08-01:2026-08-07", "2026-08-01", "2026-08-07", "failed", sameFailed, "2026-09-01T10:00:00Z"));
  statements.push(failure(catalog, sameFailed, "catalog-window:2026-08-01:2026-08-07", "2026-09-01T10:00:00Z"));
  const sameOk = add(run(catalog, "succeeded", "2026-09-02T10:00:00Z"));
  statements.push(partition(catalog, "catalog-window:2026-08-01:2026-08-07", "2026-08-01", "2026-08-07", "complete", sameOk, "2026-09-02T10:00:00Z"));

  // Regra 2: retrato datado substituído por outro posterior bem-sucedido.
  const snapFailed = add(run(catalog, "retry_scheduled", "2026-09-03T10:00:00Z"));
  statements.push(partition(catalog, "catalog-snapshot:2026-09-03", "2026-09-03", "2026-09-03", "failed", snapFailed, "2026-09-03T10:00:00Z"));
  statements.push(failure(catalog, snapFailed, "catalog-snapshot:2026-09-03", "2026-09-03T10:00:00Z"));
  const snapOk = add(run(catalog, "succeeded", "2026-09-04T10:00:00Z"));
  statements.push(partition(catalog, "catalog-snapshot:2026-09-04", "2026-09-04", "2026-09-04", "complete", snapOk, "2026-09-04T10:00:00Z"));

  // Regra 3: semana do Querido Diário coberta pelo catálogo oficial.
  const qdFailed = add(run(qd, "retry_scheduled", "2026-09-05T10:00:00Z"));
  statements.push(failure(qd, qdFailed, "published:2026-08-02:2026-08-06", "2026-09-05T10:00:00Z"));
  const qdPermanent = add(run(qd, "failed", "2026-09-05T11:00:00Z"));
  statements.push(failure(qd, qdPermanent, "published:2026-08-03:2026-08-05", "2026-09-05T11:00:00Z", "open"));

  // Continuam abertas: semana fora do catálogo, retrato só com falhas
  // posteriores e partição que voltou apenas parcial.
  const qdUncovered = add(run(qd, "retry_scheduled", "2026-09-06T10:00:00Z"));
  statements.push(failure(qd, qdUncovered, "published:2026-07-01:2026-07-07", "2026-09-06T10:00:00Z"));
  const archiveFailed = add(run(qd, "retry_scheduled", "2026-09-07T10:00:00Z"));
  statements.push(partition(qd, "archive-snapshot:2026-09-07", "2026-09-07", "2026-09-07", "failed", archiveFailed, "2026-09-07T10:00:00Z"));
  statements.push(failure(qd, archiveFailed, "archive-snapshot:2026-09-07", "2026-09-07T10:00:00Z"));
  const partialRun = add(run(catalog, "partial", "2026-09-08T10:00:00Z"));
  statements.push(partition(catalog, "backlog:catalogo", "2026-09-08", "2026-09-08", "partial", partialRun, "2026-09-08T10:00:00Z"));
  statements.push(failure(catalog, partialRun, "backlog:catalogo", "2026-09-08T10:00:00Z"));
  // Retrato bem-sucedido anterior à falha não a substitui.
  const oldSnap = add(run(catalog, "succeeded", "2026-08-01T10:00:00Z"));
  statements.push(partition(catalog, "catalog-snapshot:2026-08-01", "2026-08-01", "2026-08-01", "complete", oldSnap, "2026-08-01T10:00:00Z"));
  const lateSnapFailed = add(run(catalog, "retry_scheduled", "2026-09-20T10:00:00Z"));
  statements.push(failure(catalog, lateSnapFailed, "catalog-snapshot:2026-09-20", "2026-09-20T10:00:00Z"));

  // Regra 4: janela coberta por outra janela maior do mesmo endpoint,
  // coletada depois com sucesso.
  const windowFailed = add(run(qd, "retry_scheduled", "2026-09-09T10:00:00Z"));
  statements.push(partition(qd, "published:2026-06-10:2026-06-12", "2026-06-10", "2026-06-12", "failed", windowFailed, "2026-09-09T10:00:00Z"));
  statements.push(failure(qd, windowFailed, "published:2026-06-10:2026-06-12", "2026-09-09T10:00:00Z"));
  const windowOk = add(run(qd, "succeeded", "2026-09-10T10:00:00Z"));
  statements.push(partition(qd, "published:2026-06-01:2026-06-30", "2026-06-01", "2026-06-30", "complete", windowOk, "2026-09-10T10:00:00Z"));

  // Regra 5: erro de invocação de uma versão do coletor já substituída por
  // execução posterior (parcial basta) de versão maior no mesmo endpoint.
  const oldVersionFailed = add(run(catalog, "failed", "2026-09-11T10:00:00Z", "tcm-docs/1.0.0"));
  statements.push(valueError(catalog, oldVersionFailed, "documents:2021-01", "2026-09-11T10:00:00Z"));
  const newVersionRun = add(run(catalog, "partial", "2026-09-12T10:00:00Z", "tcm-docs/1.1.0"));
  // Mesma versão depois, ou outro coletor, não resolve.
  const sameVersionFailed = add(run(qd, "failed", "2026-09-13T10:00:00Z", "qd-weeks/2.0.0"));
  statements.push(valueError(qd, sameVersionFailed, "published:2026-05-01:2026-05-07", "2026-09-13T10:00:00Z"));
  add(run(qd, "succeeded", "2026-09-14T10:00:00Z", "qd-weeks/2.0.0"));
  add(run(qd, "succeeded", "2026-09-14T11:00:00Z", "other-collector/9.0.0"));

  await database.exec(statements.join("\n"));

  const privileges = await database.query(`
    select
      has_function_privilege('collector_worker', 'source.reconcile_collection_failures()', 'EXECUTE') as worker,
      has_function_privilege('anon', 'source.reconcile_collection_failures()', 'EXECUTE') as anon,
      has_function_privilege('authenticated', 'source.reconcile_collection_failures()', 'EXECUTE') as authenticated
  `);
  assert.deepEqual(privileges.rows[0], { worker: true, anon: false, authenticated: false });

  const first = await database.query("select * from source.reconcile_collection_failures()");
  assert.deepEqual(
    Object.fromEntries(first.rows.map((row) => [row.rule, row.resolved_count])),
    {
      same_partition_recovered: 1,
      snapshot_superseded: 1,
      covered_by_primary_source: 2,
      covered_by_later_window: 1,
      collector_version_superseded: 1,
    },
  );

  const closed = await database.query(`
    select collection_run_id::text as failed_run, resolution_run_id::text as evidence_run,
      resolution_reason, next_retry_at
    from source.collection_failures where status = 'resolved' order by collection_run_id
  `);
  assert.deepEqual(
    closed.rows.map((row) => [row.failed_run, row.evidence_run, row.resolution_reason, row.next_retry_at]),
    [
      [sameFailed, sameOk, "same_partition_recovered", null],
      [snapFailed, snapOk, "snapshot_superseded", null],
      [qdFailed, sameOk, "covered_by_primary_source", null],
      [qdPermanent, sameOk, "covered_by_primary_source", null],
      [windowFailed, windowOk, "covered_by_later_window", null],
      [oldVersionFailed, newVersionRun, "collector_version_superseded", null],
    ],
  );

  const stillOpen = await database.query(`
    select collection_run_id::text as run from source.collection_failures
    where status <> 'resolved' order by collection_run_id
  `);
  assert.deepEqual(
    stillOpen.rows.map((row) => row.run),
    [qdUncovered, archiveFailed, partialRun, lateSnapFailed, sameVersionFailed],
  );

  const audit = await database.query(`
    select actor_type, action, after_state, metadata from audit.audit_events
    where action = 'collection_failures.reconciled'
  `);
  assert.equal(audit.rows.length, 1);
  assert.equal(audit.rows[0].actor_type, "worker");
  assert.equal(audit.rows[0].metadata.version, "collection-failure-reconciliation/1.2.0");
  assert.equal(audit.rows[0].after_state.covered_by_later_window, 1);
  assert.equal(audit.rows[0].after_state.collector_version_superseded, 1);
  assert.equal(audit.rows[0].metadata.records_deleted, false);
  assert.equal(audit.rows[0].after_state.covered_by_primary_source, 2);

  // Idempotente: a segunda rodada não fecha nada nem audita de novo.
  const second = await database.query("select sum(resolved_count)::integer as total from source.reconcile_collection_failures()");
  assert.equal(second.rows[0].total, 0);
  const auditAgain = await database.query(`
    select count(*)::integer as count from audit.audit_events where action = 'collection_failures.reconciled'
  `);
  assert.equal(auditAgain.rows[0].count, 1);

  await assert.rejects(
    database.exec(`update source.collection_failures set resolution_reason = 'snapshot_superseded'
      where collection_run_id = '${qdUncovered}'`),
    /collection_failures_resolution_reason_check/,
  );

  // Execuções órfãs: só as sem sinal de vida há mais de 24 h são encerradas.
  await database.exec(`
    insert into source.collection_runs (id, source_endpoint_id, idempotency_key,
      collector_version, parser_version, status, attempt_count, started_at, heartbeat_at)
    values
      ('00000000-0000-4000-9000-00000000aa01', '${catalog}', '${"c".repeat(64)}',
       'test/1', 'parser/1', 'running', 1, now() - interval '2 days', now() - interval '2 days'),
      ('00000000-0000-4000-9000-00000000aa02', '${catalog}', '${"d".repeat(64)}',
       'test/1', 'parser/1', 'running', 1, now() - interval '2 hours', now() - interval '2 hours');
  `);
  const orphansClosed = await database.query("select source.close_orphaned_collection_runs() as n");
  assert.equal(orphansClosed.rows[0].n, 1);
  const runStates = await database.query(`
    select id::text as id, status, error_code from source.collection_runs
    where id in ('00000000-0000-4000-9000-00000000aa01', '00000000-0000-4000-9000-00000000aa02')
    order by id`);
  assert.deepEqual(runStates.rows, [
    { id: "00000000-0000-4000-9000-00000000aa01", status: "cancelled", error_code: "OrphanedRun" },
    { id: "00000000-0000-4000-9000-00000000aa02", status: "running", error_code: null },
  ]);
  assert.equal(
    (await database.query("select source.close_orphaned_collection_runs() as n")).rows[0].n,
    0,
  );
  const orphanAudit = await database.query(`
    select after_state, metadata from audit.audit_events
    where action = 'collection_runs.orphans_closed'`);
  assert.equal(orphanAudit.rows.length, 1);
  assert.equal(orphanAudit.rows[0].after_state.count, 1);
  assert.equal(orphanAudit.rows[0].metadata.version, "orphaned-collection-runs/1.0.0");
  const workerCanClose = await database.query(`select has_function_privilege(
    'collector_worker', 'source.close_orphaned_collection_runs()', 'EXECUTE') as ok`);
  assert.equal(workerCanClose.rows[0].ok, true);
} finally {
  await database.close();
}

console.log("collection failure reconciliation migration test passed");
