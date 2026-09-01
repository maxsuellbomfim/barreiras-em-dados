import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { PGlite } from "@electric-sql/pglite";

const migrationUrl = new URL(
  "../../supabase/migrations/20260901020000_index_municipal_finance_document_lookup.sql",
  import.meta.url,
);

test("consultas do catálogo financeiro usam índices de registro e documento", async () => {
  const database = new PGlite();
  await database.exec(`
    create schema raw;
    create table raw.raw_records (
      id uuid primary key,
      record_type text not null,
      source_record_key text,
      payload jsonb not null,
      raw_artifact_id uuid not null,
      created_at timestamptz not null
    );
    create table raw.raw_artifacts (
      id uuid primary key,
      source_endpoint_id uuid not null,
      artifact_kind text not null,
      metadata jsonb not null,
      source_url text not null,
      sha256 text not null,
      created_at timestamptz not null
    );
  `);
  await database.exec(await readFile(migrationUrl, "utf8"));
  await database.exec("set enable_seqscan = off");

  const recordPlan = await database.query(`
    explain (format text)
    select id
    from raw.raw_records
    where record_type = 'municipal_transparency_pdc-contas-anuais'
      and source_record_key = 'official:1'
      and payload ->> 'url' ~ '^https://'
    order by source_record_key, created_at desc, id desc
  `);
  const documentPlan = await database.query(`
    explain (format text)
    select id
    from raw.raw_artifacts
    where source_endpoint_id = '00000000-0000-0000-0000-000000000001'
      and artifact_kind = 'document'
      and metadata ->> 'schema_name' = 'municipal-transparency-document'
      and metadata ->> 'source_record_key' = 'official:1'
      and source_url = 'https://example.gov.br/documento.pdf'
    order by created_at desc, id desc
    limit 1
  `);

  const recordPlanText = JSON.stringify(recordPlan.rows);
  const documentPlanText = JSON.stringify(documentPlan.rows);
  assert.match(recordPlanText, /raw_records_finance_document_lookup_idx/);
  assert.match(documentPlanText, /raw_artifacts_municipal_document_identity_idx/);

  await database.close();
});
