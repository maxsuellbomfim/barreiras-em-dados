import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { PGlite } from "@electric-sql/pglite";

const migrationFile = (name) => new URL(`../../supabase/migrations/${name}`, import.meta.url);
const original = await readFile(migrationFile("20260809100000_public_pncp_items.sql"), "utf8");
const labels = await readFile(migrationFile("20260803142610_pncp_normalized_filtering.sql"), "utf8");
const correction = await readFile(migrationFile("20260915183000_pncp_public_decimal_amounts.sql"), "utf8")
  .catch((error) => {
    if (error.code !== "ENOENT") throw error;
    // RED exercises the actual old RPC, not a missing-file exception.
    return null;
  });

const cases = [
  { label: "decimal numérico oficial", input: 1234.56, expected: "1234.56" },
  { label: "centavos no resultado", input: 800.25, expected: "800.25" },
  { label: "inteiro", input: 1234, expected: "1234" },
  { label: "zero oficial", input: 0, expected: "0" },
  { label: "decimal negativo", input: -12.75, expected: "-12.75" },
  { label: "inteiro negativo", input: -12, expected: "-12" },
  { label: "decimal textual com escala", input: "1234.5600", expected: "1234.5600" },
  { label: "inteiro textual", input: "1234", expected: "1234" },
  { label: "zero textual com escala", input: "0.00", expected: "0.00" },
  { label: "zeros iniciais legados", input: "00012.50", expected: "12.50" },
  { label: "decimal pequeno sem arredondar", input: "0.000001", expected: "0.000001" },
  { label: "numeric além da precisão Number sem perda no SQL", input: "999999999999999999.99", expected: "999999999999999999.99" },
  { label: "campo ausente", input: undefined, expected: null },
  { label: "nulo explícito", input: null, expected: null },
  { label: "texto vazio", input: "", expected: null },
  { label: "texto não numérico", input: "não informado", expected: null },
  { label: "símbolo monetário não aceito", input: "R$ 10.00", expected: null },
  { label: "vírgula não convertida silenciosamente", input: "1,25", expected: null },
  { label: "milhar localizado não reinterpretado", input: "1.234,56", expected: null },
  { label: "espaços não removidos silenciosamente", input: " 1.25 ", expected: null },
  { label: "sinal positivo fora do formato existente", input: "+1.25", expected: null },
  { label: "notação científica textual fora do formato", input: "1e3", expected: null },
  { label: "fração sem parte inteira", input: ".50", expected: null },
  { label: "ponto sem fração", input: "1.", expected: null },
  { label: "barra não representa ponto decimal", input: "12\\x34", expected: null },
];

async function setup(t) {
  const db = new PGlite();
  t.after(() => db.close());
  await db.exec(`
    create role anon;
    create role authenticated;
    create schema api;
    create schema raw;
    create schema procurement;
    create table raw.raw_records (
      id bigint generated always as identity primary key,
      record_type text not null, payload jsonb not null, created_at timestamptz not null
    );
    create table procurement.procurements (id uuid primary key, external_id text);
    create table procurement.procurement_items (
      id uuid primary key, procurement_id uuid, supersedes_id uuid,
      external_item_number text, description text, quantity numeric, unit_name text,
      estimated_unit_amount numeric, estimated_total_amount numeric,
      result_status text, catalog_code text, version integer, created_at timestamptz
    );
    -- Stable dependency only: these tests exercise the real public monetary
    -- decoding, not ledger/contract aggregation or any publishing decision.
    create function api.get_pncp_execution_summary(text) returns jsonb
      language sql stable set search_path = '' as $summary$
        select '{"state":"not_available","methodology_version":"fixture/execution-not-under-test"}'::jsonb
      $summary$;
  `);
  const labelFunction = labels.match(/create or replace function api\.pncp_label_key\(value text\)[\s\S]*?\$function\$;/)?.[0];
  assert.ok(labelFunction);
  await db.exec(labelFunction);
  await db.exec(original);
  for (const [index, sample] of cases.entries()) {
    const control = `13654405000195-1-${String(index + 1).padStart(6, "0")}/2026`;
    const marker = `CASE-${String(index).padStart(2, "0")}-END`;
    const purchase = {
      numeroControlePNCP: control, anoCompra: 2026, sequencialCompra: index + 1,
      modalidadeNome: "Dispensa", situacaoCompraNome: "Homologada",
      objetoCompra: marker, unidadeOrgao: { nomeUnidade: "Unidade de teste" },
      dataPublicacaoPncp: "2026-09-15",
      valorTotalEstimado: sample.input, valorTotalHomologado: sample.input,
    };
    const winner = {
      numeroControlePNCPCompra: control, numeroItem: 1, sequencialResultado: 1,
      nomeRazaoSocialFornecedor: "Fornecedor de teste", tipoPessoa: "PJ",
      niFornecedor: "12345678000199", dataResultado: "2026-09-15",
      valorTotalHomologado: sample.input,
    };
    for (const [type, payload] of [["pncp_contratacao", purchase], ["pncp_resultado", winner]]) {
      await db.query("insert into raw.raw_records (record_type, payload, created_at) values ($1, $2, '2026-09-15T12:00:00Z')",
        [type, JSON.stringify(payload)]);
    }
  }
  return db;
}

