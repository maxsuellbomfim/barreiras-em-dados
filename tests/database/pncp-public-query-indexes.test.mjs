import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { PGlite } from "@electric-sql/pglite";

const readMigration = (name) => readFile(new URL(`../../supabase/migrations/${name}`, import.meta.url), "utf8");
const publicMigration = await readMigration("20260809100000_public_pncp_items.sql");
const labelMigration = await readMigration("20260803142610_pncp_normalized_filtering.sql");
const indexMigration = await readMigration("20260915170000_pncp_public_query_indexes.sql").catch((error) => {
  if (error.code !== "ENOENT") throw error;
  // During RED, run the actual query against the unindexed fixture so that
  // the failure identifies the missing access path rather than a file error.
  return null;
});
const keyA = "13654405000195-1-000101/2026";
const keyB = "13654405000195-1-000102/2026";
const expectedIndexes = [
  "raw_records_pncp_procurement_lookup_idx",
  "raw_records_pncp_result_lookup_idx",
];

async function addRecord(db, type, payload, created) {
  await db.query("insert into raw.raw_records (record_type, payload, created_at) values ($1, $2, $3)",
    [type, JSON.stringify(payload), created]);
}

async function prepareDatabase(t) {
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
      record_type text not null, payload jsonb not null,
      created_at timestamptz not null
    );
    create table procurement.procurements (id uuid primary key, external_id text);
    create table procurement.procurement_items (
      id uuid primary key, procurement_id uuid references procurement.procurements,
      supersedes_id uuid references procurement.procurement_items,
      external_item_number text, description text, quantity numeric, unit_name text,
      estimated_unit_amount numeric, estimated_total_amount numeric,
      result_status text, catalog_code text, version integer, created_at timestamptz
    );
    -- Execution/ledger aggregation is deliberately outside this index test.
    -- The real public RPC and label helper are loaded unchanged below. This
    -- stable dependency is compared with every other returned JSON field.
    create function api.get_pncp_execution_summary(text) returns jsonb
      language sql stable set search_path = '' as $summary$
        select '{"state":"not_available","methodology_version":"fixture/execution-not-under-test","contracts_count":0,"commitments_count":0,"liquidations_count":0,"payments_count":0,"contract_current_amount":0,"committed_amount":0,"liquidated_amount":0,"paid_amount":0,"contracts":[],"evidence":[],"evidence_count":0}'::jsonb
      $summary$;
  `);
  const labelDefinition = labelMigration.match(/create or replace function api\.pncp_label_key\(value text\)[\s\S]*?\$function\$;/)?.[0];
  assert.ok(labelDefinition, "load the real shared label function");
  await db.exec(labelDefinition);
  await db.exec(publicMigration);

  const original = {
    numeroControlePNCP: keyA, anoCompra: 2026, sequencialCompra: 101,
    modalidadeNome: "Dispensa", situacaoCompraNome: "Homologada",
    unidadeOrgao: { nomeUnidade: "Secretaria de Saúde" },
    objetoCompra: "Equipamento antigo", valorTotalEstimado: 1000,
    valorTotalHomologado: 500, dataPublicacaoPncp: "2026-09-14",
  };
  await addRecord(db, "pncp_contratacao", original, "2026-09-13T10:00:00Z");
  await addRecord(db, "pncp_contratacao", {
    ...original, objetoCompra: "Equipamento médico publicado", valorTotalEstimado: 1200,
    valorTotalHomologado: 900,
  }, "2026-09-14T10:00:00Z");
  await addRecord(db, "pncp_contratacao", {
    ...original, numeroControlePNCP: keyB, sequencialCompra: 102,
    modalidadeNome: "Pregão", situacaoCompraNome: "Em andamento",
    unidadeOrgao: { nomeUnidade: "Secretaria de Obras" },
    objetoCompra: "Manutenção predial", valorTotalHomologado: null,
    dataPublicacaoPncp: "2026-09-15",
  }, "2026-09-15T10:00:00Z");
  const winner = {
    numeroControlePNCPCompra: keyA, numeroItem: 1, sequencialResultado: 1,
    nomeRazaoSocialFornecedor: "Empresa Oficial", tipoPessoa: "PJ",
    niFornecedor: "12345678000199", valorTotalHomologado: 400, dataResultado: "2026-09-14",
  };
  await addRecord(db, "pncp_resultado", winner, "2026-09-13T11:00:00Z");
  await addRecord(db, "pncp_resultado", { ...winner, valorTotalHomologado: 800 }, "2026-09-14T11:00:00Z");
  await addRecord(db, "pncp_resultado", {
    ...winner, numeroItem: 2, nomeRazaoSocialFornecedor: "Pessoa física de teste",
    tipoPessoa: "PF", niFornecedor: "00000000000", valorTotalHomologado: 100,
  }, "2026-09-14T12:00:00Z");
  await db.exec(`
    insert into procurement.procurements values ('10000000-0000-0000-0000-000000000001', '${keyA}');
    insert into procurement.procurement_items values
      ('20000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', null,
       '1', 'Descrição anterior', 1, 'UN', 400, 400, 'Homologado', 'CAT-1', 1, '2026-09-13'),
      ('20000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000001',
       '1', 'Equipamento médico oficial', 1, 'UN', 800, 800, 'Homologado', 'CAT-1', 2, '2026-09-14');
    -- Three thousand unrelated PNCP rows: actual predicate types and different
    -- official keys, not unrelated endpoints that would trivially disappear.
    insert into raw.raw_records (record_type, payload, created_at)
    select 'pncp_contratacao', jsonb_build_object(
      'numeroControlePNCP', '13654405000195-1-' || lpad(n::text, 6, '0') || '/2021',
      'anoCompra', 2021, 'sequencialCompra', n,
      'modalidadeNome', 'Pregão', 'situacaoCompraNome', 'Homologada',
      'unidadeOrgao', jsonb_build_object('nomeUnidade', 'Outra unidade'),
      'objetoCompra', 'Outro objeto ' || n, 'dataPublicacaoPncp', '2021-08-01'
    ), '2021-08-01'::timestamptz from generate_series(1, 1500) as n;
    insert into raw.raw_records (record_type, payload, created_at)
    select 'pncp_resultado', jsonb_build_object(
      'numeroControlePNCPCompra', '13654405000195-1-' || lpad(n::text, 6, '0') || '/2021',
      'numeroItem', 1, 'sequencialResultado', 1,
      'nomeRazaoSocialFornecedor', 'Outro fornecedor ' || n, 'tipoPessoa', 'PJ',
      'niFornecedor', '99999999000199', 'valorTotalHomologado', 50, 'dataResultado', '2021-08-01'
    ), '2021-08-01'::timestamptz from generate_series(1, 1500) as n;
    analyze raw.raw_records;
    analyze procurement.procurements;
    analyze procurement.procurement_items;
  `);
  return db;
}

const cases = [
  { name: "latest snapshots", args: [60, null, 2026, null, null, null, null], keys: [keyB, keyA] },
  {
    name: "unfiltered public page",
    args: [60, null, null, null, null, null, null],
    keys: [keyB, keyA, ...Array.from({ length: 58 }, (_, index) =>
      `13654405000195-1-${String(index + 1).padStart(6, "0")}/2021`)],
  },
  { name: "supplier CNPJ", args: [60, "12345678000199", 2026, null, null, null, null], keys: [keyA] },
  { name: "supplier normalized name", args: [60, "EMPRESA  OFICIAL", 2026, null, null, null, null], keys: [keyA] },
  { name: "normalized labels and search", args: [60, null, 2026, "médico", "dispensa", "HOMOLOGADA", " secretaria de saude "], keys: [keyA] },
  { name: "empty year", args: [60, null, 2027, null, null, null, null], keys: [] },
  { name: "empty filter", args: [60, null, 2026, "sem correspondência", null, null, null], keys: [] },
  { name: "page limit", args: [1, null, 2026, null, null, null, null], keys: [keyB] },
];

async function queryCases(db) {
  const results = [];
  for (const sample of cases) {
    const result = await db.query("select * from api.get_pncp_procurements_normalized($1, $2, $3::smallint, $4, $5, $6, $7)", sample.args);
    assert.deepEqual(result.rows.map((row) => row.control_number), sample.keys, sample.name);
    results.push(result.rows);
  }
  return results;
}

async function definitions(db) {
  return (await db.query(`
    select p.proname, pg_get_functiondef(p.oid) as definition, p.proacl::text as permissions
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'api' order by p.proname
  `)).rows;
}

async function explain(db, sql, values = []) {
  const rows = (await db.query(`explain (format json) ${sql}`, values)).rows;
  return rows[0]["QUERY PLAN"][0].Plan;
}

function indexNames(plan) {
  return [plan["Index Name"], ...(plan.Plans ?? []).flatMap(indexNames)].filter(Boolean);
}

function planSummary(plan) {
  const nodes = [plan, ...(plan.Plans ?? []).flatMap(function descendants(node) {
    return [node, ...(node.Plans ?? []).flatMap(descendants)];
  })];
  return JSON.stringify(nodes.filter((node) => node["Relation Name"] === "raw_records")
    .map((node) => ({ type: node["Node Type"], alias: node.Alias, index: node["Index Name"] ?? null })));
}

test("índices PNCP preservam a RPC pública e aceleram caminhos reais sem forçar o planejador", async (t) => {
  const db = await prepareDatabase(t);
  const before = await queryCases(db);
  const functionsBefore = await definitions(db);
  const rawBefore = (await db.query("select count(*)::integer as records, md5(string_agg(payload::text, '' order by id)) as checksum from raw.raw_records")).rows;
  assert.equal(rawBefore[0].records, 3006);

  await t.test("fixture conserva snapshot recente, item vigente, vencedor e máscara PF", () => {
    const latest = before[0].find((row) => row.control_number === keyA);
    assert.equal(latest.objeto, "Equipamento médico publicado");
    assert.equal(latest.valor_estimado, "1200");
    assert.equal(latest.valor_homologado, "900");
    assert.equal(latest.itens.length, 1);
    assert.equal(latest.itens[0].descricao, "Equipamento médico oficial");
    assert.equal(latest.resultados.length, 2);
    assert.equal(latest.resultados[0].valor_total_homologado, 800);
    assert.equal(latest.resultados[0].ni_fornecedor, "12345678000199");
    assert.equal(latest.resultados[1].tipo_pessoa, "PF");
    assert.equal(latest.resultados[1].ni_fornecedor, null);
    assert.equal(JSON.stringify(before).includes("00000000000"), false);
    const withoutResults = before[1].find((row) => row.control_number === keyB);
    assert.deepEqual(withoutResults.itens, []);
    assert.deepEqual(withoutResults.resultados, []);
  });

  if (indexMigration !== null) await db.exec(indexMigration);
  await db.exec("analyze raw.raw_records");

  await t.test("todos os campos, contagens, filtros, funções e permissões são idênticos", async () => {
    assert.deepEqual(await queryCases(db), before);
    assert.deepEqual(await definitions(db), functionsBefore);
    assert.deepEqual((await db.query("select count(*)::integer as records, md5(string_agg(payload::text, '' order by id)) as checksum from raw.raw_records")).rows, rawBefore);
  });

  await t.test("consultas por tipo e chave usam os dois índices naturalmente", async () => {
    const enabled = (await db.query("show enable_seqscan")).rows[0].enable_seqscan;
    assert.equal(enabled, "on");
    const procurementPlan = await explain(db, `
      select payload from raw.raw_records
      where record_type = 'pncp_contratacao' and payload ->> 'numeroControlePNCP' = $1
      order by created_at desc limit 1
    `, [keyA]);
    const resultPlan = await explain(db, `
      select payload from raw.raw_records
      where record_type = 'pncp_resultado' and payload ->> 'numeroControlePNCPCompra' = $1
      order by payload ->> 'numeroItem', payload ->> 'sequencialResultado', created_at desc
    `, [keyA]);
    assert.ok(indexNames(procurementPlan).includes(expectedIndexes[0]), planSummary(procurementPlan));
    assert.ok(indexNames(resultPlan).includes(expectedIndexes[1]), planSummary(resultPlan));
  });

  await t.test("RETURN QUERY real usa o índice de resultados para cada contratação selecionada", async () => {
    const select = publicMigration.match(/return query\s+([\s\S]*?);\s*end;\s*\$function\$;/)?.[1];
    assert.ok(select, "load the real SELECT from the public RPC");
    const bindings = {
      page_size: "$1::integer", supplier_key_filter: "$2::text", fiscal_year_filter: "$3::smallint",
      query_filter: "$4::text", modality_filter: "$5::text", status_filter: "$6::text", unit_filter: "$7::text",
    };
    const query = select.replace(/\b(page_size|supplier_key_filter|fiscal_year_filter|query_filter|modality_filter|status_filter|unit_filter)\b/g,
      (parameter) => bindings[parameter]);
    const plan = await explain(db, query, cases[1].args);
    assert.ok(indexNames(plan).includes(expectedIndexes[1]), planSummary(plan));
  });

  await t.test("migration cria somente os dois índices parciais previstos", async () => {
    const rows = (await db.query(`
      select indexname, indexdef from pg_indexes where schemaname = 'raw'
        and indexname <> 'raw_records_pkey' order by indexname
    `)).rows;
    assert.deepEqual(rows.map((row) => row.indexname), expectedIndexes);
    assert.match(rows[0].indexdef, /numeroControlePNCP/);
    assert.match(rows[0].indexdef, /created_at DESC/);
    assert.match(rows[0].indexdef, /WHERE \(record_type = 'pncp_contratacao'::text\)/);
    assert.match(rows[1].indexdef, /numeroControlePNCPCompra[\s\S]*numeroItem[\s\S]*sequencialResultado[\s\S]*created_at DESC/);
    assert.match(rows[1].indexdef, /WHERE \(record_type = 'pncp_resultado'::text\)/);
  });
});
