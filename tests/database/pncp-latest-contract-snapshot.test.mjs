import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { PGlite } from "@electric-sql/pglite";

const originalMigration = await readFile(new URL(
  "../../supabase/migrations/20260803170212_normalize_pncp_contracts.sql",
  import.meta.url,
), "utf8");
const migration = await readFile(new URL(
  "../../supabase/migrations/20260915154500_pncp_latest_contract_snapshot.sql",
  import.meta.url,
), "utf8");

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

test("contrato PNCP usa somente o snapshot mais recente por chave oficial", async (t) => {
  const db = await databaseFor(t);
  await preserve(db, 1, contract("PNCP-A", { valorGlobal: 100 }));
  await preserve(db, 2, contract("PNCP-A", { valorGlobal: 250 }));
  assert.deepEqual(await normalize(db), totals(1));
  assert.deepEqual(await contracts(db), [{
    external_id: "PNCP-A", origin_raw_record_id: recordId(2), version: 1,
    supersedes_id: null, amount: "250",
  }]);
});

test("repetir o lote não recria contratos nem faz oscilar fornecedores", async (t) => {
  const db = await databaseFor(t);
  const supplier = { niFornecedor: "12.345.678/0001-99", tipoPessoa: "PJ" };
  await preserve(db, 1, contract("PNCP-A", {
    ...supplier, nomeRazaoSocialFornecedor: "Fornecedor histórico", valorGlobal: 100,
  }));
  await preserve(db, 2, contract("PNCP-A", {
    ...supplier, nomeRazaoSocialFornecedor: "Fornecedor atual", valorGlobal: 200,
  }));
  await preserve(db, 3, contract("PNCP-B", {
    ...supplier, nomeRazaoSocialFornecedor: "Outra grafia publicada", valorGlobal: 300,
  }));
  await normalize(db);
  const before = await contracts(db);
  const suppliersBefore = (await db.query("select count(*)::integer as count from procurement.suppliers")).rows[0].count;
  assert.deepEqual(await normalize(db), totals(0));
  assert.deepEqual(await contracts(db), before);
  assert.equal((await db.query("select count(*)::integer as count from procurement.suppliers")).rows[0].count, suppliersBefore);
});

test("alteração nova cria uma versão e preserva a linhagem normalizada anterior", async (t) => {
  const db = await databaseFor(t);
  await preserve(db, 1, contract("PNCP-A"));
  assert.deepEqual(await normalize(db), totals(1));
  const first = (await db.query("select id from procurement.contracts")).rows[0].id;
  await preserve(db, 2, contract("PNCP-A", { valorGlobal: 400 }));
  assert.deepEqual(await normalize(db), totals(1));
  await preserve(db, 3, contract("PNCP-A", { valorGlobal: 400 }));
  assert.deepEqual(await normalize(db), totals(0));
  assert.deepEqual(await contracts(db), [
    { external_id: "PNCP-A", origin_raw_record_id: recordId(1), version: 1, supersedes_id: null, amount: "100" },
    { external_id: "PNCP-A", origin_raw_record_id: recordId(2), version: 2, supersedes_id: first, amount: "400" },
  ]);
});

test("correção restaura o snapshot atual sem apagar versões históricas já criadas", async (t) => {
  const db = await databaseFor(t, { applyCorrection: false });
  await preserve(db, 1, contract("PNCP-A", { valorGlobal: 100 }));
  await preserve(db, 2, contract("PNCP-A", { valorGlobal: 200 }));
  assert.deepEqual(await normalize(db), totals(2));
  const historical = await contracts(db);
  assert.equal(historical.at(-1).origin_raw_record_id, recordId(1));
  const previous = (await db.query("select id from procurement.contracts where version = 2")).rows[0].id;
  await db.exec(migration);
  assert.deepEqual(await normalize(db), totals(1));
  const corrected = await contracts(db);
  assert.deepEqual(corrected.slice(0, 2), historical);
  assert.deepEqual(corrected[2], {
    external_id: "PNCP-A", origin_raw_record_id: recordId(2), version: 3,
    supersedes_id: previous, amount: "200",
  });
  assert.deepEqual(await normalize(db), totals(0));
});

