import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { PGlite } from '@electric-sql/pglite';
const sql=await readFile(new URL('../../scripts/sql/import-pharmacy-plan.sql',import.meta.url),'utf8');
const registry=await readFile(new URL('../../supabase/migrations/20260908173000_fns_pharmacy_registry.sql',import.meta.url),'utf8');
const renewal=await readFile(new URL('../../supabase/migrations/20260909010000_pharmacy_renewal_identity.sql',import.meta.url),'utf8');
for (const format of ['xlsx','pdf']) test(`pharmacy ${format} import replays without new snapshots, preserves approvals and rolls back conflicts`,async()=>{
 const db=new PGlite();
 try {
  await db.exec(`create role anon; create role authenticated; create role service_role;
   create schema source; create schema raw; create schema audit; create schema api;
   create function audit.reject_mutation() returns trigger language plpgsql as $$ begin raise exception 'immutable'; end $$;
   create table source.data_sources(id uuid primary key default gen_random_uuid(),slug text);
   create table source.source_endpoints(id uuid primary key default gen_random_uuid(),data_source_id uuid,slug text,enabled boolean);
   create table source.collection_runs(id uuid primary key default gen_random_uuid(),source_endpoint_id uuid,idempotency_key text unique,collector_version text,parser_version text,status text,attempt_count int,started_at timestamptz,completed_at timestamptz,metrics jsonb);
   create table raw.raw_artifacts(id uuid primary key default gen_random_uuid(),collection_run_id uuid,source_endpoint_id uuid,idempotency_key text unique,artifact_kind text,source_url text,retrieved_at timestamptz,http_status int,content_type text,byte_size bigint,sha256 text,object_key text unique,collector_version text,parser_version text);
   create table raw.raw_records(id uuid primary key default gen_random_uuid(),raw_artifact_id uuid,source_record_key text,record_type text,record_index int,payload jsonb,payload_sha256 text,parser_version text,idempotency_key text unique,collected_at timestamptz,unique(raw_artifact_id,record_index));
   insert into source.data_sources(slug) values('fns-farmacia-popular');
   insert into source.source_endpoints(data_source_id,slug,enabled) select id,unnest(array['payment','register','register-renewal']),true from source.data_sources;`);
  await db.exec(registry);
  await db.exec(renewal);
  const name="FARMACIA D'AGUA";
  const plan={version:'fns-pharmacy-import/1.0.0',publication_allowed:false,plan_sha256:'e'.repeat(64),
   artifacts:[['payment','a','https://consultafns.saude.gov.br/recursos/consulta-detalhada/detalhe-pagamento?ano=2025','application/json'],['register','b','https://infoms.saude.gov.br/tempcontent/test.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']].map(([endpoint,hash,source_url,content_type])=>({endpoint,sha256:hash.repeat(64),byte_size:100,object_key:`fns/${hash}`,source_url,content_type,retrieved_at:'2026-09-08T16:00:00Z',http_status:endpoint==='payment'?200:null})),
   snapshots:[{scope_key:'c'.repeat(64),payment_year:2025,payment_sha256:'a'.repeat(64),register_sha256:'b'.repeat(64),establishment:name,documents:[{payload:{document_key:'d'.repeat(64),document_date:'2025-02-07',net:'10.00',source_row:1,register_row:2,establishment:name,register_sha256:'b'.repeat(64)},payload_sha256:'f'.repeat(64),idempotency_key:'1'.repeat(64)}]}]};
  if(format==='pdf') {
   Object.assign(plan.artifacts[1],{endpoint:'register-renewal',content_type:'application/pdf',http_status:200,source_url:'https://www.gov.br/saude/pt-br/composicao/sectics/farmacia-popular/renovacao-de-estabelecimentos-participantes/empresas-credenciadas-para-realizar-a-renovacao-2025/@@download/file'});
   Object.assign(plan.snapshots[0].documents[0].payload,{register_page:44,register_row:1});
  }
  const run=()=>db.exec(sql.replaceAll('__PLAN_JSON__',`'${JSON.stringify(plan).replaceAll("'","''")}'`));
  await run(); await run();
  assert.equal((await db.query('select * from source.fns_pharmacy_snapshots')).rows.length,1);
  assert.equal((await db.query('select * from raw.raw_records')).rows.length,1);
  assert.equal((await db.query('select * from api.get_public_pharmacy_payments(2025,0)')).rows.length,0);
  await db.exec("insert into source.fns_pharmacy_decisions(snapshot_id,decision,reviewer_ref,review_note) values(1,'approved','operator:test','Synthetic verification for replay')");
  await run();
  assert.equal((await db.query('select * from api.get_public_pharmacy_payments(2025,0)')).rows.length,1);
  plan.snapshots[0].documents[0].payload.net='20.00';
  await assert.rejects(run(),/replay conflict/);
  await db.exec('rollback');
  assert.equal((await db.query('select * from api.get_public_pharmacy_payments(2025,0)')).rows[0].amount,'10.00');
 } finally {await db.close();}
});
