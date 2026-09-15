import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { PGlite } from "@electric-sql/pglite";

const source = await readFile(new URL(
  "../../workers/collectors/src/barreiras_collectors/persistence/postgres.py", import.meta.url,
), "utf8");
const method = source.slice(source.indexOf("    def pncp_pending_contratos("), source.indexOf("    def pncp_itens_com_resultado("));
const sqlLiteral = method.match(/connection\.execute\(\s*"""([\s\S]*?)"""/)?.[1];
assert.ok(sqlLiteral, "exercise the repository's actual static SQL");
// Decode the only escape in this static Python SQL literal (\\d -> \d).
const query = sqlLiteral.replace(/\\\\/g, "\\").replace(/%s/g, (() => {
  let parameter = 0;
  return () => `$${++parameter}`;
})());
const legacyOffsetQuery = /\boffset\b/i.test(query);
const key = (number) => `13654405000195-1-${String(number).padStart(6, "0")}/2023`;

async function fixture(t) {
  const db = new PGlite();
  t.after(() => db.close());
  await db.exec(`
    create schema raw;
    create table raw.raw_records (
      id bigint generated always as identity primary key,
      record_type text not null, payload jsonb not null, created_at timestamptz not null
    );
    create table raw.raw_artifacts (
      id bigint generated always as identity primary key, metadata jsonb not null
    );
  `);
  return db;
}

async function preserve(db, number, {
  control = key(number), published = "2021-01-01", created = "2026-09-01",
  sequence = number, year = 2023,
} = {}) {
  await db.query("insert into raw.raw_records (record_type, payload, created_at) values ('pncp_contratacao', $1, $2)", [JSON.stringify({
    numeroControlePNCP: control, anoCompra: year, sequencialCompra: sequence,
    dataPublicacaoPncp: published,
  }), created]);
}

async function snapshot(db, number, schema = "pncp-contratos-page") {
  await db.query("insert into raw.raw_artifacts (metadata) values ($1)", [JSON.stringify({
    schema_name: schema, cursor: { ano: 2023, sequencial: number },
  })]);
}

async function pending(db, {
  refreshDays = 120, limit = 50, afterControl = null, includeControls = [], legacyOffset = 0,
} = {}) {
  // RED can execute the original OFFSET query with its original parameter
  // shape. Once fixed, every call uses the new repository contract exactly.
  const params = legacyOffsetQuery
    ? [refreshDays, limit, legacyOffset]
    : [refreshDays, includeControls, afterControl, afterControl, limit];
  return (await db.query(query, params)).rows;
}

test("fila mutável de 120 controles não pula 50 após preservar o primeiro lote", async (t) => {
  const db = await fixture(t);
  for (let number = 1; number <= 120; number++) await preserve(db, number);
  const first = await pending(db);
  assert.deepEqual(first.map((row) => row.control), Array.from({ length: 50 }, (_, index) => key(index + 1)));
  for (const row of first) await snapshot(db, row.sequencial);
  const second = await pending(db, { afterControl: first.at(-1).control, legacyOffset: 50 });
  assert.deepEqual(second.map((row) => row.control), Array.from({ length: 50 }, (_, index) => key(index + 51)));
  for (const row of second) await snapshot(db, row.sequencial);
  const third = await pending(db, { afterControl: second.at(-1).control, legacyOffset: 100 });
  assert.deepEqual(third.map((row) => row.control), Array.from({ length: 20 }, (_, index) => key(index + 101)));
  const all = [...first, ...second, ...third].map((row) => row.control);
  assert.equal(new Set(all).size, 120);
  for (const row of third) await snapshot(db, row.sequencial);
  assert.deepEqual(await pending(db, { afterControl: third.at(-1).control }), []);
});

test("elegibilidade preserva recentes, faltantes e retomada explícita antes do cursor", async (t) => {
  const db = await fixture(t);
  const today = (await db.query("select current_date::text as day")).rows[0].day;
  await preserve(db, 1); await snapshot(db, 1);
  await preserve(db, 2, { published: today }); await snapshot(db, 2);
  await preserve(db, 3, { published: "data não informada" });
  await preserve(db, 4); await snapshot(db, 4, "outro-endpoint");
  await preserve(db, 5); await snapshot(db, 999);
  // A newer snapshot, not a historical recent observation, controls refresh.
  await preserve(db, 6, { published: today, created: "2026-08-01" });
  await preserve(db, 6, { published: "2021-01-01", created: "2026-09-01" });
  await snapshot(db, 6);
  const initial = await pending(db, { refreshDays: 0 });
  assert.deepEqual(initial.map((row) => row.control), [key(2), key(3), key(4), key(5)]);
  const forced = await pending(db, { refreshDays: 0, includeControls: [key(1), key(1), "unknown-control"] });
  assert.deepEqual(forced.map((row) => row.control), [key(1), key(2), key(3), key(4), key(5)]);
  const after = await pending(db, { refreshDays: 0, afterControl: key(2), includeControls: [key(1), key(6)] });
  assert.deepEqual(after.map((row) => row.control), [key(3), key(4), key(5), key(6)]);
});

test("ordem e cursor usam a mesma collation C e não inventam controles vazios", async (t) => {
  const db = await fixture(t);
  const controls = ["fixture-á", "fixture-a", "fixture-Z", "fixture-A"];
  for (const [index, control] of controls.entries()) await preserve(db, index + 1, { control });
  await preserve(db, 20, { control: null });
  await preserve(db, 21, { control: " " });
  const first = await pending(db, { limit: 2 });
  assert.deepEqual(first.map((row) => row.control), ["fixture-A", "fixture-Z"]);
  const next = await pending(db, { afterControl: "fixture-Z", limit: 2, legacyOffset: 2 });
  assert.deepEqual(next.map((row) => row.control), ["fixture-a", "fixture-á"]);
  const all = await pending(db, { limit: 20 });
  assert.deepEqual(all.map((row) => row.control), ["fixture-A", "fixture-Z", "fixture-a", "fixture-á"]);
  assert.match(query, /control collate "C" > .*collate "C"/);
  assert.match(query, /order by control collate "C"/);
});

test("snapshot mais recente da mesma chave usa id decrescente no empate de data", async (t) => {
  const db = await fixture(t);
  await preserve(db, 1, { sequence: 999, created: "2026-08-01" });
  await preserve(db, 1, { sequence: 998, created: "2026-09-01" });
  await preserve(db, 1, { sequence: 1, created: "2026-09-01" });
  const rows = await pending(db);
  assert.deepEqual(rows, [{ control: key(1), ano: 2023, sequencial: 1 }]);
});
