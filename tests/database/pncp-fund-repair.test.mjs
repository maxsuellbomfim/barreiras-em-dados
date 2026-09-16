import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import {PGlite} from '@electric-sql/pglite';
const foundation=await readFile(new URL('../../supabase/migrations/20260731000705_initial_public_data_foundation.sql',import.meta.url),'utf8');
const migration=await readFile(new URL('../../supabase/migrations/20260916104808_pncp_fund_owner_repair.sql',import.meta.url),'utf8');
const repair=migration+'\nselect procurement.repair_reviewed_fund_owners();';
const specs=[
 ['30667266000153','30667266000153-2-000013/2026','FUNDO MUNICIPAL DE EDUCACAO FMED','5117962643d65c60aba9bcb72449ab4b13f44bb9b5edc633fa9f3d5028ebcdbf','30756.96'],
 ['50525166000108','50525166000108-2-000062/2026','FUNDO MUNICIPAL DE CULTURA DE BARREIRAS - FMCB','29b00d5f75451024ccea89093ffe1b46684ad2c719d938f50c0804044ee388e2','11259.12'],
];
const parent='13654405000195-1-000002/2026';
async function fixture(t){
 const db=new PGlite(); t.after(()=>db.close());
 await db.exec(`create schema raw; create schema org; create schema procurement;
 create table raw.raw_artifacts(id uuid primary key default gen_random_uuid(),sha256 text,http_status int,byte_size bigint,source_url text);
 create table raw.raw_records(id uuid primary key default gen_random_uuid(),raw_artifact_id uuid references raw.raw_artifacts,payload jsonb,payload_sha256 text,record_type text);
 create table procurement.procurements(id uuid primary key default gen_random_uuid(),external_id text);
 create table procurement.suppliers(id uuid primary key default gen_random_uuid());`);
 const bodyDDL=foundation.slice(foundation.indexOf('create table org.public_bodies ('),foundation.indexOf('create table org.departments ('));
 const contractDDL=foundation.slice(foundation.indexOf('create table procurement.contracts ('),foundation.indexOf('create index contracts_supplier_date_idx'));
 await db.exec(bodyDDL+contractDDL);
 await db.exec(`create schema finance;
 create table finance.commitments(contract_id uuid references procurement.contracts);
 create table procurement.contract_amendments(contract_id uuid references procurement.contracts);
 create table procurement.public_works(contract_id uuid references procurement.contracts);`);
 const artifact=(await db.query(`insert into raw.raw_artifacts(sha256,http_status,byte_size,source_url) values ('c5bea3b7b0c28a793d139dcd577d62c2250654215076910b53a778096f2ca2f9',200,5931,'https://pncp.gov.br/api/pncp/v1/orgaos/13654405000195/contratos/contratacao/2026/2?pagina=1&tamanhoPagina=50') returning id`)).rows[0].id;
 const origin=(await db.query(`insert into raw.raw_records(record_type,payload) values ('fixture','{}') returning id`)).rows[0].id;
 const body=(await db.query(`insert into org.public_bodies(origin_raw_record_id,ibge_code,official_code,name,body_type) values($1,'2903201','PREF-BARREIRAS','Prefeitura','executive') returning id`,[origin])).rows[0].id;
 const purchase=(await db.query('insert into procurement.procurements(external_id) values($1) returning id',[parent])).rows[0].id;
 for(const [cnpj,key,name,hash,amount] of specs){
  const payload={numeroControlePNCP:key,numeroControlePNCPCompra:parent,orgaoEntidade:{cnpj,razaoSocial:name},unidadeOrgao:{codigoIbge:'2903201'}};
  const raw=(await db.query('insert into raw.raw_records(raw_artifact_id,payload,payload_sha256,record_type) values($1,$2,$3,\'pncp_contrato\') returning id',[artifact,JSON.stringify(payload),hash])).rows[0].id;
  await db.query(`insert into procurement.contracts(origin_raw_record_id,public_body_id,procurement_id,external_id,object_description,initial_amount,current_amount) values($1,$2,$3,$4,'Texto oficial intocado',$5,$5)`,[raw,body,purchase,key,amount]);
 }
 return db;
}
const snapshot=async db=>(await db.query('select to_jsonb(c) data from procurement.contracts c order by external_id,version')).rows.map(r=>r.data);
test('reparo preserva contratos antigos e cria apenas duas versões com os fundos corretos',async t=>{
 const db=await fixture(t),before=await snapshot(db); await db.exec(repair);
 const after=await snapshot(db); assert.equal(after.length,4);
 for(const old of before){
  assert.deepEqual(after.find(r=>r.id===old.id),old);
  const next=after.find(r=>r.supersedes_id===old.id); assert.ok(next);
  for(const field of Object.keys(old).filter(k=>!['id','public_body_id','supersedes_id','version','created_at'].includes(k))) assert.deepEqual(next[field],old[field],field);
  assert.equal(next.version,2); assert.notEqual(next.public_body_id,old.public_body_id);
 }
 assert.equal((await db.query("select count(*)::int n from org.public_bodies where body_type='municipal_fund'")).rows[0].n,2);
 assert.deepEqual((await db.query("select count(*)::int n,sum(current_amount)::text total from procurement.contracts c where not exists(select 1 from procurement.contracts newer where newer.supersedes_id=c.id)")).rows[0],{n:2,total:'42016.08'});
 await db.exec(repair); assert.deepEqual(await snapshot(db),after);
});
test('vínculo financeiro existente bloqueia reparo que poderia ocultá-lo',async t=>{
 const db=await fixture(t),before=await snapshot(db);
 await db.query('insert into finance.commitments values($1)',[before[0].id]);
 await assert.rejects(db.exec(repair),/vínculos dependentes/); await db.exec('rollback');
 assert.deepEqual(await snapshot(db),before);
});
test('migração não executa reparo automaticamente nem concede acesso público',async t=>{
 const db=await fixture(t),before=await snapshot(db);
 await db.exec("create role anon; create role authenticated; create role collector_worker;");
 await db.exec(migration); assert.deepEqual(await snapshot(db),before);
 for(const role of ['anon','authenticated','collector_worker']){
  assert.equal((await db.query("select has_function_privilege($1,'procurement.repair_reviewed_fund_owners()','execute') allowed",[role])).rows[0].allowed,false);
 }
});
test('novo tipo permite fundos distintos sem afrouxar unicidade da Prefeitura ou CNPJ',async t=>{
 const db=await fixture(t); await db.exec(repair);
 await assert.rejects(db.exec("insert into org.public_bodies(origin_raw_record_id,ibge_code,official_code,name,body_type) select origin_raw_record_id,ibge_code,official_code,name,body_type from org.public_bodies where body_type='executive'"),/unique/);
 await assert.rejects(db.exec("insert into org.public_bodies(origin_raw_record_id,ibge_code,official_code,name,body_type) select origin_raw_record_id,ibge_code,official_code,name,body_type from org.public_bodies where body_type='municipal_fund' limit 1"),/unique/);
 await assert.rejects(db.exec("insert into org.public_bodies(origin_raw_record_id,ibge_code,name,body_type) select origin_raw_record_id,ibge_code,name,'municipal_fund' from org.public_bodies limit 1"),/check/);
});
test('evidência divergente bloqueia tudo sem reparo parcial',async t=>{
 const db=await fixture(t); const before=await snapshot(db);
 await db.exec("update raw.raw_records set payload_sha256='bad' where payload->>'numeroControlePNCP'='50525166000108-2-000062/2026'");
 await assert.rejects(db.exec(repair)); await db.exec('rollback');
 assert.deepEqual(await snapshot(db),before);
 assert.equal((await db.query('select count(*)::int n from org.public_bodies')).rows[0].n,1);
});
