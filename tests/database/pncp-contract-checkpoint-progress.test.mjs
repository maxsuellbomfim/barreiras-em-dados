import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { PGlite } from "@electric-sql/pglite";

const source = await readFile(new URL(
  "../../workers/collectors/src/barreiras_collectors/persistence/postgres.py", import.meta.url,
), "utf8");
const method = source.slice(source.indexOf("    def pncp_contract_checkpoint_progress("), source.indexOf("    def pncp_itens_com_resultado("));
const queries = [...method.matchAll(/connection\.execute\(\s*"""([\s\S]*?)"""/g)].map((match) => {
  let parameter = 0;
  return match[1].replace(/%s/g, () => `$${++parameter}`);
});
assert.equal(queries.length, 2, "exercise both actual static repository statements");
const uuid = (number) => `00000000-0000-4000-8000-${String(number).padStart(12, "0")}`;
const endpoint = uuid(101);

async function fixture(t) {
  const db = new PGlite();
  t.after(() => db.close());
  await db.exec(`
    create schema source;
    create table source.data_sources (id uuid primary key, slug text, status text);
    create table source.source_endpoints (
      id uuid primary key, data_source_id uuid references source.data_sources,
      slug text, enabled boolean
    );
    create table source.collection_runs (
      id uuid primary key, source_endpoint_id uuid references source.source_endpoints,
      status text, cursor_after jsonb default '{"old":true}',
      collection_window_start date, collection_window_end date,
      completed_at timestamptz, heartbeat_at timestamptz default '2026-09-01',
      metrics jsonb default '{"untouched":true}', error_detail text default 'untouched'
    );
    create table source.collection_partitions (
      source_endpoint_id uuid references source.source_endpoints,
      partition_key text, period_start date not null, period_end date not null,
      status text, observed_records int, collection_run_id uuid references source.collection_runs,
      checkpoint jsonb check (jsonb_typeof(checkpoint) = 'object'),
      last_attempted_at timestamptz, completed_at timestamptz, block_reason text,
      unique (source_endpoint_id, partition_key)
    );
    create table source.collection_failures (id int, status text);
    insert into source.collection_failures values (1, 'retry_scheduled');
    insert into source.data_sources values
      ('${uuid(201)}', 'pncp', 'active'), ('${uuid(202)}', 'other', 'active'),
      ('${uuid(203)}', 'pncp', 'inactive');
    insert into source.source_endpoints values
      ('${endpoint}', '${uuid(201)}', 'contratos-api', true),
      ('${uuid(102)}', '${uuid(201)}', 'itens-api', true),
      ('${uuid(103)}', '${uuid(202)}', 'contratos-api', true),
      ('${uuid(104)}', '${uuid(201)}', 'contratos-api', false),
      ('${uuid(105)}', '${uuid(203)}', 'contratos-api', true);
  `);
  for (const [id, endpointId, status, completedAt] of [
    [1, 101, "running", null], [2, 101, "succeeded", "2026-09-14"],
    [3, 102, "running", null], [4, 103, "running", null],
    [5, 101, "running", "2026-09-14"], [6, 104, "running", null],
    [7, 105, "running", null],
  ]) {
    await db.query(`insert into source.collection_runs (
      id, source_endpoint_id, status, completed_at, collection_window_start, collection_window_end
    ) values ($1, $2, $3, $4, '2026-09-07', '2026-09-14')`, [uuid(id), uuid(endpointId), status, completedAt]);
  }
  return db;
}

async function reserve(db, runId, checkpoint) {
  // Match the repository's transaction and fail-closed guard, without a network
  // driver. The SQL itself is extracted above, never reconstructed here.
  return db.transaction(async (tx) => {
    const { rows } = await tx.query(queries[0], [JSON.stringify(checkpoint), runId]);
    if (rows.length !== 1) throw new Error("run outside scope");
    const row = rows[0];
    await tx.query(queries[1], [row.endpoint_id, row.period_start, row.period_end, runId, JSON.stringify(checkpoint)]);
  });
}

test("reserva SQL troca conclusão antiga por parcial e mantém todos os controles, run e falhas", async (t) => {
  const db = await fixture(t);
  await db.query(`insert into source.collection_partitions (
    source_endpoint_id, partition_key, period_start, period_end, status,
    observed_records, collection_run_id, checkpoint, completed_at
  ) values ($1, 'backlog:contratos', '2026-01-01', '2026-01-31', 'complete',
    99, $2, '{"old":true}', '2026-02-01')`, [endpoint, uuid(2)]);
  const checkpoint = {
    cursor_version: 2, next_after_control: null, pending_truncated: true,
    retry_controls: Array.from({ length: 150 }, (_, i) => `13654405000195-1-${String(i + 1).padStart(6, "0")}/2023`),
    contract_pages_truncated_controls: [],
  };
  await reserve(db, uuid(1), checkpoint);
  const [run] = (await db.query("select * from source.collection_runs where id = $1", [uuid(1)])).rows;
  assert.equal(run.status, "running");
  assert.equal(run.completed_at, null);
  assert.deepEqual(run.cursor_after, checkpoint);
  assert.deepEqual(run.metrics, { untouched: true });
  assert.equal(run.error_detail, "untouched");
  assert.ok(run.heartbeat_at > new Date("2026-09-01"));
  const [partition] = (await db.query("select * from source.collection_partitions")).rows;
  assert.equal(partition.source_endpoint_id, endpoint);
  assert.equal(partition.partition_key, "backlog:contratos");
  assert.equal(partition.period_start.toISOString().slice(0, 10), "2026-09-07");
  assert.equal(partition.period_end.toISOString().slice(0, 10), "2026-09-14");
  assert.equal(partition.collection_run_id, uuid(1));
  assert.equal(partition.status, "partial");
  assert.equal(partition.observed_records, 0);
  assert.equal(partition.completed_at, null);
  assert.equal(partition.block_reason, null);
  assert.deepEqual(partition.checkpoint, checkpoint);
  assert.deepEqual((await db.query("select * from source.collection_failures")).rows, [{ id: 1, status: "retry_scheduled" }]);
});

test("guardas SQL rejeitam run ausente, terminal, outra fonte ou endpoint, concluído e desativados", async (t) => {
  const db = await fixture(t);
  const before = (await db.query("select * from source.collection_runs order by id")).rows;
  for (const id of [2, 3, 4, 5, 6, 7, 999]) {
    await assert.rejects(reserve(db, uuid(id), { retry_controls: ["pending"] }), /run outside scope/);
  }
  assert.deepEqual((await db.query("select * from source.collection_runs order by id")).rows, before);
  assert.deepEqual((await db.query("select * from source.collection_partitions")).rows, []);
});

test("falha no upsert reverte também cursor e heartbeat do run na transação real", async (t) => {
  const db = await fixture(t);
  await db.exec("alter table source.collection_partitions add constraint deliberate_failure check (checkpoint ->> 'reject' is null)");
  const before = (await db.query("select * from source.collection_runs where id = $1", [uuid(1)])).rows;
  await assert.rejects(reserve(db, uuid(1), { reject: true, retry_controls: ["pending"] }), /deliberate_failure/);
  assert.deepEqual((await db.query("select * from source.collection_runs where id = $1", [uuid(1)])).rows, before);
  assert.deepEqual((await db.query("select * from source.collection_partitions")).rows, []);
});
