import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { PGlite } from "@electric-sql/pglite";
import { pgcrypto } from "@electric-sql/pglite/contrib/pgcrypto";

const originalMigration = await readFile(new URL(
  "../../supabase/migrations/20260803170212_normalize_pncp_contracts.sql",
  import.meta.url,
), "utf8");
const previousMigration = await readFile(new URL(
  "../../supabase/migrations/20260915154500_pncp_latest_contract_snapshot.sql",
  import.meta.url,
), "utf8");

const migration = await readFile(new URL("../../supabase/migrations/20260916023040_pncp_explicit_owner.sql", import.meta.url), "utf8");
const bodyId = "10000000-0000-0000-0000-000000000001";
const recordId = (number) => `20000000-0000-0000-0000-${String(number).padStart(12, "0")}`;
const totals = (contracts, suppliers = 0, skipped = 0, procurements = 0) => ({
  procurements_inserted: procurements,
  suppliers_inserted: suppliers,
  contracts_inserted: contracts,
  contracts_skipped: skipped,
});

async function databaseFor(t, { applyCorrection = true } = {}) {
  const db = new PGlite({extensions:{pgcrypto}});
  t.after(() => db.close());
  await db.exec(`
    create role anon;
    create role authenticated;
    create role collector_worker;
    create schema raw;
    create schema org;
    create schema procurement;
    create table raw.raw_records (
      id uuid primary key, record_type text not null, payload jsonb not null,
      payload_sha256 text not null, collected_at timestamptz not null,
      created_at timestamptz not null
    );
    create table org.public_bodies (
      id uuid primary key, official_code text, ibge_code text,
      body_type text, active_until date, version integer
    );
    create table procurement.procurements (
      id uuid primary key default gen_random_uuid(),
      origin_raw_record_id uuid references raw.raw_records,
      public_body_id uuid references org.public_bodies,
      supersedes_id uuid references procurement.procurements, version integer,
      created_at timestamptz not null default now(), external_id text,
      process_number text, procurement_mode text, object_description text,
      legal_basis text, status text, publication_date date, opening_date timestamptz,
      estimated_amount numeric, awarded_amount numeric
    );
    create table procurement.suppliers (
      id uuid primary key default gen_random_uuid(),
      origin_raw_record_id uuid references raw.raw_records,
      supersedes_id uuid references procurement.suppliers, version integer,
      created_at timestamptz not null default now(), entity_type text,
      legal_name text, normalized_name text, public_registration_type text,
      public_registration_number text, municipality text, state_code text
    );
    create table procurement.contracts (
      id uuid primary key default gen_random_uuid(),
      origin_raw_record_id uuid references raw.raw_records,
      public_body_id uuid references org.public_bodies,
      procurement_id uuid references procurement.procurements,
      supplier_id uuid references procurement.suppliers,
      supersedes_id uuid references procurement.contracts, version integer,
      created_at timestamptz not null default now(), external_id text,
      contract_number text, object_description text, signed_date date,
      effective_from date, effective_until date, initial_amount numeric,
      current_amount numeric, status text
    );
    insert into org.public_bodies values (
      '${bodyId}', '13.654.405/0001-95', '2903201', 'executive', null, 1
    );
  `);
  await db.exec(originalMigration);
  if (applyCorrection) await db.exec(migration);
  return db;
}

function contract(key, changes = {}) {
  return {
    numeroControlePNCP: key,
    orgaoEntidade: { cnpj: "13654405000195" },
    unidadeOrgao: { codigoIbge: "2903201", municipioNome: "Barreiras", ufSigla: "BA" },
    objetoContrato: "Objeto oficial preservado",
    valorInicial: 100,
    valorGlobal: 100,
    ...changes,
  };
}

async function preserve(db, number, payload, {
  day = number,
  collected = `2026-09-${String(day).padStart(2, "0")}T10:00:00Z`,
  created = collected,
  type = "pncp_contrato",
} = {}) {
  const serialized = JSON.stringify(payload);
  await db.query(`
    insert into raw.raw_records values ($1, $2, $3, $4, $5, $6)
  `, [recordId(number), type, serialized,
    createHash("sha256").update(serialized).digest("hex"), collected, created]);
}

async function normalize(db, limit = 500) {
  return (await db.query("select * from procurement.normalize_pncp_contracts($1)", [limit])).rows[0];
}

async function contracts(db) {
  return (await db.query(`
    select external_id, origin_raw_record_id, version, supersedes_id,
           current_amount::text as amount
    from procurement.contracts order by external_id, version
  `)).rows;
}



