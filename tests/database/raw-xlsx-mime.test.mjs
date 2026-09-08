import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { PGlite } from "@electric-sql/pglite";

const migrationUrl = new URL(
  "../../supabase/migrations/20260908200000_allow_raw_xlsx_artifacts.sql",
  import.meta.url,
);

const XLSX_MIME =
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

test("habilita XLSX no bucket privado sem remover tipos existentes ou duplicar a auditoria", async () => {
  const database = new PGlite();
  await database.exec(`
    create schema storage;
    create schema audit;
    create table storage.buckets (
      id text primary key,
      public boolean not null default false,
      allowed_mime_types text[]
    );
    create table audit.audit_events (
      id bigint generated always as identity primary key,
      event_id uuid unique,
      occurred_at timestamptz not null default statement_timestamp(),
      actor_type text not null,
      actor_subject text,
      action text not null,
      target_type text not null,
      target_id text,
      after_state jsonb,
      metadata jsonb not null default '{}'::jsonb
    );
    insert into storage.buckets (id, allowed_mime_types)
    values ('raw-artifacts', array['application/json', 'application/pdf']);
  `);

  const migration = await readFile(migrationUrl, "utf8");
  await database.exec(migration);
  await database.exec(migration);

  const bucket = await database.query(
    "select public, allowed_mime_types from storage.buckets where id = 'raw-artifacts'",
  );
  assert.equal(bucket.rows[0].public, false);
  const mimeTypes = bucket.rows[0].allowed_mime_types;
  assert.deepEqual(
    [...mimeTypes].sort(),
    ["application/json", "application/pdf", XLSX_MIME].sort(),
  );
  assert.equal(mimeTypes.filter((value) => value === XLSX_MIME).length, 1);

  const auditEvents = await database.query(`
    select count(*)::integer as count
    from audit.audit_events
    where actor_subject = 'migration:allow-raw-xlsx-artifacts'
  `);
  assert.equal(auditEvents.rows[0].count, 1);

  await database.close();
});