async function contract(db) {
  return (await db.query(`
    select p.oid::text as oid, pg_get_function_identity_arguments(p.oid) as arguments,
           pg_get_function_result(p.oid) as result, p.proacl::text as permissions,
           p.provolatile, p.prosecdef, p.proconfig
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'api' and p.proname = 'get_pncp_procurements_normalized'
  `)).rows;
}

async function rawState(db) {
  return (await db.query("select count(*)::integer as count, md5(string_agg(payload::text, '' order by id)) as checksum from raw.raw_records")).rows;
}

test("RPC PNCP preserva centavos oficiais sem reinterpretar formatos inválidos", async (t) => {
  const db = await setup(t);
  const beforeContract = await contract(db);
  const beforeRaw = await rawState(db);
  const beforeBody = (await db.query("select prosrc from pg_proc where oid = 'api.get_pncp_procurements_normalized(integer,text,smallint,text,text,text,text)'::regprocedure")).rows[0].prosrc;
  if (correction !== null) await db.exec(correction);

  for (const [index, sample] of cases.entries()) {
    await t.test(sample.label, async () => {
      const rows = (await db.query(`
        select p.valor_estimado::text as estimated,
               p.valor_homologado::text as awarded,
               p.resultados -> 0 ->> 'valor_total_homologado' as winner_amount,
               jsonb_array_length(p.resultados) as winners,
               p.methodology_version,
               pg_typeof(p.valor_estimado)::text as amount_type
        from api.get_pncp_procurements_normalized(60, null, 2026::smallint, $1, null, null, null) p
      `, [`CASE-${String(index).padStart(2, "0")}-END`])).rows;
      assert.deepEqual(rows, [{
        estimated: sample.expected, awarded: sample.expected, winner_amount: sample.expected,
        winners: 1, methodology_version: "pncp-procurements/1.5.0", amount_type: "numeric",
      }]);
    });
  }

  await t.test("correção conserva OID, assinatura, tipagem, permissões e dados brutos", async () => {
    assert.deepEqual(await contract(db), beforeContract);
    assert.deepEqual(await rawState(db), beforeRaw);
    const privileges = (await db.query(`
      select has_function_privilege('anon', 'api.get_pncp_procurements_normalized(integer,text,smallint,text,text,text,text)', 'execute') as anon,
             has_function_privilege('authenticated', 'api.get_pncp_procurements_normalized(integer,text,smallint,text,text,text,text)', 'execute') as authenticated
    `)).rows;
    assert.deepEqual(privileges, [{ anon: true, authenticated: true }]);
  });

  await t.test("somente as três regex monetárias mudam no corpo da função", async () => {
    const patterns = [...beforeBody.matchAll(/->> '(?:valorTotalEstimado|valorTotalHomologado)' ~ '([^']+)'/g)].map((match) => match[1]);
    assert.equal(patterns.length, 3);
    assert.equal(new Set(patterns).size, 1);
    const afterBody = (await db.query("select prosrc from pg_proc where oid = 'api.get_pncp_procurements_normalized(integer,text,smallint,text,text,text,text)'::regprocedure")).rows[0].prosrc;
    assert.ok(afterBody === beforeBody.replaceAll(patterns[0], "^-?[0-9]+([.][0-9]+)?$"),
      "the complete SQL body must change only the three monetary guards");
  });
});
