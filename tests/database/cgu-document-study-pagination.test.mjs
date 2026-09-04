import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { PGlite } from "@electric-sql/pglite";

const migrationUrl = new URL(
  "../../supabase/migrations/20260902230614_cgu_document_study_pagination.sql",
  import.meta.url,
);

test("documentos federais da CGU paginam e filtram o acervo completo", async () => {
  const migration = await readFile(migrationUrl, "utf8");
  assert.match(migration, /get_public_cgu_federal_amendment_document_study/i);
  assert.match(migration, /count\(\*\).*filtered/is);

  const database = new PGlite();
  try {
    await database.exec(`
      create role anon nologin;
      create role authenticated nologin;
      create schema api;
      create schema territory;
      grant usage on schema api to anon, authenticated;
      create table territory.cgu_federal_amendment_documents (
        raw_record_id uuid primary key,
        archive_year smallint not null,
        amendment_year smallint not null,
        amendment_code text not null,
        amendment_number text not null,
        amendment_type text not null,
        author_kind text not null,
        author_key text not null,
        author_name text not null,
        document_date date not null,
        document_code text not null,
        expense_stage text not null,
        expense_stage_source text not null,
        committed_amount numeric(20,2) not null,
        paid_amount numeric(20,2) not null,
        beneficiary_name text not null,
        beneficiary_type text,
        beneficiary_municipality text,
        locality text not null,
        agency_name text not null,
        superior_agency_name text,
        function_name text,
        subfunction_name text,
        program_name text,
        action_name text not null,
        citizen_language text,
        source_row_number integer not null,
        source_url text not null,
        artifact_sha256 text not null,
        collected_at timestamptz not null
      );
    `);
    await database.exec(migration);
    await database.exec(`
      insert into territory.cgu_federal_amendment_documents values
        ('00000000-0000-0000-0000-000000000001', 2024, 2022, 'A-1', '1', 'Emenda individual', 'person', 'ana', 'ANA', '2024-09-10', 'DOC-3', 'payment', 'Pagamento', 0, 300, 'FUNDO DE SAÚDE', 'Fundo', 'BARREIRAS', 'BARREIRAS - BA', 'MINISTÉRIO DA SAÚDE', null, 'SAÚDE', null, null, 'ATENÇÃO À SAÚDE', 'Custeio da saúde', 3, 'https://example.test/2024.zip', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', '2026-09-01T10:00:00Z'),
        ('00000000-0000-0000-0000-000000000002', 2024, 2023, 'B-2', '2', 'Emenda individual', 'person', 'bruno', 'BRUNO', '2024-08-10', 'DOC-2', 'commitment', 'Empenho', 200, 0, 'MUNICÍPIO DE BARREIRAS', 'Município', 'BARREIRAS', 'BARREIRAS - BA', 'MINISTÉRIO DA EDUCAÇÃO', null, 'EDUCAÇÃO', null, null, 'TRANSPORTE ESCOLAR', 'Ônibus escolar', 2, 'https://example.test/2024.zip', 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', '2026-09-01T10:00:00Z'),
        ('00000000-0000-0000-0000-000000000003', 2023, 2021, 'C-3', '3', 'Emenda de comissão', 'commission', 'saude', 'COMISSÃO DA SAÚDE', '2023-07-10', 'DOC-1', 'liquidation', 'Liquidação', 0, 0, 'HOSPITAL REGIONAL', 'Hospital', 'BARREIRAS', 'BARREIRAS - BA', 'MINISTÉRIO DA SAÚDE', null, 'SAÚDE', null, null, 'ATENÇÃO ESPECIALIZADA', 'Assistência hospitalar', 1, 'https://example.test/2023.zip', 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc', '2026-09-01T10:00:00Z');
    `);

    await database.exec("set role anon");
    const page = await database.query(`
      select * from api.get_public_cgu_federal_amendment_document_study(
        1, 1, null, null, null, null
      )
    `);
    const filtered = await database.query(`
      select * from api.get_public_cgu_federal_amendment_document_study(
        25, 0, 2024::smallint, null, 'commitment', 'educacao'
      )
    `);
    await database.exec("reset role");

    assert.equal(page.rows.length, 1);
    assert.equal(Number(page.rows[0].total_count), 3);
    assert.equal(Number(page.rows[0].catalog_count), 3);
    assert.deepEqual(page.rows[0].available_years, [2024, 2023]);
    assert.equal(page.rows[0].items.length, 1);
    assert.equal(page.rows[0].items[0].document_code, "DOC-2");

    assert.equal(Number(filtered.rows[0].total_count), 1);
    assert.equal(Number(filtered.rows[0].catalog_count), 3);
    assert.equal(filtered.rows[0].items[0].author_name, "BRUNO");
    assert.deepEqual(filtered.rows[0].available_stages, [
      "commitment",
      "liquidation",
      "payment",
    ]);
  } finally {
    await database.close();
  }
});
