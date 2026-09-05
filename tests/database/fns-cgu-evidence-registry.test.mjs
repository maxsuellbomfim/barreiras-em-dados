import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { PGlite } from "@electric-sql/pglite";

const migration = await readFile(new URL(
  "../../supabase/migrations/20260905040239_fns_cgu_evidence_registry.sql", import.meta.url,
), "utf8");
const key = "d".repeat(64);
const code = "257001000012025OB055607";

async function setup() {
  const db = new PGlite();
  await db.exec(`
    create role anon nologin;
    create role authenticated nologin;
    create role service_role nologin bypassrls;
    create schema source; create schema raw; create schema audit;
    create schema territory; create schema api;
    grant usage on schema api to anon, authenticated;
    grant usage on schema source to anon, authenticated, service_role;
    create function audit.reject_mutation() returns trigger language plpgsql as $$
      begin raise exception 'immutable'; end;
    $$;
    create table raw.raw_artifacts (
      id uuid primary key, sha256 text not null, source_url text not null,
      http_status smallint, byte_size bigint, artifact_kind text, content_type text
    );
    create table raw.raw_records (
      id uuid primary key, raw_artifact_id uuid references raw.raw_artifacts(id),
      record_type text, payload jsonb
    );
    create table territory.cgu_federal_amendment_documents (
      raw_record_id uuid, raw_artifact_id uuid, artifact_sha256 text,
      document_code text, amendment_code text, amendment_year smallint,
      document_date date, paid_amount numeric(20,2), author_name text,
      author_kind text, expense_stage text, source_row_number integer
    );
    insert into raw.raw_artifacts values
      ('00000000-0000-0000-0000-000000000001', repeat('a',64),
       'https://consultafns.saude.gov.br/recursos/consulta-detalhada/detalhe-pagamento?ano=2025',
       200, 100, 'http_response', 'application/json'),
      ('00000000-0000-0000-0000-000000000002', repeat('b',64),
       'https://consultafns.saude.gov.br/recursos/consulta-detalhada/detalhe-ordem-bancaria?ano=2025',
       200, 100, 'http_response', 'application/json'),
      ('00000000-0000-0000-0000-000000000003', repeat('c',64),
       'https://dadosabertos-download.cgu.gov.br/PortalDaTransparencia/saida/emendas-parlamentares-documentos/2025_EmendasParlamentaresPorDocumento.zip',
       200, 100, 'archive', 'application/zip');
    insert into raw.raw_records values (
      '00000000-0000-0000-0000-000000000004',
      '00000000-0000-0000-0000-000000000003', 'cgu_federal_amendment_document',
      '{"document_code":"${code}","amendment_code":"202550410002",
        "amendment_year":2025,"document_date":"2025-10-24","paid_amount":"5000000.00",
        "author_name":"COM. DA SAUDE","municipality_ibge":"2903201",
        "beneficiary_code":"08595187000125","expense_stage":"payment",
        "source_row_number":281848}');
    insert into territory.cgu_federal_amendment_documents values (
      '00000000-0000-0000-0000-000000000004',
      '00000000-0000-0000-0000-000000000003', repeat('c',64),
      '${code}', '202550410002', 2025, '2025-10-24', 5000000,
      'COM. DA SAUDE', 'commission', 'payment', 281848
    );
  `);
  await db.exec(migration);
  const relation = await db.query("select to_regclass('source.fns_cgu_evidence')::text as name");
  assert.equal(relation.rows[0].name, "source.fns_cgu_evidence");
  return db;
}

async function insertEvidence(db, overrides = {}) {
  const row = {
    reconciliation_key: key,
    payment_artifact_id: "00000000-0000-0000-0000-000000000001",
    order_artifact_id: "00000000-0000-0000-0000-000000000002",
    cgu_raw_record_id: "00000000-0000-0000-0000-000000000004",
    payment_sha256: "a".repeat(64), order_sha256: "b".repeat(64), cgu_archive_sha256: "c".repeat(64),
    document_code: code, amendment_code: "202550410002", amendment_year: 2025,
    document_date: "2025-10-24", paid_amount: "5000000.00", source_row_number: 281848,
    proposal_number: "36000703585202500", cgu_author_name: "COM. DA SAUDE",
    fns_author_name: "COMISSÃO DA SAÚDE", requester_name: "PARLAMENTAR EXEMPLO",
    requester_source_code: "4438", ...overrides,
  };
  const keys = Object.keys(row);
  return db.query(`insert into source.fns_cgu_evidence (${keys.join(",")}) values (${keys.map((_, i) => `$${i + 1}`).join(",")})`, Object.values(row));
}

async function decide(db, decision, target = key) {
  await db.query(`insert into source.fns_cgu_decisions
    (reconciliation_key, decision, reviewer_ref, review_note)
    values ($1,$2,'operator:test','Conferidos os originais e a reconciliação integral.')`, [target, decision]);
}