test("as duas grafias oficiais e espaços laterais convergem para a mesma chave", async (t) => {
  const db = await databaseFor(t);
  await preserve(db, 1, contract(" PNCP-A "));
  await preserve(db, 2, contract(" ", { numeroControlePncp: "PNCP-A", valorGlobal: 500 }));
  assert.deepEqual(await normalize(db), totals(1));
  assert.equal((await contracts(db))[0].origin_raw_record_id, recordId(2));
  assert.equal((await contracts(db))[0].external_id, "PNCP-A");
});

test("desempate usa coleta, criação e id de forma determinística", async (t) => {
  const db = await databaseFor(t);
  await preserve(db, 1, contract("PNCP-A", { valorGlobal: 1 }), { day: 10, created: "2026-09-10T11:00:00Z" });
  await preserve(db, 3, contract("PNCP-A", { valorGlobal: 3 }), { day: 10, created: "2026-09-10T12:00:00Z" });
  await preserve(db, 2, contract("PNCP-A", { valorGlobal: 2 }), { day: 10, created: "2026-09-10T12:00:00Z" });
  await preserve(db, 4, contract("PNCP-A", { valorGlobal: 4 }), { day: 9, created: "2026-09-11T12:00:00Z" });
  assert.deepEqual(await normalize(db), totals(1));
  assert.equal((await contracts(db))[0].origin_raw_record_id, recordId(3));
});

test("limite conta chaves recentes pendentes sem deixar versões antigas estagnadas", async (t) => {
  const db = await databaseFor(t);
  await preserve(db, 1, contract("PNCP-A"));
  await preserve(db, 2, contract("PNCP-B"));
  await preserve(db, 3, contract("PNCP-C"));
  await preserve(db, 4, contract("PNCP-C", { valorGlobal: 400 }));
  assert.deepEqual(await normalize(db, 2), totals(2));
  assert.deepEqual((await contracts(db)).map((row) => row.external_id), ["PNCP-B", "PNCP-C"]);
  assert.deepEqual(await normalize(db, 2), totals(1));
  assert.deepEqual(await normalize(db, 2), totals(0));
  assert.equal((await contracts(db)).length, 3);
});

test("limites zero, negativo e nulo preservam o contrato existente de lote", async (t) => {
  const db = await databaseFor(t);
  await preserve(db, 1, contract("PNCP-A"));
  await preserve(db, 2, contract("PNCP-B"));
  await preserve(db, 3, contract("PNCP-C"));
  assert.deepEqual(await normalize(db, 0), totals(1));
  assert.deepEqual(await normalize(db, -10), totals(1));
  assert.deepEqual(await normalize(db, null), totals(1));
  assert.deepEqual(await normalize(db, 5001), totals(0));
});

test("registro fora do território não substitui o snapshot válido de Barreiras", async (t) => {
  const db = await databaseFor(t);
  await preserve(db, 1, contract("PNCP-A"));
  await preserve(db, 2, contract("PNCP-A", {
    orgaoEntidade: { cnpj: "99999999000199" }, unidadeOrgao: { codigoIbge: "0000000" },
    valorGlobal: 900,
  }));
  await preserve(db, 3, contract("PNCP-B", {
    orgaoEntidade: { cnpj: "99999999000199" }, unidadeOrgao: { codigoIbge: "0000000" },
  }));
  assert.deepEqual(await normalize(db), totals(1));
  assert.equal((await contracts(db))[0].origin_raw_record_id, recordId(1));
});

