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
assert.ok(migrationNames.some((name) => name.endsWith("_property_rentals_location.sql")));

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
  const rent = "LOCAÇÃO DE IMÓVEIS";
  const commitment = (artifact, key, date, amount, landlord, subelement, history) =>
    record(artifact, "municipal_commitment_webrun", `empenho:${key}:${artifact}`, {
      field1082407: date, field1082409: "Global", field1082410: "1",
      field1082412: amount, field1082413: "FUNDO MUNICIPAL DE SAÚDE",
      field1135665: subelement, field1144629: landlord, field1144631: key,
      field1144633: "10", field1144634: history,
    });
  const payment = (artifact, key, amount) =>
    record(artifact, "municipal_payment_webrun", `pagamento:${key}:${artifact}`, {
      field1082587: "10/07/2025", field1082592: amount, field1082596: key,
      field1082593: `${recordCount}`,
    });

  const oldJuly = grid("municipal-commitments-webrun-grid", "2025-07", "2025-08-01T00:00:00Z");
  const july = grid("municipal-commitments-webrun-grid", "2025-07", "2025-09-01T00:00:00Z");
  const july2024 = grid("municipal-commitments-webrun-grid", "2024-07", "2024-08-01T00:00:00Z");
  const payJuly = grid("municipal-payments-webrun-grid", "2025-07", "2025-09-01T00:00:00Z");
  const oldPayJuly = grid("municipal-payments-webrun-grid", "2025-07", "2025-08-01T00:00:00Z");

  const ubs = "Locação de imóvel situado à Rua A, 93, para funcionamento de UBS. "
    + "Contrato nº 0242/2020. Locador CPF 123.456.789-09.";
  commitment(july, "O-1", "03/07/2025", "4.898,92", "MARIA LOCADORA", rent, ubs);
  commitment(july, "O-2", "20/07/2025", "1000", "MARIA LOCADORA", "LOCAÇAO DE IMÓVEL", ubs);
  commitment(july, "O-3", "05/07/2025", "2500", "JOSE LOCADOR", rent,
    "Locação de um imóvel na Rua Ceará, 281, para a Casa de Passagem. Contrato nº 002-FMS/2023.");
  commitment(july, "O-5", "06/07/2025", "300", "ANA LOCADORA", rent,
    "Locação de um imóvel na Rua B, 10, para depósito.");
  commitment(july, "O-6", "07/07/2025", "200", "AVELUZ", rent,
    "Locação de um imóvel na Av. C, conforme contrato 181/2022 com vigência até 2025.");
  commitment(july, "O-4", "05/07/2025", "9000", "EMPRESA X", "SALÁRIO", "Folha");
  // Recoleta antiga do mesmo mês: não pode contar em dobro.
  commitment(oldJuly, "O-1", "03/07/2025", "9999,99", "MARIA LOCADORA", rent, ubs);
  commitment(july2024, "O-9", "03/07/2024", "700", "OUTRO ANO", rent, "2024");
  payment(payJuly, "O-1", "4460,45");
  payment(payJuly, "O-2", "1000");
  payment(oldPayJuly, "O-1", "4460,45");
  await database.exec(statements.join("\n"));

  const rows = (await database.query(
    "select * from api.get_public_property_rentals(2025)")).rows;
  assert.deepEqual(
    rows.map((row) => [
      row.landlord_name, row.contract_text, row.commitments,
      row.committed_amount, row.paid_amount,
    ]),
    [
      ["MARIA LOCADORA", "0242/2020", 2, "5898.92", "5460.45"],
      ["JOSE LOCADOR", "002-FMS/2023", 1, "2500.00", "0.00"],
      ["ANA LOCADORA", null, 1, "300.00", "0.00"],
      ["AVELUZ", "181/2022", 1, "200.00", "0.00"],
    ],
  );
  const [first] = rows;
  assert.doesNotMatch(first.description, /123\.456\.789-09/, "CPF mascarado");
  assert.match(first.description, /funcionamento de UBS/);
  assert.equal(first.latest_commitment_key, "O-2");
  assert.equal(first.first_commitment_date.toISOString().slice(0, 10), "2025-07-03");
  assert.deepEqual(
    [first.year_landlords, first.year_commitments, first.year_committed_amount,
      first.year_paid_amount, first.year_grid_months],
    [4, 5, "8898.92", "5460.45", 1],
  );
  assert.equal(first.methodology_version, "municipal-property-rentals/1.3.0");
  assert.equal(first.address_text, "Rua A, 93");
  assert.equal(first.use_text, "UBS");
  assert.equal(first.year_addresses, 1, "só o histórico da UBS cita endereço");
  assert.equal(rows[1].address_text, null, "sem 'situado' não há endereço inventado");

  const located = (await database.query(`select
      finance.rental_address_v1(h) as address, finance.rental_use_v1(h) as use
    from (values
      ('Locação de um imóvel, situado a av. Barão do Rio Branco, 149 vila rica Barreiras/ba com adequação necessária para o funcionamento da sala do empreendedor, Secretaria'),
      ('Locação de imóvel situado à Pça. Landulfo Alves, 99 - Centro Histórico - Barreiras-BA, CEP 47.800-140, com adequação necessária para funcionamento da Secretaria de Esporte, Juventude'),
      ('Referente a Locação de um imóvel, situado Rua do Funrural, 104 Morada Nobre Barreiras/Ba, com adequação necessária para funcionamento da GESTÃO E DEPÓSITO DA MERENDA ESCOLAR, na sede'),
      ('Locação de Imóvel para sediar as instalações da UBS Adolfina Araújo Vieira, situado na Avenida Principal, N° 367, Mocambo de Cima, CEP: 47.800-000, Zona Rural'),
      ('O contrato tem por objeto a locação de um imóvel para funcionamento da Secretaria Municipal de Saúde, na sede deste município.')
    ) as t(h)`)).rows;
  assert.deepEqual(located, [
    { address: "av. Barão do Rio Branco, 149 vila rica Barreiras/ba", use: "sala do empreendedor" },
    { address: "Pça. Landulfo Alves, 99 - Centro Histórico - Barreiras-BA", use: "Secretaria de Esporte" },
    { address: "Rua do Funrural, 104 Morada Nobre Barreiras/Ba", use: "GESTÃO E DEPÓSITO DA MERENDA ESCOLAR" },
    { address: "Avenida Principal, N° 367, Mocambo de Cima", use: "UBS Adolfina Araújo Vieira" },
    { address: null, use: "Secretaria Municipal de Saúde" },
  ]);
  assert.match(first.grid_artifact_sha256, /^[0-9a-f]{64}$/);

  assert.equal(
    (await database.query("select count(*)::integer as n from api.get_public_property_rentals(2024)"))
      .rows[0].n,
    1,
  );
  await assert.rejects(
    database.query("select * from api.get_public_property_rentals(2023)"),
    /ano deve estar entre 2024 e 2100/,
  );
  const access = await database.query(`select
    has_function_privilege('anon', 'api.get_public_property_rentals(integer)', 'EXECUTE') as anon`);
  assert.equal(access.rows[0].anon, true);
} finally {
  await database.close();
}

console.log("property rentals migration test passed");
