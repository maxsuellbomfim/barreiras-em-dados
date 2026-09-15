import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import test from "node:test";
import { PGlite } from "@electric-sql/pglite";

const migrations = new URL("../../supabase/migrations/", import.meta.url);
const names = (await readdir(migrations)).filter(name=>name.endsWith("_pncp_contract_query_status.sql"));
assert.ok(names.length<=1,"single versioned projection migration");
const migration = names.length ? await readFile(new URL(names[0],migrations),"utf8") : null;
const id = n => `00000000-0000-4000-8000-${String(n).padStart(12,"0")}`;
const control = "13654405000195-1-000027/2026";
const hash = "a".repeat(64);
async function setup(t, seed) {
  const db = new PGlite(); t.after(()=>db.close());
  await db.exec(`create role anon; create role authenticated; create role collector_worker;
    create schema source; create schema raw; create schema api;
    grant usage on schema api to anon, authenticated;
    create table source.data_sources(id uuid primary key,slug text);
    create table source.source_endpoints(id uuid primary key,data_source_id uuid,slug text);
    create table source.collection_runs(id uuid primary key,source_endpoint_id uuid,status text,
      started_at timestamptz,completed_at timestamptz,cursor_after jsonb,metrics jsonb);
    create table raw.raw_artifacts(id uuid primary key,sha256 text,http_status int,metadata jsonb);
    insert into source.data_sources values ('${id(1)}','pncp');
    insert into source.source_endpoints values ('${id(2)}','${id(1)}','contratos-api');
    insert into raw.raw_artifacts values ('${id(3)}','${hash}',200,
      '{"schema_name":"pncp-contratos-page","cursor":{"ano":2026,"sequencial":27,"pagina":1}}');`);
  if(seed) await seed(db);
  if(migration) await db.exec(migration);
  else await db.exec(`create function api.get_pncp_contract_query_status(control_numbers text[])
    returns table(control_number text,state text,checked_at timestamptz,source_url text)
    language sql as $$select unnest(control_numbers),'unknown'::text,null::timestamptz,null::text$$;`);
  return db;
}
function observation(overrides={}) { return { version:1, scope:"pncp_contracts_query",control,
  started_at:"2026-09-15T10:00:01+00:00",finished_at:"2026-09-15T10:00:02+00:00",
  state:"query_complete",reason:null,http_status:null,response_page:null,records_preserved:2,
  pages:[{page:1,raw_artifact_id:id(3),sha256:hash,http_status:200,records:2}],...overrides }; }
async function run(db, number, {obs=[observation()], status="partial", start="2026-09-15T10:00:00Z", end="2026-09-15T10:00:03Z", cursor={}, extra={}}={}) {
  await db.query(`insert into source.collection_runs values($1,$2,$3,$4,$5,$6,$7)`,[id(number),id(2),status,start,end,JSON.stringify(cursor),JSON.stringify({control_plane:true,control_observations:obs,...extra})]);
}
async function read(db) { return (await db.query("select * from api.get_pncp_contract_query_status($1)",[[control]])).rows[0]; }

