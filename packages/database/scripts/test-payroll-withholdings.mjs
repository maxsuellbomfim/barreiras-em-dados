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
assert.ok(migrationNames.some((name) => name.endsWith("_public_payroll_withholdings.sql")));

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

  const run = "00000000-0000-4000-a000-000000000003";
  await database.exec(`
    insert into source.data_sources (id, slug, name, authority_level, homepage_url)
    values ('00000000-0000-4000-a000-000000000001', 'teste-webrun', 'WebRun de teste',
            'official', 'https://barreiras.ba.gov.br');
    insert into source.source_endpoints (id, data_source_id, slug, endpoint_kind, base_url)
    values ('00000000-0000-4000-a000-000000000002', '00000000-0000-4000-a000-000000000001',
            'grid-teste', 'api', 'https://barreiras.ba.gov.br');
    insert into source.collection_runs (id, source_endpoint_id, idempotency_key,
      collector_version, parser_version, status, attempt_count, started_at, completed_at)
    values ('${run}', '00000000-0000-4000-a000-000000000002', '${"e".repeat(64)}',
            'test/1', 'parser/1', 'succeeded', 1, now(), now());
  `);

  const statements = [];
  let artifactCount = 0;
  function grid(schema, month, retrievedAt) {
    artifactCount += 1;
    const id = `00000000-0000-4000-b000-${String(artifactCount).padStart(12, "0")}`;
    statements.push(`insert into raw.raw_artifacts (id, collection_run_id, source_endpoint_id,
      idempotency_key, artifact_kind, source_url, retrieved_at, http_status, content_type,
      byte_size, sha256, object_key, collector_version, metadata)
      values ('${id}', '${run}', '00000000-0000-4000-a000-000000000002',
      '${sha(`idem-${id}`)}', 'http_response', 'https://barreiras.ba.gov.br/grid',
      '${retrievedAt}', 200, 'application/json', 2, '${sha(`grid-${id}`)}',
      'grid/${id}.json', 'test/1',
      '{"schema_name":"${schema}","cursor":{"month":"${month}"}}');`);
    return id;
  }
  let recordCount = 0;
  function record(artifact, type, key, payload) {
    recordCount += 1;
    statements.push(`insert into raw.raw_records (raw_artifact_id, source_record_key,
      record_type, record_index, payload, payload_sha256, parser_version, idempotency_key,
      collected_at) values ('${artifact}', '${key}', '${type}', ${recordCount},
      '${JSON.stringify(payload).replaceAll("'", "''")}', '${sha(`p${recordCount}`)}',
      'parser/1', '${sha(`i${recordCount}`)}', now());`);
  }
  const commitment = (artifact, key, date, amount, creditor, history, type = "Extra-Orçamentária") =>
    record(artifact, "municipal_commitment_webrun", `empenho:${key}:${artifact}`, {
      field1082407: date, field1082409: type, field1082412: amount,
      field1082413: "PREFEITURA MUNICIPAL DE BARREIRAS", field1135665: "",
      field1144629: creditor, field1144631: key, field1144634: history,
    });

  const oldJuly = grid("municipal-commitments-webrun-grid", "2025-07", "2025-08-01T00:00:00Z");
  const july = grid("municipal-commitments-webrun-grid", "2025-07", "2025-09-01T00:00:00Z");
  const august = grid("municipal-commitments-webrun-grid", "2025-08", "2025-09-01T00:00:00Z");
  const payJuly = grid("municipal-payments-webrun-grid", "2025-07", "2025-09-01T00:00:00Z");

  const bank = "PAGAMENTO DE RETENÇÃO (BANCO SANTANDER) DA FOLHA DE PAGAMENTO - MÊS: JULHO/2025.";
  commitment(july, "E-1", "10/07/2025", "1.000,00", "BANCO SANTANDER", bank);
  commitment(july, "E-2", "11/07/2025", "-200", "BANCO SANTANDER", `Estorno - ${bank}`);
  commitment(july, "E-3", "12/07/2025", "500", "INSS - INSTITUTO NACIONAL DO SEGURO SOCIAL",
    "Valor referente ao INSS Segurado da Folha de Pagamento dos servidores.");
  commitment(july, "E-4", "13/07/2025", "300", "MARIA BENEFICIARIA",
    "Despesa destinada a Pensão alimentícia descontada em folha do servidor: FULANO DE TAL");
  commitment(july, "E-5", "14/07/2025", "50", "JOAO SILVA",
    "Contribuição sindical retida em folha de pagamento.");
  // Retenção de fornecedor e empenho orçamentário ficam de fora.
  commitment(july, "E-6", "15/07/2025", "999", "INSS - INSTITUTO NACIONAL DO SEGURO SOCIAL",
    "DARF referente ao INSS da empresa X LTDA, Nota Fiscal nº 10.");
  commitment(july, "E-7", "16/07/2025", "777", "BANCO SANTANDER", bank, "Global");
  // Recoleta antiga do mesmo mês: não pode contar em dobro.
  commitment(oldJuly, "E-1", "10/07/2025", "9999", "BANCO SANTANDER", bank);
  commitment(august, "E-9", "05/08/2025", "100", "CAIXA ECONOMICA FEDERAL",
    "Consignado retido em folha - agosto/2025.");
  record(payJuly, "municipal_payment_webrun", "pagamento:E-1", {
    field1082587: "20/07/2025", field1082592: "1000", field1082596: "E-1",
  });
  await database.exec(statements.join("\n"));

  const rows = (await database.query(
    "select * from api.get_public_payroll_withholdings(2025)")).rows;
  assert.deepEqual(
    rows.map((row) => [row.creditor_name, row.commitments, row.amount, row.reversal_amount]),
    [
      ["BANCO SANTANDER", 2, "800.00", "-200.00"],
      ["INSS - INSTITUTO NACIONAL DO SEGURO SOCIAL", 1, "500.00", "0.00"],
      [null, 2, "350.00", "0.00"],
      ["CAIXA ECONOMICA FEDERAL", 1, "100.00", "0.00"],
    ],
    "pensão e pessoa física somadas sem nome; fornecedor e orçamentário fora",
  );
  const [first] = rows;
  assert.equal(first.latest_commitment_key, "E-2");
  assert.equal(first.first_commitment_date.toISOString().slice(0, 10), "2025-07-10");
  assert.match(first.grid_artifact_sha256, /^[0-9a-f]{64}$/);
  assert.deepEqual(
    [first.year_commitments, first.year_amount, first.year_reversal_amount,
      first.year_grid_months, first.year_linked_payments],
    [6, "1750.00", "-200.00", 2, 1],
  );
  assert.deepEqual(first.year_months, [
    { month: "2025-07", commitments: 5, amount: "1650.00" },
    { month: "2025-08", commitments: 1, amount: "100.00" },
  ]);
  assert.equal(first.methodology_version, "municipal-payroll-withholdings/1.0.0");
  assert.doesNotMatch(JSON.stringify(rows), /MARIA BENEFICIARIA|JOAO SILVA|FULANO/);

  assert.equal(
    (await database.query("select count(*)::integer as n from api.get_public_payroll_withholdings(2024)"))
      .rows[0].n,
    0,
  );
  await assert.rejects(
    database.query("select * from api.get_public_payroll_withholdings(2023)"),
    /ano deve estar entre 2024 e 2100/,
  );
  const access = await database.query(`select
    has_function_privilege('anon', 'api.get_public_payroll_withholdings(integer)', 'EXECUTE') as anon`);
  assert.equal(access.rows[0].anon, true);
} finally {
  await database.close();
}

console.log("payroll withholdings migration test passed");
