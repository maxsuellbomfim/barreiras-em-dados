import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { PGlite } from "@electric-sql/pglite";

test("busca do Diário identifica a edição e preserva sequência e publicação", async (t) => {
  const db = new PGlite();
  try {
    // Limite externo: somente as colunas consumidas pela RPC, sem mock da consulta.
    await db.exec(`
      create role anon; create role authenticated;
      create schema api; create schema editorial; create schema raw;
      create table raw.raw_artifacts (id integer primary key, sha256 text, metadata jsonb);
      create table editorial.gazette_document_versions (
        id integer primary key, raw_artifact_id integer references raw.raw_artifacts,
        edition integer, edition_year integer, edition_date date,
        batch_idempotency_key text, created_at timestamptz, published_at timestamptz,
        publication_status text, document_order integer, literal_title text,
        document_type text, page_start integer, page_end integer,
        full_text text, text_sha256 text
      );
      insert into raw.raw_artifacts values
        (1, repeat('a',64), '{"schema_name":"gazette-direct-edition"}'),
        (2, repeat('b',64), '{"schema_name":"gazette-direct-edition"}'),
        (3, repeat('c',64), '{"schema_name":"gazette-direct-edition"}');
      insert into editorial.gazette_document_versions values
        (1,1,4598,2026,'2026-02-13','a','2026-03-01','2026-03-01','validated',
          1,'Portaria Alfa','portaria',1,2,'Portaria Alfa. Texto literal.',repeat('d',64)),
        (2,1,4598,2026,'2026-02-13','a','2026-03-01','2026-03-01','validated',
          2,'Resolução Beta','resolucao',3,4,'Resolução Beta. Calendário escolar.',repeat('e',64)),
        (3,2,4600,2026,'2026-02-20','b','2026-03-01','2026-03-01','validated',
          1,'Aviso posterior','aviso',1,1,'Aviso posterior. Referência à edição 4598.',repeat('f',64)),
        (4,3,4598,2025,'2025-02-13','c','2025-03-01','2025-03-01','edition_fallback',
          1,'Publicação antiga',null,1,1,'Publicação antiga. Texto anterior.',repeat('1',64));
    `);
    for (const name of [
      "20260811111905_integral_gazette_global_search.sql",
      "20260905022054_diary_edition_search.sql",
    ]) {
      await db.exec(await readFile(new URL(`../../supabase/migrations/${name}`, import.meta.url), "utf8"));
    }
    const search = async (query, size = 21, offset = 0) =>
      (await db.query("select * from api.search_integral_gazette_editions($1,$2,$3)", [query, size, offset])).rows;

    await t.test("número exato precede menções em outras edições", async () => {
      const rows = await search("4598");
      assert.deepEqual(rows.map((r) => [r.edition, r.edition_year]), [[4598,2026],[4598,2025],[4600,2026]]);
      assert.deepEqual(rows[0].documents.map((d) => d.document_order), [1,2]);
    });
    await t.test("número com ano e separador de milhar respeita o exercício", async () => {
      for (const query of ["4598/2026", " 4.598/2026 "]) {
        const rows = await search(query);
        assert.deepEqual(rows.map((r) => [r.edition,r.edition_year]), [[4598,2026]]);
      }
    });
    await t.test("termo no segundo documento retorna a sequência inteira sem reescrever", async () => {
      const rows = await search("CALENDÁRIO");
      assert.equal(rows.length, 1);
      assert.deepEqual(rows[0].documents.map((d) => [d.document_order,d.full_text]), [
        [1,"Portaria Alfa. Texto literal."], [2,"Resolução Beta. Calendário escolar."],
      ]);
    });
    await t.test("paginação é estável após priorizar número exato", async () => {
      assert.deepEqual((await search("4598",1,1)).map((r) => [r.edition,r.edition_year]), [[4598,2025]]);
      assert.equal((await search("inexistente")).length, 0);
      assert.equal((await search(" ")).length, 3);
    });
    await t.test("entrada excessiva e paginação inválida são rejeitadas", async () => {
      await assert.rejects(search("a".repeat(121)), /120/);
      await assert.rejects(search("4598",0), /page_size/);
      await assert.rejects(search("4598",21,-1), /page_offset/);
      assert.equal((await search("9".repeat(120))).length, 0);
    });
    await t.test("lote mais novo não publicado não reativa o anterior", async () => {
      await db.exec(`insert into editorial.gazette_document_versions
        select 5,raw_artifact_id,edition,edition_year,edition_date,'new',
          '2026-04-01'::timestamptz,null,'pending',document_order,literal_title,
          document_type,page_start,page_end,full_text,text_sha256
        from editorial.gazette_document_versions where id=1;`);
      assert.equal((await search("4598/2026")).length, 0);
      assert.equal((await search("calendário")).length, 0);
    });
    await t.test("consulta pública mantém grants explícitos", async () => {
      const {rows} = await db.query(`select
        has_function_privilege('anon','api.search_integral_gazette_editions(text,integer,integer)','execute') allowed,
        has_function_privilege('authenticated','api.search_integral_gazette_editions(text,integer,integer)','execute') signed_in`);
      assert.deepEqual(rows, [{allowed:true,signed_in:true}]);
    });
  } finally {
    await db.close();
  }
});
