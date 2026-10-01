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
assert.ok(migrationNames.some((name) => name.endsWith("_public_dca_expense_groups.sql")));

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
      where d.slug = 'siconfi-barreiras' and e.slug = 'dca'`)
  ).rows[0]?.id;
  assert.ok(endpoint, "endpoint dca cadastrado");
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
  function page(retrievedAt, year, lines) {
    artifacts += 1;
    const id = `00000000-0000-4000-b000-${String(artifacts).padStart(12, "0")}`;
    statements.push(`insert into raw.raw_artifacts (id, collection_run_id, source_endpoint_id,
      idempotency_key, artifact_kind, source_url, retrieved_at, http_status, content_type,
      byte_size, sha256, object_key, collector_version, metadata)
      values ('${id}', '${run}', '${endpoint}', '${sha(`idem-${id}`)}', 'http_response',
      'https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca', '${retrievedAt}', 200,
      'application/json', 2, '${sha(`page-${id}`)}', 'siconfi/dca/${id}.json', 'test/1',
      '{"schema_name":"siconfi-dca-page"}');`);
    lines.forEach(([anexo, coluna, code, conta, valor], index) => {
      records += 1;
      const payload = { exercicio: year, anexo, coluna, cod_conta: code, conta, valor };
      statements.push(`insert into raw.raw_records (raw_artifact_id, source_record_key,
        record_type, record_index, payload, payload_sha256, parser_version, idempotency_key,
        collected_at) values ('${id}', 'k${records}', 'siconfi_dca_line', ${index},
        '${JSON.stringify(payload).replaceAll("'", "''")}', '${sha(`p${records}`)}',
        'parser/1', '${sha(`i${records}`)}', now());`);
    });
    return id;
  }
  const id = "DCA-Anexo I-D";
  page("2026-08-01T00:00:00Z", 2025, [
    [id, "Despesas Pagas", "DO3.1.00.00.00.00", "3.1.00.00.00 - Pessoal e Encargos Sociais", "1.00"],
  ]);
  const latest = page("2026-08-24T00:00:00Z", 2025, [
    [id, "Despesas Pagas", "TotalDespesas", "Total Geral da Despesa", "950096510.57"],
    [id, "Despesas Liquidadas", "TotalDespesas", "Total Geral da Despesa", "990006209.71"],
    [id, "Despesas Pagas", "DO3.1.00.00.00.00", "3.1.00.00.00 - Pessoal e Encargos Sociais", "499801753.51"],
    [id, "Despesas Pagas", "DO4.6.00.00.00.00", "4.6.00.00.00 - Amortização da Dívida", "99006091.3"],
    [id, "Despesas Pagas", "DO3.1.90.11.00.00", "3.1.90.11.00 - Vencimentos", "328961134.90"],
    [id, "Despesas Empenhadas", "DO3.3.00.00.00.00", "3.3.00.00.00 - Outras Despesas Correntes", "1"],
    ["DCA-Anexo I-C", "Receitas Brutas Realizadas", "TotalReceitas", "Total", "1"],
  ]);
  page("2026-08-24T00:00:00Z", 2024, [
    [id, "Despesas Pagas", "TotalDespesas", "Total Geral da Despesa", "908142035.95"],
  ]);
  await database.exec(statements.join("\n"));

  const rows = (await database.query(
    "select * from api.get_public_dca_expense_groups(2025)")).rows;
  assert.deepEqual(
    rows.map((row) => [row.account_code, row.paid_amount, row.liquidated_amount]),
    [
      ["DO3.1.00.00.00.00", "499801753.51", null],
      ["DO4.6.00.00.00.00", "99006091.30", null],
      ["TotalDespesas", "950096510.57", "990006209.71"],
    ],
    "só grupos e total, coluna empenhada fora, retificação mais recente vale",
  );
  assert.equal(rows[0].artifact_sha256, sha(`page-${latest}`));
  assert.equal(rows[0].methodology_version, "siconfi-dca-expense-groups/1.0.0");
  assert.equal(
    (await database.query("select count(*)::integer as n from api.get_public_dca_expense_groups(2023)"))
      .rows[0].n,
    0,
    "ano sem DCA: nenhuma linha",
  );
  await assert.rejects(
    database.query("select * from api.get_public_dca_expense_groups(1999)"),
    /ano deve estar entre 2015 e 2100/,
  );
  const access = await database.query(`select
    has_function_privilege('anon', 'api.get_public_dca_expense_groups(integer)', 'EXECUTE') as anon`);
  assert.equal(access.rows[0].anon, true);
} finally {
  await database.close();
}

console.log("dca expense groups migration test passed");
