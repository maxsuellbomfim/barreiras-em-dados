import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { PGlite } from "@electric-sql/pglite";

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
  const db = new PGlite();
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


const fundId = "10000000-0000-0000-0000-000000000002";
const parent = "13250888000162-1-000003/2026";
const key = "13654405000195-2-000023/2026";
async function fund(db) {
  await db.query("insert into org.public_bodies values ($1,'13250888000162','2903201','other',null,1)",[fundId]);
}
async function pair(db) {
  await preserve(db,1,contract(parent,{orgaoEntidade:{cnpj:"13250888000162"},objetoCompra:"Compra oficial"}),{type:"pncp_contratacao"});
  await preserve(db,2,contract(key,{numeroControlePNCPCompra:parent,valorGlobal:28780}));
}
test("órgão ainda não cadastrado não é substituído pela Prefeitura",async t=>{
 const db=await databaseFor(t); await pair(db); await normalize(db);
 assert.equal((await db.query("select count(*)::int n from procurement.procurements")).rows[0].n,0);
 assert.equal((await db.query("select procurement_id from procurement.contracts")).rows[0].procurement_id,null);
});
test("dois órgãos cadastrados conservam CNPJs e vínculo oficial sem duplicação",async t=>{
 const db=await databaseFor(t); await fund(db); await pair(db); await normalize(db);
 const row=(await db.query("select c.public_body_id contractor,p.public_body_id buyer,c.current_amount::text amount from procurement.contracts c join procurement.procurements p on p.id=c.procurement_id")).rows[0];
 assert.deepEqual(row,{contractor:bodyId,buyer:fundId,amount:"28780"});
 assert.deepEqual(await normalize(db),totals(0));
});
test("cadastro tardio do Fundo repara vínculo com nova versão, sem mudar o bruto",async t=>{
 const db=await databaseFor(t); await pair(db); await normalize(db);
 const old=(await db.query("select id from procurement.contracts")).rows[0].id;
 await fund(db); await normalize(db);
 const rows=(await db.query("select supersedes_id, procurement_id from procurement.contracts order by version")).rows;
 assert.equal(rows.length,2); assert.equal(rows[1].supersedes_id,old); assert.ok(rows[1].procurement_id);
 assert.deepEqual(await normalize(db),totals(0));
});
test("IBGE sozinho, CNPJ ambíguo ou controle de outro dono não autorizam órgão",async t=>{
 const db=await databaseFor(t);
 await preserve(db,1,contract("99999999000199-2-000001/2026",{orgaoEntidade:{cnpj:"99999999000199"}}));
 await preserve(db,2,contract("13250888000162-2-000002/2026"));
 await normalize(db); assert.equal((await contracts(db)).length,0);
 await fund(db);
 await db.exec("insert into org.public_bodies select '10000000-0000-0000-0000-000000000003',official_code,ibge_code,body_type,null,2 from org.public_bodies where official_code='13250888000162'");
 await preserve(db,3,contract("13250888000162-2-000003/2026",{orgaoEntidade:{cnpj:"13250888000162"}}));
 await normalize(db); assert.equal((await contracts(db)).length,0);
});
test("cadastro legado explícito da Prefeitura continua aceito",async t=>{
 const db=await databaseFor(t); await db.exec("update org.public_bodies set official_code='PREF-BARREIRAS'");
 await preserve(db,1,contract(key)); assert.deepEqual(await normalize(db),totals(1));
});
test("campos de contratação-pai conflitantes não geram vínculo presumido",async t=>{
 const db=await databaseFor(t); await fund(db); await pair(db);
 await preserve(db,3,contract(key,{numeroControlePNCPCompra:parent,numeroControlePncpCompra:"13654405000195-1-000001/2026"}));
 await normalize(db); assert.equal((await contracts(db)).length,0);
});
test("corrige atribuição antiga por nova versão e conserva o histórico",async t=>{
 const db=await databaseFor(t); await db.exec(previousMigration); await pair(db); await normalize(db);
 const old=(await db.query("select id from procurement.procurements")).rows[0].id;
 await fund(db); await db.exec(migration); await normalize(db);
 const rows=(await db.query("select public_body_id,supersedes_id from procurement.procurements order by version")).rows;
 assert.deepEqual(rows,[{public_body_id:bodyId,supersedes_id:null},{public_body_id:fundId,supersedes_id:old}]);
 assert.deepEqual(await normalize(db),totals(0));
});
test("snapshot novo não regride e a repetição não duplica o contrato",async t=>{
 const db=await databaseFor(t); await fund(db); await pair(db);
 await preserve(db,3,contract(key,{numeroControlePNCPCompra:parent,valorGlobal:30000}));
 await normalize(db); assert.equal((await contracts(db))[0].amount,"30000");
 assert.deepEqual(await normalize(db),totals(0));
});
test("resolução de órgãos e pais não abre acesso público",async t=>{
 const db=await databaseFor(t);
 for(const fn of ["pncp_owner_body(text)","pncp_parent_procurement(text)"]) {
   const row=(await db.query("select has_function_privilege('anon',$1,'execute') a,has_function_privilege('authenticated',$1,'execute') b",["procurement."+fn])).rows[0];
   assert.deepEqual(row,{a:false,b:false});
 }
});