async function published(db) {
  await db.exec("set role anon");
  try {
    return (await db.query("select * from api.get_public_fns_cgu_links($1::text[])", [[code]])).rows;
  } finally { await db.exec("reset role"); }
}

test("FNS: evidência não publica sozinha; aprovação/revogação preservam histórico", async () => {
  const db = await setup();
  try {
    await insertEvidence(db);
    assert.deepEqual(await published(db), []);
    await decide(db, "approved");
    const rows = await published(db);
    assert.equal(rows.length, 1);
    assert.equal(rows[0].requester_name, "PARLAMENTAR EXEMPLO");
    assert.equal(rows[0].fns_author_name, "COMISSÃO DA SAÚDE");
    assert.equal(rows[0].cgu_archive_sha256, "c".repeat(64));
    assert.deepEqual(Object.keys(rows[0]).sort(), [
      "document_code", "cgu_archive_sha256", "requester_name", "fns_author_name",
      "payment_sha256", "order_sha256", "source_url", "reviewed_at", "methodology_version",
    ].sort());
    await decide(db, "revoked");
    assert.deepEqual(await published(db), []);
    assert.equal((await db.query("select count(*)::int n from source.fns_cgu_decisions")).rows[0].n, 2);
    assert.equal((await db.query("select paid_amount::text v from territory.cgu_federal_amendment_documents")).rows[0].v, "5000000.00");
  } finally { await db.close(); }
});

test("FNS: versão nova ou mudança na CGU invalidam a aprovação anterior", async () => {
  const db = await setup();
  try {
    await insertEvidence(db); await decide(db, "approved");
    await db.exec("update territory.cgu_federal_amendment_documents set artifact_sha256=repeat('f',64)");
    assert.deepEqual(await published(db), []);
    await db.exec("update territory.cgu_federal_amendment_documents set artifact_sha256=repeat('c',64), paid_amount=1");
    assert.deepEqual(await published(db), []);
    await db.exec("update territory.cgu_federal_amendment_documents set paid_amount=5000000");
    assert.equal((await published(db)).length, 1);
    await insertEvidence(db, { reconciliation_key: "e".repeat(64), requester_name: "OUTRO NOME" });
    assert.deepEqual(await published(db), []);
    await decide(db, "approved", "e".repeat(64));
    assert.equal((await published(db))[0].requester_name, "OUTRO NOME");
    await db.exec("insert into territory.cgu_federal_amendment_documents select * from territory.cgu_federal_amendment_documents");
    assert.deepEqual(await published(db), []);
  } finally { await db.close(); }
});

test("FNS: originais/valores divergentes são bloqueados e o registro é imutável", async () => {
  const db = await setup();
  try {
    for (const override of [
      { payment_sha256: "f".repeat(64) }, { order_sha256: "f".repeat(64) },
      { cgu_archive_sha256: "f".repeat(64) }, { paid_amount: "1.00" },
      { amendment_year: 2024 }, { document_date: "2025-10-25" },
      { source_row_number: 1 }, { requester_name: "CPF 12345678901" },
      { requester_name: "<b>EXEMPLO</b>" }, { requester_source_code: null },
    ]) await assert.rejects(insertEvidence(db, override));
    await insertEvidence(db);
    await assert.rejects(insertEvidence(db));
    await assert.rejects(db.exec("update source.fns_cgu_evidence set requester_name='TROCA'"));
    await assert.rejects(db.exec("delete from source.fns_cgu_evidence"));
    await decide(db, "approved");
    await assert.rejects(db.exec("update source.fns_cgu_decisions set decision='revoked'"));
    await assert.rejects(db.exec("delete from source.fns_cgu_decisions"));
    await db.exec("update raw.raw_artifacts set source_url='https://evil.example/data' where id='00000000-0000-0000-0000-000000000001'");
    assert.deepEqual(await published(db), []);
    await assert.rejects(insertEvidence(db, { reconciliation_key: "e".repeat(64) }));
  } finally { await db.close(); }
});

test("FNS: acesso comum não lê registro privado nem aprova; API tem limite", async () => {
  const db = await setup();
  try {
    await insertEvidence(db);
    for (const role of ["anon", "authenticated", "service_role"]) {
      await db.exec(`set role ${role}`);
      try {
        await assert.rejects(db.exec("select * from source.fns_cgu_evidence"));
        await assert.rejects(db.exec("select * from source.fns_cgu_decisions"));
        await assert.rejects(decide(db, "approved"));
      } finally { await db.exec("reset role"); }
    }
    await db.exec("set role anon");
    await assert.rejects(db.query("select * from api.get_public_fns_cgu_links($1::text[])", [Array(51).fill(code)]));
    await assert.rejects(db.query("select * from api.get_public_fns_cgu_links($1::text[])", [[null]]));
    await assert.rejects(db.query("select * from api.get_public_fns_cgu_links($1::text[])", [["invalid"]]));
    await db.exec("reset role");
  } finally { await db.close(); }
});