test("controle ausente é contabilizado sem publicar contrato ou fornecedor", async (t) => {
  const db = await databaseFor(t);
  await preserve(db, 1, contract(" ", {
    numeroControlePncp: "", niFornecedor: "12345678000199", nomeRazaoSocialFornecedor: "Sem chave oficial",
  }));
  assert.deepEqual(await normalize(db), totals(0, 0, 1));
  assert.deepEqual(await contracts(db), []);
  assert.equal((await db.query("select count(*)::integer as count from procurement.suppliers")).rows[0].count, 0);
});

test("controles ausentes recentes não bloqueiam a chave válida com limite um", async (t) => {
  const db = await databaseFor(t);
  await preserve(db, 1, contract("PNCP-A"));
  await preserve(db, 2, contract("PNCP-B"));
  const invalid = contract(" ", {
    niFornecedor: "12345678000199", nomeRazaoSocialFornecedor: "Sem controle",
  });
  await preserve(db, 3, invalid);
  await preserve(db, 4, invalid);
  assert.deepEqual(await normalize(db, 1), totals(1, 0, 1));
  assert.equal((await contracts(db))[0].external_id, "PNCP-B");
  assert.deepEqual(await normalize(db, 1), totals(1, 0, 1));
  assert.deepEqual(await normalize(db, 1), totals(0, 0, 1));
  assert.equal((await contracts(db)).length, 2);
  assert.equal((await db.query("select count(*)::integer as count from procurement.suppliers")).rows[0].count, 0);
});

test("valores, contratação-pai, CNPJ e origem continuam oficiais", async (t) => {
  const db = await databaseFor(t);
  await preserve(db, 1, contract("COMPRA-1", { objetoCompra: "Objeto da contratação" }), { type: "pncp_contratacao" });
  await preserve(db, 2, contract("PNCP-A", {
    numeroControlePNCPCompra: "COMPRA-1", numeroContratoEmpenho: "42/2026",
    niFornecedor: "12.345.678/0001-99", tipoPessoa: "PJ", nomeRazaoSocialFornecedor: "Empresa oficial",
    valorInicial: 125.50, valorAcumulado: 175.25, valorGlobal: 999,
    dataAssinatura: "2026-09-01", dataVigenciaInicio: "2026-09-02", dataVigenciaFim: "2027-09-02",
  }));
  assert.deepEqual(await normalize(db), totals(1, 1, 0, 1));
  const actual = (await db.query(`
    select c.origin_raw_record_id, p.external_id as parent, c.contract_number,
           c.initial_amount::text, c.current_amount::text,
           s.public_registration_type, s.public_registration_number
    from procurement.contracts c
    join procurement.procurements p on p.id = c.procurement_id
    join procurement.suppliers s on s.id = c.supplier_id
  `)).rows[0];
  assert.deepEqual(actual, {
    origin_raw_record_id: recordId(2), parent: "COMPRA-1", contract_number: "42/2026",
    initial_amount: "125.5", current_amount: "175.25",
    public_registration_type: "CNPJ", public_registration_number: "12345678000199",
  });
  assert.deepEqual(await normalize(db), totals(0));
});

test("função continua restrita ao worker e usa search_path fechado", async (t) => {
  const db = await databaseFor(t);
  const actual = (await db.query(`
    select has_function_privilege('anon', 'procurement.normalize_pncp_contracts(integer)', 'EXECUTE') as anon,
           has_function_privilege('authenticated', 'procurement.normalize_pncp_contracts(integer)', 'EXECUTE') as authenticated,
           has_function_privilege('collector_worker', 'procurement.normalize_pncp_contracts(integer)', 'EXECUTE') as worker,
           prosecdef, proconfig
    from pg_proc where oid = 'procurement.normalize_pncp_contracts(integer)'::regprocedure
  `)).rows[0];
  assert.deepEqual(actual, {
    anon: false, authenticated: false, worker: true,
    prosecdef: true, proconfig: ["search_path=pg_catalog"],
  });
});
