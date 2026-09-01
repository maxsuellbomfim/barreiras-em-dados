import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { PGlite } from "@electric-sql/pglite";

const migrationUrl = new URL(
  "../../supabase/migrations/20260901040000_publish_municipal_control_text.sql",
  import.meta.url,
);
const optimizationMigrationUrl = new URL(
  "../../supabase/migrations/20260901050000_optimize_municipal_control_detail.sql",
  import.meta.url,
);

test("texto da base legal publica somente a projeção oficial verificada", async () => {
  const database = new PGlite();
  try {
    await database.exec(`
      create role anon nologin;
      create role authenticated nologin;
      create schema api;
      create schema raw;
      grant usage on schema api to anon, authenticated;
      create table raw.raw_artifacts (
        id uuid primary key,
        source_endpoint_id uuid not null,
        artifact_kind text not null,
        source_url text not null,
        sha256 text not null,
        content_type text,
        http_status integer,
        metadata jsonb not null default '{}'::jsonb,
        created_at timestamptz not null
      );
      create table raw.raw_records (
        id uuid primary key,
        raw_artifact_id uuid not null references raw.raw_artifacts(id),
        source_record_key text,
        record_type text not null,
        payload jsonb not null,
        created_at timestamptz not null
      );
      create table raw.document_pages (
        id uuid primary key,
        raw_artifact_id uuid not null references raw.raw_artifacts(id),
        page_number integer not null,
        parser_version text not null,
        extraction_method text not null,
        text_content text,
        text_sha256 text,
        created_at timestamptz not null default statement_timestamp()
      );
      create table raw.extraction_jobs (
        id uuid primary key,
        raw_artifact_id uuid references raw.raw_artifacts(id),
        job_type text not null,
        status text not null
      );
    `);
    await database.exec(await readFile(migrationUrl, "utf8"));
    await database.exec(await readFile(optimizationMigrationUrl, "utf8"));
    await database.exec(`
      insert into raw.raw_artifacts (
        id, source_endpoint_id, artifact_kind, source_url, sha256,
        content_type, http_status, metadata, created_at
      ) values
        (
          '00000000-0000-0000-0000-000000000901',
          '00000000-0000-0000-0000-000000000001',
          'http_response', 'https://barreiras.ba.gov.br/api/controle',
          '${"a".repeat(64)}', 'application/json', 200, '{}',
          '2026-09-01 10:00:00+00'
        ),
        (
          '00000000-0000-0000-0000-000000000902',
          '00000000-0000-0000-0000-000000000001',
          'document', 'https://barreiras.ba.gov.br/lei-controle.docx',
          '${"b".repeat(64)}',
          'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
          200,
          '{"schema_name":"municipal-transparency-document","document_role":"docx","source_record_key":"controle:1"}',
          '2026-09-01 10:01:00+00'
        ),
        (
          '00000000-0000-0000-0000-000000000903',
          '00000000-0000-0000-0000-000000000001',
          'document', 'https://barreiras.ba.gov.br/lei-sem-texto.docx',
          '${"c".repeat(64)}',
          'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
          200,
          '{"schema_name":"municipal-transparency-document","document_role":"docx","source_record_key":"controle:2"}',
          '2026-09-01 10:02:00+00'
        );
      insert into raw.raw_records (
        id, raw_artifact_id, source_record_key, record_type, payload, created_at
      ) values
        (
          '00000000-0000-0000-0000-000000000911',
          '00000000-0000-0000-0000-000000000901', 'controle:1',
          'municipal_transparency_pdc-contas-anuais',
          '{"titulo":"Lei de controle interno","data":"01/01/2024","url":"https://barreiras.ba.gov.br/lei-controle.docx"}',
          '2026-09-01 10:00:00+00'
        ),
        (
          '00000000-0000-0000-0000-000000000912',
          '00000000-0000-0000-0000-000000000901', 'controle:2',
          'municipal_transparency_pdc-contas-anuais',
          '{"titulo":"Lei ainda não processada","data":"02/01/2024","url":"https://barreiras.ba.gov.br/lei-sem-texto.docx"}',
          '2026-09-01 10:00:00+00'
        ),
        (
          '00000000-0000-0000-0000-000000000913',
          '00000000-0000-0000-0000-000000000901', 'controle:1',
          'municipal_transparency_pdc-contas-anuais',
          '{"titulo":"Lei de controle interno","data":"01/01/2024","url":"https://barreiras.ba.gov.br/lei-controle.docx"}',
          '2026-09-01 10:03:00+00'
        );
      insert into raw.document_pages (
        id, raw_artifact_id, page_number, parser_version, extraction_method,
        text_content, text_sha256
      ) values (
        '00000000-0000-0000-0000-000000000921',
        '00000000-0000-0000-0000-000000000902', 1,
          'docx-wordprocessingml/1.0.0', 'embedded_text',
          'Art. 1º Esta lei organiza o controle interno do Município de Barreiras.',
          '${"d".repeat(64)}'
      );
      insert into raw.extraction_jobs (
        id, raw_artifact_id, job_type, status
      ) values (
        '00000000-0000-0000-0000-000000000931',
        '00000000-0000-0000-0000-000000000902',
        'municipal_docx_text', 'succeeded'
      );
    `);

    await database.exec("set role anon");
    const search = await database.query(`
      select document_id, title, excerpt, total_count, methodology_version
      from api.search_public_municipal_control_documents('controle', 20, 0)
    `);
    const detail = await database.query(`
      select document_id, title, full_text, document_artifact_sha256,
        text_sha256, parser_version, methodology_version
      from api.get_public_municipal_control_document(
        '00000000-0000-0000-0000-000000000913'
      )
    `);
    const stale = await database.query(`
      select document_id
      from api.get_public_municipal_control_document(
        '00000000-0000-0000-0000-000000000911'
      )
    `);
    const hidden = await database.query(`
      select document_id
      from api.search_public_municipal_control_documents('processada', 20, 0)
    `);

    assert.deepEqual(search.rows, [{
      document_id: "00000000-0000-0000-0000-000000000913",
      title: "Lei de controle interno",
      excerpt:
        "Art. 1º Esta lei organiza o controle interno do Município de Barreiras.",
      total_count: 1,
      methodology_version: "municipal-control-text/1.0.0",
    }]);
    assert.deepEqual(detail.rows, [{
      document_id: "00000000-0000-0000-0000-000000000913",
      title: "Lei de controle interno",
      full_text:
        "Art. 1º Esta lei organiza o controle interno do Município de Barreiras.",
      document_artifact_sha256: "b".repeat(64),
      text_sha256: "d".repeat(64),
      parser_version: "docx-wordprocessingml/1.0.0",
      methodology_version: "municipal-control-text/1.0.0",
    }]);
    assert.deepEqual(stale.rows, []);
    assert.deepEqual(hidden.rows, []);
    await assert.rejects(
      database.query("select text_content from raw.document_pages"),
      /permission denied/,
    );
    await database.exec("reset role");
  } finally {
    await database.close();
  }
});
