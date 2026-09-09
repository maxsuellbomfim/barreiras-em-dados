import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { PGlite } from '@electric-sql/pglite';

const migration = await readFile(new URL('../../supabase/migrations/20260908173000_fns_pharmacy_registry.sql', import.meta.url), 'utf8');
const key = 'd'.repeat(64);
async function setup() {
  const db = new PGlite();
  await db.exec(`
    create role anon; create role authenticated; create role service_role bypassrls;
    create schema source; create schema raw; create schema api; create schema audit;
    grant usage on schema api, source to anon, authenticated, service_role;
    create function audit.reject_mutation() returns trigger language plpgsql as $$ begin raise exception 'immutable'; end $$;
    create table raw.raw_artifacts(id uuid primary key, sha256 text, source_url text, http_status int, byte_size bigint, content_type text);
    create table raw.raw_records(id uuid primary key, raw_artifact_id uuid references raw.raw_artifacts, record_type text, payload jsonb);
    insert into raw.raw_artifacts values
      ('00000000-0000-0000-0000-000000000001',repeat('a',64),'https://consultafns.saude.gov.br/recursos/consulta-detalhada/detalhe-pagamento?ano=2025',200,100,'application/json'),
      ('00000000-0000-0000-0000-000000000002',repeat('b',64),'https://infoms.saude.gov.br/tempcontent/export/register.xlsx',null,100,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
    insert into raw.raw_records values ('00000000-0000-0000-0000-000000000003','00000000-0000-0000-0000-000000000001','fns_pharmacy_payment',
      '{"document_key":"${key}","document_date":"2025-02-07","net":"10.00","source_row":1,"establishment":"FARMACIA TESTE","register_row":2,"register_sha256":"${'b'.repeat(64)}"}');
  `);
  await db.exec(migration);
  await db.exec(await readFile(new URL('../../supabase/migrations/20260909001000_pharmacy_public_coverage.sql', import.meta.url), 'utf8'));
  return db;
}
async function snapshot(db, scope='c'.repeat(64)) {
  const {rows} = await db.query(`insert into source.fns_pharmacy_snapshots(scope_key,payment_year,payment_artifact_id,register_artifact_id,payment_sha256,register_sha256,establishment,expected_documents)
    values ($1,2025,'00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002',repeat('a',64),repeat('b',64),'FARMACIA TESTE',1) returning id`, [scope]);
  return rows[0].id;
}
async function document(db, id) {
  await db.query(`insert into source.fns_pharmacy_documents(snapshot_id,document_key,raw_record_id,document_date,net_amount,source_row,register_row)
    values ($1,$2,'00000000-0000-0000-0000-000000000003','2025-02-07',10,1,2)`, [id,key]);
}
async function decide(db,id,decision='approved') {
  await db.query(`insert into source.fns_pharmacy_decisions(snapshot_id,decision,reviewer_ref,review_note) values ($1,$2,'operator:test','Private review note not for frontend')`,[id,decision]);
}
const read = db => db.query('select * from api.get_public_pharmacy_payments(2025,0)');
const coverage = async db => (await db.query('select * from api.get_public_pharmacy_coverage(2025)')).rows[0];

test('pharmacy pending, approved, revoked and new snapshot never fall back', async () => {
  const db=await setup();
  try {
    const id=await snapshot(db); await document(db,id);
    assert.equal((await read(db)).rows.length,0);
    assert.equal((await coverage(db)).status,'pending');
    await decide(db,id);
    await db.exec('set role anon');
    const rows=(await read(db)).rows;
    assert.equal(rows.length,1); assert.equal(rows[0].amount,'10.00');
    assert.equal(rows[0].historical_registration_verified,false);
    assert.equal((await coverage(db)).published_documents,1);
    assert.equal((await coverage(db)).status,'partial');
    assert.doesNotMatch(JSON.stringify(rows), /review_note|Private review|raw_record_id|scope_key|snapshot_id/);
    await assert.rejects(db.query('select * from source.fns_pharmacy_documents'), /permission denied/);
    await db.exec('reset role');
    await decide(db,id,'revoked'); assert.equal((await read(db)).rows.length,0);
    assert.equal((await coverage(db)).published_documents,0);
    await decide(db,id); assert.equal((await read(db)).rows.length,1);
    await snapshot(db); assert.equal((await read(db)).rows.length,0);
    assert.equal((await coverage(db)).status,'pending');
  } finally { await db.close(); }
});

test('pharmacy approval requires complete evidence; immutable decisions seal documents',async()=>{
  const db=await setup();
  try {
    const id=await snapshot(db);
    await assert.rejects(decide(db,id),/incomplete|evidence/i);
    await document(db,id); await decide(db,id);
    await assert.rejects(document(db,id),/sealed/i);
    await assert.rejects(db.query('delete from source.fns_pharmacy_decisions'),/immutable/);
    await db.exec("update raw.raw_artifacts set sha256=repeat('f',64) where id='00000000-0000-0000-0000-000000000001'");
    assert.equal((await read(db)).rows.length,0);
    assert.equal((await coverage(db)).published_documents,0);
    await assert.rejects(db.query('select * from api.get_public_pharmacy_payments(2025,-1)'),/Invalid/);
  } finally { await db.close(); }
});

test('pharmacy duplicated document across scopes is excluded, never doubled',async()=>{
  const db=await setup();
  try {
    for(const scope of ['c','e']) { const id=await snapshot(db,scope.repeat(64)); await document(db,id); await decide(db,id); }
    assert.equal((await read(db)).rows.length,0);
    await db.exec('set role service_role');
    await assert.rejects(db.query('select * from source.fns_pharmacy_snapshots'),/permission denied/);
  } finally { await db.close(); }
});

test('pharmacy raw lineage mismatches are rejected and pagination is bounded',async()=>{
  const db=await setup();
  try {
    const first=await snapshot(db);
    await db.exec("update raw.raw_records set payload=jsonb_set(payload,'{net}','\"11.00\"')");
    await assert.rejects(document(db,first),/mismatch/);
    await db.exec("update raw.raw_records set payload=jsonb_set(payload,'{net}','\"10.00\"')");
    await document(db,first); await decide(db,first);
    for(let i=1;i<=25;i++) {
      const docKey=i.toString(16).padStart(64,'0');
      const recordId=`00000000-0000-0000-0001-${String(i).padStart(12,'0')}`;
      await db.query(`insert into raw.raw_records select $1::uuid,raw_artifact_id,record_type,
        jsonb_set(payload,'{document_key}',to_jsonb($2::text)) from raw.raw_records
        where id='00000000-0000-0000-0000-000000000003'`,[recordId,docKey]);
      const id=await snapshot(db,docKey);
      await db.query(`insert into source.fns_pharmacy_documents values($1,$2,$3::uuid,'2025-02-07',10,1,2)`,[id,docKey,recordId]);
      await decide(db,id);
    }
    const page1=(await read(db)).rows;
    const page2=(await db.query('select * from api.get_public_pharmacy_payments(2025,25)')).rows;
    assert.equal(page1.length,25); assert.equal(page2.length,1);
    assert.equal(new Set([...page1,...page2].map(r=>r.id)).size,26);
    assert.equal((await coverage(db)).published_documents,26);
    assert.equal((await coverage(db)).establishments,26);
    await assert.rejects(db.query('select * from api.get_public_pharmacy_coverage(2020)'),/Invalid/);
    assert.equal((await db.query('select * from api.get_public_pharmacy_payments(2024,0)')).rows.length,0);
  } finally { await db.close(); }
});
