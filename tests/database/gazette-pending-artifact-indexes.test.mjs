import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { PGlite } from "@electric-sql/pglite";

const migrationUrl = new URL(
  "../../supabase/migrations/20260902043000_optimize_pending_gazette_artifacts.sql",
  import.meta.url,
);

test("fila do Diario usa indices parciais em vez de varrer o acervo bruto", async () => {
  const database = new PGlite();
  await database.exec(`
    create schema raw;
    create table raw.raw_artifacts (
      id uuid primary key,
      sha256 text not null,
      metadata jsonb not null,
      created_at timestamptz not null
    );
    create table raw.raw_records (
      id uuid primary key,
      source_record_key text,
      record_type text not null,
      payload jsonb not null,
      collected_at timestamptz not null
    );
  `);
  await database.exec(await readFile(migrationUrl, "utf8"));
  await database.exec("set enable_seqscan = off");

  const directPlan = await database.query(`
    explain (format text)
    select id
    from raw.raw_artifacts
    where metadata ->> 'schema_name' = 'gazette-direct-edition'
      and coalesce(metadata ->> 'edition', '') ~ '^[0-9]+$'
      and coalesce(metadata ->> 'year', '') ~ '^[0-9]{4}$'
    order by (metadata ->> 'year')::integer desc,
      (metadata ->> 'edition')::integer desc,
      created_at desc
    limit 10
  `);
  const txtPlan = await database.query(`
    explain (format text)
    select id
    from raw.raw_artifacts
    where metadata ->> 'document_role' = 'txt'
      and metadata ? 'source_record_key'
    order by metadata ->> 'source_record_key', created_at desc, id desc
  `);
  const recordPlan = await database.query(`
    explain (format text)
    select payload
    from raw.raw_records
    where record_type = 'querido_diario_gazette'
      and source_record_key = 'gazette:4706'
    order by collected_at desc, id desc
    limit 1
  `);

  assert.match(
    JSON.stringify(directPlan.rows),
    /raw_artifacts_gazette_direct_pending_idx/,
  );
  assert.match(
    JSON.stringify(txtPlan.rows),
    /raw_artifacts_querido_diario_txt_pending_idx/,
  );
  assert.match(
    JSON.stringify(recordPlan.rows),
    /raw_records_querido_diario_latest_idx/,
  );

  await database.close();
});