const publishMigration=await readFile(new URL('../../supabase/migrations/20260916131458_publish_social_fund_pair.sql',import.meta.url),'utf8');
const parentKey='13250888000162-1-000003/2026',contractKey='13654405000195-2-000023/2026';
const urls=['https://pncp.gov.br/api/pncp/v1/orgaos/13654405000195/contratos/2026/23','https://pncp.gov.br/api/consulta/v1/orgaos/13250888000162/compras/2026/3'];
async function setup(t){
 const db=await databaseFor(t);
 await db.exec(`create schema extensions;create extension pgcrypto with schema extensions;
 create table raw.raw_artifacts(id uuid primary key default gen_random_uuid(),sha256 text,byte_size bigint,source_url text,http_status int,retrieved_at timestamptz default now(),metadata jsonb default '{}');
 alter table raw.raw_records alter column id set default gen_random_uuid();
 alter table raw.raw_records alter column created_at set default now();
 alter table raw.raw_records add column raw_artifact_id uuid references raw.raw_artifacts;
 alter table raw.raw_records add column source_record_key text;
 alter table raw.raw_records add column record_index int;
 alter table raw.raw_records add column parser_version text;
 alter table raw.raw_records add column idempotency_key text unique;
 alter table org.public_bodies alter column id set default gen_random_uuid();
 alter table org.public_bodies alter column version set default 1;
 alter table org.public_bodies add column origin_raw_record_id uuid;
 alter table org.public_bodies add column name text;
 alter table org.public_bodies add column jurisdiction text;
 alter table org.public_bodies add column state_code text;`);
 await db.exec(publishMigration);
 await db.exec(await readFile(new URL('../../supabase/migrations/20260916133316_scope_social_fund_normalization.sql',import.meta.url),'utf8'));
 const data=[contract(contractKey,{numeroControlePNCPCompra:parentKey,valorInicial:28780,valorGlobal:28780}),{numeroControlePNCP:parentKey,orgaoEntidade:{cnpj:'13250888000162',razaoSocial:'FUNDO MUNICIPAL DE ASSISTENCIA SOCIAL'},unidadeOrgao:{codigoIbge:'2903201'},valorTotalEstimado:28780,objetoCompra:'Objeto oficial'}];
 const bodies=data.map(x=>Buffer.from(JSON.stringify(x))),ids=[];
 for(let i=0;i<2;i++)ids.push((await db.query("insert into raw.raw_artifacts(sha256,byte_size,source_url,http_status,metadata) values($1,$2,$3,200,$4) returning id",[createHash('sha256').update(bodies[i]).digest('hex'),bodies[i].length,urls[i],JSON.stringify({schema_name:'pncp-registry-snapshot',final_url:urls[i]})])).rows[0].id);
 return {db,bodies,ids};
}
async function publish({db,bodies,ids}){return (await db.query("select procurement.publish_social_fund_pair($1,$2,$3,$4) result",[ids[0],bodies[0],ids[1],bodies[1]])).rows[0].result;}
test('publicação atômica conserva órgãos distintos, valor e repetição sem duplicação',async t=>{
 const f=await setup(t);const result=await publish(f);assert.equal(result.contracts,1);
 const row=(await f.db.query("select c.current_amount::text amount,c.public_body_id<>p.public_body_id distinct_owners from procurement.contracts c join procurement.procurements p on p.id=c.procurement_id")).rows[0];
 assert.deepEqual(row,{amount:'28780',distinct_owners:true});
 assert.deepEqual(await publish(f),result);
 assert.equal((await f.db.query("select count(*)::int n from procurement.contracts")).rows[0].n,1);
});
test('bytes adulterados bloqueiam antes de inserir registros',async t=>{
 const f=await setup(t);f.bodies[0]=Buffer.from('{}');await assert.rejects(publish(f));
 assert.equal((await f.db.query("select count(*)::int n from raw.raw_records")).rows[0].n,0);
});
test('origem incompatível bloqueia publicação mesmo com hash válido',async t=>{
 const f=await setup(t);await f.db.query("update raw.raw_artifacts set source_url='https://example.invalid' where id=$1",[f.ids[1]]);
 await assert.rejects(publish(f));assert.equal((await f.db.query("select count(*)::int n from procurement.contracts")).rows[0].n,0);
});
test('anon não publica e worker só recebe a função delimitada',async t=>{
 const f=await setup(t);
 const row=(await f.db.query("select has_function_privilege('anon','procurement.publish_social_fund_pair(uuid,bytea,uuid,bytea)','execute') a,has_function_privilege('collector_worker','procurement.publish_social_fund_pair(uuid,bytea,uuid,bytea)','execute') w")).rows[0];
 assert.deepEqual(row,{a:false,w:true});
});
test('compra pendente fora do lote não bloqueia nem é publicada por este importador',async t=>{
 const f=await setup(t);
 const payload={numeroControlePNCP:'13654405000195-1-009999/2026',orgaoEntidade:{cnpj:'13654405000195'},objetoCompra:'Compra fora do lote'};
 await f.db.query("insert into raw.raw_records(record_type,payload,payload_sha256,collected_at) values('pncp_contratacao',$1,$2,now())",[JSON.stringify(payload),'a'.repeat(64)]);
 assert.equal((await publish(f)).status,'published');
 assert.equal((await f.db.query("select count(*)::int n from procurement.procurements where external_id='13654405000195-1-009999/2026'")).rows[0].n,0);
});
test('valor divergente com bytes íntegros não publica',async t=>{
 const f=await setup(t);
 const payload=JSON.parse(f.bodies[0].toString());payload.valorGlobal=28781;
 f.bodies[0]=Buffer.from(JSON.stringify(payload));
 await f.db.query('update raw.raw_artifacts set sha256=$1,byte_size=$2 where id=$3',[createHash('sha256').update(f.bodies[0]).digest('hex'),f.bodies[0].length,f.ids[0]]);
 await assert.rejects(publish(f),/valores divergentes/);
 assert.equal((await f.db.query('select count(*)::int n from raw.raw_records')).rows[0].n,0);
});
test('falha posterior à inserção reverte também os registros brutos e o Fundo',async t=>{
 const f=await setup(t);
 await f.db.exec(`create or replace function procurement.normalize_pncp_social_fund_pair(p_limit integer default 500)
 returns table(procurements_inserted integer,suppliers_inserted integer,contracts_inserted integer,contracts_skipped integer)
 language sql as 'select 2,0,1,0';`);
 await assert.rejects(publish(f),/excedeu o lote/);
 assert.equal((await f.db.query('select count(*)::int n from raw.raw_records')).rows[0].n,0);
 assert.equal((await f.db.query("select count(*)::int n from org.public_bodies where official_code='13250888000162'")).rows[0].n,0);
});
