import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { PGlite } from '@electric-sql/pglite';

test('catálogo financeiro encontra anos antigos além dos primeiros 200 sem repetir versões', async () => {
  const db = new PGlite();
  try {
    await db.exec(`
      create role anon; create role authenticated;
      create schema api; create schema raw;
      grant usage on schema api to anon;
      create table raw.raw_records(id uuid primary key, record_type text,
        source_record_key text, payload jsonb, raw_artifact_id uuid, created_at timestamptz);
      create table raw.raw_artifacts(id uuid primary key, source_endpoint_id uuid,
        artifact_kind text, metadata jsonb, source_url text, sha256 text,
        retrieved_at timestamptz, created_at timestamptz);
      insert into raw.raw_artifacts values ('00000000-0000-0000-0000-000000000001',
        '00000000-0000-0000-0000-000000000002','response','{}',
        'https://official.test/catalog',repeat('a',64),now(),now());
      insert into raw.raw_records
      select md5(n::text)::uuid,'municipal_transparency_balancetes',n::text,
        jsonb_build_object('ano',case when n<=5 then '2021' else '2026' end,
          'titulo','Documento '||n,'url','https://official.test/'||n||'.pdf'),
        '00000000-0000-0000-0000-000000000001',
        '2026-01-01'::timestamptz + n*interval '1 minute'
      from generate_series(1,210) n;
      -- Latest version changes reference year: old year must not resurrect it.
      insert into raw.raw_records values (md5('new')::uuid,
        'municipal_transparency_balancetes','5',
        '{"ano":"2026","titulo":"Corrigido","url":"https://official.test/5.pdf"}',
        '00000000-0000-0000-0000-000000000001','2026-02-01');
    `);
    await db.exec(await readFile(new URL('../../supabase/migrations/20261025051028_finance_document_catalog_pagination.sql', import.meta.url),'utf8'));
    await db.exec('set role anon');
    const query = async (page=1, year=2021, family='balancetes') =>
      (await db.query('select * from api.get_public_finance_document_page($1,$2,$3,$4)',[3,page,year,family])).rows[0];
    const first = await query(); const second = await query(2);
    assert.equal(Number(first.total_count),4);
    assert.equal(first.items.length,3);
    assert.equal(second.items.length,1);
    assert.equal(new Set([...first.items,...second.items].map(x=>x.document_id)).size,4);
    assert.ok(first.items.every(x=>x.fiscal_year===2021 && !x.document_preserved));
    assert.deepEqual(first.available_years,[2026,2021]);
    assert.equal(Number((await query(1,null,null)).total_count),210);
    assert.equal(Number((await query(1,2020)).total_count),0);
    assert.deepEqual((await query(500)).items,[]);
    await assert.rejects(query(0));
    await assert.rejects(query(1,2021,'unsafe'));
    await assert.rejects(db.query('select * from raw.raw_records'));
  } finally { await db.close(); }
});
