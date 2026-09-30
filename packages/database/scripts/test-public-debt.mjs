import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile, readdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { PGlite } from "@electric-sql/pglite";
import { pg_trgm } from "@electric-sql/pglite/contrib/pg_trgm";
import { pgcrypto } from "@electric-sql/pglite/contrib/pgcrypto";

const migrationsUrl = new URL("../../../supabase/migrations/", import.meta.url);
const migrationNames = (await readdir(fileURLToPath(migrationsUrl)))
  .filter((name) => name.endsWith(".sql"))
  .sort();
assert.ok(migrationNames.some((name) => name.endsWith("_public_debt_rgf_annex2.sql")));

const sha = (text) => createHash("sha256").update(text).digest("hex");
const database = new PGlite({ extensions: { pgcrypto, pg_trgm } });
try {
  await database.exec(`
    create role anon nologin;
    create role authenticated nologin;
    create role authenticator nologin;
    create role service_role nologin bypassrls;
    create schema auth;
    create table auth.users (id uuid primary key);
    insert into auth.users (id) values
      ('1575c740-fcff-4b1a-89a9-e8e5a314880a'),
      ('27b3add6-f788-48e5-bf6f-50dfbd8cf198'),
      ('c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a');
    create function auth.uid() returns uuid language sql stable set search_path = ''
      as $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
    create function auth.jwt() returns jsonb language sql stable set search_path = ''
      as $$ select coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb) $$;
    create schema storage;
    create table storage.buckets (
      id text primary key, name text not null, public boolean not null default false,
      file_size_limit bigint, allowed_mime_types text[]
    );
    create table storage.objects (
      id uuid primary key, bucket_id text not null references storage.buckets(id),
      name text not null, unique(bucket_id, name)
    );
    alter table storage.objects enable row level security;
    grant usage on schema storage to authenticated;
    grant select, insert, update, delete on storage.objects to authenticated;
  `);
  for (const name of migrationNames) {
    await database.exec(await readFile(fileURLToPath(new URL(name, migrationsUrl)), "utf8"));
  }

  const endpoint = (
    await database.query(`select e.id from source.source_endpoints e
      join source.data_sources d on d.id = e.data_source_id
      where d.slug = 'siconfi-barreiras' and e.slug = 'rgf-anexo-02'`)
  ).rows[0]?.id;
  assert.ok(endpoint, "endpoint rgf-anexo-02 cadastrado");
  const run = "00000000-0000-4000-a000-000000000003";
  await database.exec(`
    insert into source.collection_runs (id, source_endpoint_id, idempotency_key,
      collector_version, parser_version, status, attempt_count, started_at, completed_at)
    values ('${run}', '${endpoint}', '${"e".repeat(64)}', 'test/1', 'parser/1',
      'succeeded', 1, now(), now());
  `);

  const statements = [];
  let artifacts = 0;
  let records = 0;
  function page(retrievedAt, year, period, lines) {
    artifacts += 1;
    const id = `00000000-0000-4000-b000-${String(artifacts).padStart(12, "0")}`;
    statements.push(`insert into raw.raw_artifacts (id, collection_run_id, source_endpoint_id,
      idempotency_key, artifact_kind, source_url, retrieved_at, http_status, content_type,
      byte_size, sha256, object_key, collector_version, metadata)
      values ('${id}', '${run}', '${endpoint}', '${sha(`idem-${id}`)}', 'http_response',
      'https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rgf', '${retrievedAt}', 200,
      'application/json', 2, '${sha(`page-${id}`)}', 'siconfi/rgf/${id}.json', 'test/1',
      '{"schema_name":"siconfi-rgf-annex2-page"}');`);
    lines.forEach(([coluna, code, conta, valor], index) => {
      records += 1;
      const payload = {
        exercicio: year, periodo: period, periodicidade: "Q", co_poder: "E", esfera: "M",
        anexo: "RGF-Anexo 02", coluna, cod_conta: code, conta, valor,
      };
      statements.push(`insert into raw.raw_records (raw_artifact_id, source_record_key,
        record_type, record_index, payload, payload_sha256, parser_version, idempotency_key,
        collected_at) values ('${id}', 'k${records}', 'siconfi_rgf_annex2_line', ${index},
        '${JSON.stringify(payload).replaceAll("'", "''")}', '${sha(`p${records}`)}',
        'parser/1', '${sha(`i${records}`)}', now());`);
    });
    return id;
  }
  const q3 = "Até o 3º Quadrimestre";
  const full = (dcl) => [
    ["SALDO DO EXERCÍCIO ANTERIOR", "DividaConsolidadaLiquida", "DCL (III)", "919609678.89"],
    ["Até o 2º Quadrimestre", "DividaConsolidadaLiquida", "DCL (III)", "728506219.45"],
    [q3, "DividaConsolidada", "DÍVIDA CONSOLIDADA - DC (I)", "851127589.50"],
    [q3, "RGF2Emprestimos", "Empréstimos", "203128025.18"],
    [q3, "DeducoesDaDividaConsolidada", "DEDUÇÕES (II)", "13634624.92"],
    [q3, "DividaConsolidadaLiquida", "DCL (III)", dcl],
    [q3, "ReceitaCorrenteLiquidaAjustadaParaCalculoDosLimitesDeEndividamento", "RCL (VI)",
      "918218391.18"],
    [q3, "PercentualDaDCLSobreARCL", "% da DCL", "91.21"],
    [q3, "LimiteDefinidoPorResolucaoDoSenadoFederal", "LIMITE SENADO", "1101862069.42"],
    [q3, "LimiteDeAlerta", "LIMITE DE ALERTA", "991675862.47"],
  ];
  page("2025-02-01T00:00:00Z", 2024, 3, full("800000000.00"));
  // Retificação coletada depois: esta vale.
  const latest = page("2025-03-01T00:00:00Z", 2024, 3, full("837492964.58"));
  page("2024-10-01T00:00:00Z", 2024, 2, [
    ["Até o 2º Quadrimestre", "DividaConsolidadaLiquida", "DCL (III)", "728506219.45"],
  ]);
  await database.exec(statements.join("\n"));

  const rows = (await database.query("select * from api.get_public_debt_statements()")).rows;
  assert.deepEqual(rows.map((row) => [row.fiscal_year, row.period]), [[2024, 3], [2024, 2]]);
  const [q3row, q2row] = rows;
  assert.equal(q3row.net_consolidated_debt, "837492964.58");
  assert.equal(q3row.consolidated_debt, "851127589.50");
  assert.equal(q3row.deductions, "13634624.92");
  assert.equal(q3row.adjusted_net_current_revenue, "918218391.18");
  assert.equal(q3row.net_debt_revenue_percent, "91.21");
  assert.equal(q3row.senate_limit, "1101862069.42");
  assert.equal(q3row.alert_limit, "991675862.47");
  assert.equal(q3row.period_end.toISOString().slice(0, 10), "2024-12-31");
  assert.equal(q3row.composition.length, 8, "só a coluna do próprio quadrimestre");
  assert.deepEqual(q3row.composition[1], {
    code: "RGF2Emprestimos", account: "Empréstimos", value: "203128025.18",
  });
  assert.equal(q3row.methodology_version, "municipal-debt-rgf-annex2/1.0.0");
  assert.equal(
    q3row.artifact_sha256,
    (await database.query(`select sha256 from raw.raw_artifacts where id = '${latest}'`))
      .rows[0].sha256,
  );
  assert.equal(q2row.net_consolidated_debt, "728506219.45");
  assert.equal(q2row.consolidated_debt, null, "conta ausente fica nula, nunca zero");
  assert.equal(q2row.period_end.toISOString().slice(0, 10), "2024-08-31");

  const access = await database.query(`select
    has_function_privilege('anon', 'api.get_public_debt_statements()', 'EXECUTE') as anon,
    exists (select 1 from audit.storage_workload_identities
      where object_prefix = 'siconfi/rgf/' and status = 'active') as corridor`);
  assert.deepEqual(access.rows[0], { anon: true, corridor: true });
} finally {
  await database.close();
}

console.log("public debt migration test passed");