test("consulta completa expõe só estado, data e fonte; projeção é indexada",async t=>{
  const db=await setup(t); await run(db,10);
  const row=await read(db); assert.equal(row.state,"query_complete");
  assert.equal(new Date(row.checked_at).toISOString(),"2026-09-15T10:00:02.000Z");
  assert.equal(row.source_url,"https://pncp.gov.br/app/editais/13654405000195/2026/27");
  assert.deepEqual(Object.keys(row).sort(),["checked_at","control_number","source_url","state"]);
  assert.ok(!JSON.stringify(row).includes(hash));
  const {rows}=await db.query("select indexdef from pg_indexes where tablename='pncp_contract_query_status'");
  assert.ok(rows.some(r=>/UNIQUE.*control_number/.test(r.indexdef)));
});
test("vazio exige página preservada; 404 sem página é inconclusivo",async t=>{
  const db=await setup(t); await run(db,10,{obs:[observation({state:"empty_confirmed",records_preserved:0,pages:[{...observation().pages[0],records:0}]})]});
  assert.equal((await read(db)).state,"empty_confirmed");
  await run(db,11,{obs:[observation({state:"inconclusive",http_status:404,records_preserved:null,pages:[]})]});
  assert.equal((await read(db)).state,"inconclusive");
});
test("reserva nova e fechamento sem observação não reciclam sucesso antigo",async t=>{
  const db=await setup(t); await run(db,10);
  await run(db,11,{obs:[],status:"running",start:"2026-09-16T10:00:00Z",end:null,cursor:{cursor_version:1,retry_controls:[control]}});
  assert.equal((await read(db)).state,"pending"); assert.equal((await read(db)).checked_at,null);
  await db.query("update source.collection_runs set status='failed', completed_at='2026-09-16T10:05:00Z' where id=$1",[id(11)]);
  assert.equal((await read(db)).state,"pending");
  await db.query("update source.collection_runs set metrics=metrics where id=$1",[id(10)]);
  assert.equal((await read(db)).state,"pending");
});
test("fechamento da mesma execução substitui a reserva pela observação",async t=>{
  const db=await setup(t); await run(db,10,{obs:[],status:"running",end:null,cursor:{cursor_version:1,retry_controls:[control]}});
  assert.equal((await read(db)).state,"pending");
  await db.query("update source.collection_runs set status='partial',completed_at='2026-09-15T10:00:03Z',metrics=$2 where id=$1",[id(10),JSON.stringify({control_plane:true,control_observations:[observation()]})]);
  assert.equal((await read(db)).state,"query_complete");
});
test("evidências incompatíveis, duplicadas ou sem versão falham fechadas",async t=>{
  const db=await setup(t);
  const bad=[{version:2},{scope:"all_payments"},{records_preserved:3},{pages:[]},
    {pages:[{...observation().pages[0],sha256:"b".repeat(64)}]},
    {pages:[{...observation().pages[0],raw_artifact_id:id(999)}]},
    {pages:[{...observation().pages[0],page:2}]},
    {finished_at:"2026-09-20T10:00:00Z"},{state:"empty_confirmed"}];
  for(let i=0;i<bad.length;i++) { await run(db,100+i,{obs:[observation(bad[i])]}); assert.equal((await read(db)).state,"unknown",JSON.stringify(bad[i])); }
  await run(db,200,{obs:[observation(),observation()]}); assert.equal((await read(db)).state,"unknown");
});
test("artefato de outra contratação não comprova esta consulta",async t=>{
  const db=await setup(t); await db.exec("update raw.raw_artifacts set metadata=jsonb_set(metadata,'{cursor,sequencial}','99')");
  await run(db,10); assert.equal((await read(db)).state,"unknown");
});
test("sem observação e origem estranha não viram vazio ou não coletado",async t=>{
  const db=await setup(t); assert.equal((await read(db)).state,"unknown");
  await run(db,10,{extra:{control_plane:false}}); assert.equal((await read(db)).state,"unknown");
  await db.exec("update source.data_sources set slug='other'"); await run(db,11); assert.equal((await read(db)).state,"unknown");
});
test("público lê somente projeção limitada, não tabela ou função interna",async t=>{
  const db=await setup(t); await run(db,10); await db.exec("set role anon");
  assert.equal((await read(db)).state,"query_complete");
  await assert.rejects(db.exec("select * from source.pncp_contract_query_status"),/permission denied/);
  await assert.rejects(db.query("select * from api.get_pncp_contract_query_status($1)",[Array(61).fill(control)]),/60/);
  await assert.rejects(db.query("select * from api.get_pncp_contract_query_status($1)",[["invalid"]]),/invalid/i);
});
test("bootstrap normaliza o histórico auditável e respeita a reserva mais recente",async t=>{
  const db=await setup(t,async db=>{
    await run(db,10);
    await run(db,11,{obs:[],status:"running",start:"2026-09-16T10:00:00Z",end:null,cursor:{cursor_version:1,retry_controls:[control]}});
  });
  assert.equal((await read(db)).state,"pending");
});
test("telemetria malformada não aborta o coletor nem certifica sucesso",async t=>{
  const db=await setup(t); await run(db,10);
  await run(db,11,{obs:"invalid",cursor:{cursor_version:1,retry_controls:[control]}});
  assert.equal((await read(db)).state,"pending");
  await db.exec("update raw.raw_artifacts set metadata=jsonb_set(metadata,'{cursor,pagina}','\"bad\"')");
  await run(db,12); assert.equal((await read(db)).state,"unknown");
});
