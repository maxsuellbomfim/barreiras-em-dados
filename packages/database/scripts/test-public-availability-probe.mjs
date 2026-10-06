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
assert.ok(migrationNames.some((name) => name.endsWith("_public_availability_pg_cron_probe.sql")));

const sha = (text) => createHash("sha256").update(text).digest("hex");
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
    await database.exec(await readFile(fileURLToPath(new URL(name, migrationsUrl)), "utf8"));
  }

  const html = (path) => ({
    content_kind: "html", status_code: 200, content_type: "text/html; charset=utf-8",
    body: `<!DOCTYPE html><html lang="pt-BR"><title>${path} | Barreiras 360</title></html>`,
    latency_ms: 120,
  });
  const healthBody = {
    status: "ok", service: "barreiras-em-dados-web", stage: "pre-launch", httpStatus: 200,
    checks: [
      { key: "diary", label: "Diário", status: "available", records: 1 },
      { key: "finance", label: "Finanças", status: "available", records: 70 },
      { key: "representatives", label: "Representação", status: "available", records: 136 },
    ],
  };
  const health = (body = healthBody, status = 200) => ({
    content_kind: "health_json", status_code: status, content_type: "application/json",
    body: JSON.stringify(body), latency_ms: 300,
  });
  const slugs = ["home", "status", "official-diary", "finance", "procurement", "resources",
    "representatives"];
  const allValid = () => [
    ...slugs.map((slug) => ({ target_slug: slug, ...html(slug) })),
    { target_slug: "health-api", ...health() },
  ];

  const healthStatus = async (code, type, body) => (await database.query(
    "select source.public_availability_health_status_v1($1, $2, $3) as s", [code, type, body],
  )).rows[0].s;
  assert.equal(await healthStatus(200, "application/json", JSON.stringify(healthBody)), "ok");
  const degraded = structuredClone(healthBody);
  degraded.status = "degraded";
  degraded.checks[1] = { key: "finance", label: "F", status: "unavailable", records: null };
  assert.equal(await healthStatus(200, "application/json", JSON.stringify(degraded)), "degraded");
  const lying = structuredClone(degraded);
  lying.status = "ok";
  assert.equal(await healthStatus(200, "application/json", JSON.stringify(lying)), null,
    "status declarado precisa bater com os checks");
  assert.equal(await healthStatus(503, "application/json", JSON.stringify(healthBody)), null,
    "httpStatus do corpo precisa bater com o HTTP");
  assert.equal(await healthStatus(200, "text/html", JSON.stringify(healthBody)), null);
  assert.equal(await healthStatus(200, "application/json", "{nao e json"), null);
  const twoKeys = structuredClone(healthBody);
  twoKeys.checks[2].key = "diary";
  assert.equal(await healthStatus(200, "application/json", JSON.stringify(twoKeys)), null);
  const emptyWithRecords = structuredClone(healthBody);
  emptyWithRecords.status = "degraded";
  emptyWithRecords.checks[0] = { key: "diary", status: "empty", records: 3 };
  assert.equal(await healthStatus(200, "application/json", JSON.stringify(emptyWithRecords)), null);

  const endpoint = (await database.query(`select endpoint.id from source.source_endpoints endpoint
    join source.data_sources source on source.id = endpoint.data_source_id
    where source.slug = 'barreiras-360' and endpoint.slug = 'critical-public-pages'`)).rows[0].id;
  let runCount = 0;
  const startRun = async (startedAt) => {
    runCount += 1;
    return (await database.query(`insert into source.collection_runs (source_endpoint_id,
      idempotency_key, collector_version, parser_version, status, attempt_count, started_at,
      heartbeat_at, metrics) values ($1, $2, 'public-availability-probe-pg/1.0.0',
      'public-availability-contract/1.0.0', 'running', 1, $3, $3,
      '{"control_plane":true,"execution_origin":"supabase_pg_cron","workflow_event":"schedule","target_count":8}')
      returning id`, [endpoint, `public-availability:pg-cron:test-${runCount}`, startedAt])).rows[0].id;
  };
  const record = async (run, responses) => (await database.query(
    "select source.record_public_availability_probe($1, $2::jsonb) as r",
    [run, JSON.stringify(responses)])).rows[0].r;
  const runRow = async (run) => (await database.query(
    "select status, error_code, metrics from source.collection_runs where id = $1", [run])).rows[0];

  const good = await startRun("2026-10-01T15:17:00Z");
  assert.equal(await record(good, allValid()), "complete");
  const goodRow = await runRow(good);
  assert.equal(goodRow.status, "succeeded");
  assert.equal(goodRow.error_code, null);
  assert.deepEqual(
    [goodRow.metrics.targets_checked, goodRow.metrics.http_5xx_count,
      goodRow.metrics.transport_failures, goodRow.metrics.contract_failures,
      goodRow.metrics.health_status, goodRow.metrics.collection_outcome,
      goodRow.metrics.maximum_latency_ms, goodRow.metrics.execution_origin],
    [8, 0, 0, 0, "ok", "complete", 300, "supabase_pg_cron"],
  );
  await assert.rejects(database.query("select source.record_public_availability_probe($1, '[]')",
    [good]), /inexistente ou já encerrada/);

  const bad = await startRun("2026-10-01T16:17:00Z");
  const broken = allValid();
  broken[0] = { target_slug: "home", ...html("home"), status_code: 500 };
  broken[1] = { target_slug: "status", transport_failure: true };
  broken[2] = { target_slug: "official-diary", ...html("x"), body: "<html>outro site</html>" };
  assert.equal(await record(bad, broken), "partial");
  const badRow = await runRow(bad);
  assert.equal(badRow.status, "partial");
  assert.equal(badRow.error_code, "PublicAvailabilityGateFailure");
  assert.deepEqual(
    [badRow.metrics.http_5xx_count, badRow.metrics.http_non_2xx_count,
      badRow.metrics.transport_failures, badRow.metrics.contract_failures],
    [1, 1, 1, 1],
  );
  const short = await startRun("2026-10-01T17:17:00Z");
  assert.equal(await record(short, allValid().slice(0, 7)), "partial",
    "resposta ausente nunca vira sucesso");

  // 20 sondagens válidas do banco num dia encerrado fazem o dia passar no gate.
  for (let hour = 0; hour < 20; hour += 1) {
    const run = await startRun(`2026-10-03T${String(hour + 3).padStart(2, "0")}:17:00Z`);
    await record(run, allValid());
  }
  await database.exec(`
    update source.source_endpoints set created_at = '2026-09-01' where id = '${endpoint}';
    insert into audit.reviewer_identities (auth_user_id, display_name, status, activated_at)
    values ('1575c740-fcff-4b1a-89a9-e8e5a314880a', 'Revisor de Teste', 'active',
      statement_timestamp());
    select set_config('request.jwt.claim.sub', '1575c740-fcff-4b1a-89a9-e8e5a314880a', false);
  `);
  const gate = (await database.query(`select availability_daily_history as h
    from api.get_collection_health_v8(500, '2026-10-04')
    where source_slug = 'barreiras-360' and endpoint_slug = 'critical-public-pages'`)).rows[0].h;
  const day = gate.find((item) => item.day === "2026-10-03");
  assert.deepEqual([day.state, day.runs_observed, day.valid_runs], ["passed", 20, 20]);
  const failedDay = gate.find((item) => item.day === "2026-10-01");
  assert.equal(failedDay.state, "failed", "sondagem partial derruba o dia");
  assert.equal((await database.query(`select methodology_version from
    api.get_collection_health_v8(500, '2026-10-04') limit 1`)).rows[0].methodology_version,
    "collection-health/1.9.0");

  const access = await database.query(`select
    has_function_privilege('anon', 'source.record_public_availability_probe(uuid, jsonb)', 'EXECUTE') as anon,
    has_table_privilege('anon', 'source.public_availability_probe_requests', 'SELECT') as anon_read`);
  assert.deepEqual(access.rows[0], { anon: false, anon_read: false });
} finally {
  await database.close();
}

console.log("public availability probe migration test passed");
