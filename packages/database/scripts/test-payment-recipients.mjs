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
assert.ok(migrationNames.some((name) => name.endsWith("_payment_recipients_snapshot.sql")));

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
  function grid(month, retrievedAt) {
    artifactCount += 1;
    const id = `00000000-0000-4000-b000-${String(artifactCount).padStart(12, "0")}`;
    statements.push(`insert into raw.raw_artifacts (id, collection_run_id, source_endpoint_id,
      idempotency_key, artifact_kind, source_url, retrieved_at, http_status, content_type,
      byte_size, sha256, object_key, collector_version, metadata)
      values ('${id}', '${run}', '00000000-0000-4000-a000-000000000002',
      '${sha(`idem-${id}`)}', 'http_response', 'https://barreiras.ba.gov.br/grid',
      '${retrievedAt}', 200, 'application/json', 2, '${sha(`grid-${id}`)}',
      'grid/${id}.json', 'test/1',
      '{"schema_name":"municipal-payments-webrun-grid","cursor":{"month":"${month}"}}');`);
    return id;
  }
  let recordCount = 0;
  function payment(artifact, date, amount, creditor, nature, extra = {}) {
    recordCount += 1;
    const payload = {
      field1082587: date, field1082592: amount, field1082593: `${recordCount}`,
      field1082594: "Orçamentária", field1082596: `O-${recordCount}`,
      field1082598: "PREFEITURA MUNICIPAL DE BARREIRAS",
      field1135675: nature, field1144925: creditor, ...extra,
    };
    statements.push(`insert into raw.raw_records (raw_artifact_id, source_record_key,
      record_type, record_index, payload, payload_sha256, parser_version, idempotency_key,
      collected_at) values ('${artifact}', 'pagamento:${recordCount}', 'municipal_payment_webrun',
      ${recordCount}, '${JSON.stringify(payload).replaceAll("'", "''")}',
      '${sha(`p${recordCount}`)}', 'parser/1', '${sha(`i${recordCount}`)}', now());`);
  }
  function commitment(artifact, key, date) {
    recordCount += 1;
    statements.push(`insert into raw.raw_records (raw_artifact_id, source_record_key,
      record_type, record_index, payload, payload_sha256, parser_version, idempotency_key,
      collected_at) values ('${artifact}', 'empenho:${recordCount}', 'municipal_commitment_webrun',
      ${recordCount}, '${JSON.stringify({ field1144631: key, field1082407: date })}',
      '${sha(`p${recordCount}`)}', 'parser/1', '${sha(`i${recordCount}`)}', now());`);
  }

  const groups = (
    await database.query(`select finance.payment_recipient_group_v1(n) as g from (values
      ('3.7.6.8.0 - VENCIMENTOS E SALÁRIOS'),
      ('4.4.4.0.0 - OUTROS SERVIÇOS DE TERCEIROS - PESSOA JURÍDICA'),
      ('3.8.0.1.0 - CONTRIBUIÇÕES PREVIDENCIÁRIAS - INSS'),
      ('5.4.1.8.0 - OUTRAS AMORTIZAÇÕES DA DÍVIDA CONTRATADA'),
      ('JUROS SOBRE A DÍVIDA POR CONTRATO'),
      ('MULTAS E JUROS DE MORA'),
      ('SENTENÇAS JUDICIAIS (PESSOAL E ENCARGOS SOCIAIS)'),
      ('DESP. EXERCÍCIOS ANTERIORES (PESSOAL E ENCARGOS)'),
      ('DESPESAS DE EXERCÍCIOS ANTERIORES (OUTRAS QUE NÃO PESSOAL)'),
      ('INDENIZAÇÕES E RESTITUIÇÕES TRABALHISTAS'),
      ('OUTRAS INDENIZAÇÕES E RESTITUIÇÕES'),
      ('RESSARCIMENTO DE PASSAGENS E DESPESAS COM LOCOMOÇÃO'),
      ('RESSARCIMENTO DE DESPESAS PESSOAL REQUISITADO'),
      ('OUTOS AUXÍLIOS-TRANSPORTE'),
      ('OUTROS AUXÍLIOS FINANCEIROS A PESSOAS FÍSICAS'),
      ('AUXÍLIO FINANCEIRO A PESQUISADORES'),
      ('OUTROS RATEIOS PELA PARTICIPAÇÃO EM CONSÓRCIOS PÚBLICOS'),
      ('AUXÍLIOS'),
      ('OUTRAS CONTIBUIÇÕES'),
      ('CONTRIBUIÇÃO PARA O PIS/PASEP'),
      ('OUTROS BENEFÍCIOS PREVIDENCIÁRIOS DO SERVIDOR'),
      ('OUTRAS DESPESAS VARIÁVEIS - PESSOAL CIVIL'),
      ('APOSENTADORIAS DO RPPS'),
      ('DIÁRIAS NO PAÍS'),
      ('CESTA BÁSICA'),
      ('9.9 - NÃO USAR ESSA'),
      (''),
      (null)) as t(n)`)
  ).rows.map((row) => row.g);
  assert.deepEqual(groups, [
    "pessoal", "compras_servicos", "tributos_encargos", "divida", "divida", "compras_servicos",
    "judicial", "pessoal", "compras_servicos", "pessoal", "restituicoes", "restituicoes",
    "pessoal", "pessoal", "auxilios", "auxilios", "transferencias", "transferencias",
    "transferencias", "tributos_encargos", "pessoal", "pessoal", "pessoal", "pessoal",
    "compras_servicos", "nao_identificado", "nao_identificado", "nao_identificado",
  ]);

  const entity = (
    await database.query(`select n, finance.payment_creditor_is_entity_v1(n) as e from (values
      ('RODE BEM LOCACAO DE MAQUINAS LTDA - ME'), ('MD SAÚDE S/S'), ('B3 S.A.'),
      ('34.903.373 JACKSON DIEGO VILAS BOAS'), ('MINISTERIO DAS CIDADES'),
      ('FOPAG - FUNDO MUNICIPAL DE SAUDE'), ('MARIA DA SILVA'), ('JOSÉ CÂMARA'),
      ('EMPRESA FULANO 123.456.789-09'), ('FULANO LTDA 12345678909'), (null),
      ('THABATA BARROS DE SÁ TELES'), ('PAULO JAIME DE SÁ'), ('COSME SOUZA MEDRADO - ME')) as t(n)`)
  ).rows.map((row) => row.e);
  assert.deepEqual(entity, [
    true, true, true, true, true, true, false, false, false, false, false, false, false, true,
  ]);

  const services = "4.4.4.0.0 - OUTROS SERVIÇOS DE TERCEIROS - PESSOA JURÍDICA";
  const salary = "3.7.6.8.0 - VENCIMENTOS E SALÁRIOS";
  const restitution = "OUTRAS INDENIZAÇÕES E RESTITUIÇÕES";
  const oldJuly = grid("2025-07", "2025-08-01T00:00:00Z");
  const july = grid("2025-07", "2025-09-01T00:00:00Z");
  const august = grid("2025-08", "2025-09-01T00:00:00Z");
  const july2024 = grid("2024-07", "2024-08-01T00:00:00Z");
  payment(july, "10/07/2025", "333200", "RODE BEM LTDA", services);            // O-1
  payment(august, "05/08/2025", "1.000,50", "RODE BEM LTDA", services);        // O-2
  payment(july, "11/07/2025", "99,99", "PRESTADOR 123.456.789-09", services); // O-3
  payment(july, "11/07/2025", "200", "JOANA SOUZA", services);             // O-4
  payment(july, "12/07/2025", "5000", "MARIA SERVIDORA", salary);              // O-5
  payment(august, "12/08/2025", "7000", "PREFEITURA MUNICIPAL DE BARREIRAS", salary, {
    field1082598: "CÂMARA MUNICIPAL DE BARREIRAS",
  });                                                                          // O-6
  payment(august, "13/08/2025", "1000", "MINISTERIO DAS CIDADES", restitution); // O-7
  payment(august, "13/08/2025", "valor?", "ILEGIVEL LTDA", services);          // O-8
  payment(august, "14/08/2025", "50", "EXTRA LTDA", services, {
    field1082594: "Extra-orçamentária", field1082596: "E-9",
  });
  payment(august, "31/12/2024", "70", "OUTRA DATA LTDA", services);            // O-10
  // Recoleta antiga do mesmo mês: não conta em dobro.
  payment(oldJuly, "10/07/2025", "333200", "RODE BEM LTDA", services);
  payment(july2024, "10/07/2024", "10", "OUTRO ANO LTDA", services);
  commitment(july2024, "O-1", "02/12/2024");
  commitment(july, "O-2", "01/07/2025");
  commitment(july, "O-5", "01/07/2025");
  await database.exec(statements.join("\n"));

  assert.equal((await database.query(
    "select count(*)::integer as n from api.get_public_payment_recipients(2025)")).rows[0].n, 0,
    "sem atualização, nada é publicado");
  const refreshed = (await database.query(
    "select finance.refresh_payment_recipients() as n")).rows[0].n;
  assert.equal(refreshed, 6, "2025 (5 linhas) e 2024 (1 linha)");
  const audit = (await database.query(`select after_state from audit.audit_events
    where action = 'source_snapshot.refreshed'
      and target_type = 'finance.payment_recipient_snapshots'
    order by occurred_at, id`)).rows;
  const latest = audit.at(-1).after_state;
  assert.ok(audit.length >= 2, "as migrations e esta atualização ficam auditadas");
  assert.equal(latest.row_count, 6);
  assert.match(latest.content_sha256, /^[0-9a-f]{64}$/);
  assert.equal((await database.query(
    "select finance.refresh_payment_recipients() as n")).rows[0].n, 6, "atualizar de novo não duplica");

  const rows = (await database.query(
    "select * from api.get_public_payment_recipients(2025)")).rows;
  assert.ok(rows.every((row) => row.refreshed_at instanceof Date));
  assert.deepEqual(
    rows.map((row) => [
      row.payment_group, row.creditor_name, row.creditors, row.payments, row.paid_amount,
    ]),
    [
      ["compras_servicos", "RODE BEM LTDA", 1, 2, "334200.50"],
      ["compras_servicos", null, 2, 2, "299.99"],
      ["pessoal", "PREFEITURA MUNICIPAL DE BARREIRAS", 1, 1, "7000.00"],
      ["pessoal", null, 1, 1, "5000.00"],
      ["restituicoes", "MINISTERIO DAS CIDADES", 1, 1, "1000.00"],
    ],
  );
  assert.ok(rows.every((row) => !/123\.456|JOANA|MARIA/.test(row.creditor_name ?? "")),
    "pessoa física e CPF nunca saem pelo nome");
  const [first] = rows;
  assert.equal(first.main_nature, "OUTROS SERVIÇOS DE TERCEIROS - PESSOA JURÍDICA");
  assert.equal(first.first_payment_date.toISOString().slice(0, 10), "2025-07-10");
  assert.equal(first.last_payment_date.toISOString().slice(0, 10), "2025-08-05");
  assert.match(first.grid_artifact_sha256, /^[0-9a-f]{64}$/);
  assert.deepEqual(
    [first.group_payments, first.group_creditors, first.group_paid_amount],
    [4, 3, "334500.49"],
  );
  assert.deepEqual(
    [first.year_payments, first.year_paid_amount, first.year_grid_months,
      first.year_unreadable_rows, first.year_excluded_rows],
    [7, "347500.49", 2, 1, 2],
  );
  const groupSum = [...new Map(rows.map((row) => [row.payment_group, row.group_paid_amount]))
    .values()].reduce((sum, value) => sum + Math.round(Number(value) * 100), 0);
  assert.equal(groupSum, 34750049, "grupos somam o total do ano");
  assert.equal(first.year_prior_commitment_amount, "333200.00", "restos a pagar de 2024");
  assert.equal(first.year_uncollected_commitment_amount, "8299.99");
  assert.deepEqual(first.year_bodies, [
    { public_body: "PREFEITURA MUNICIPAL DE BARREIRAS", payments: 6, paid_amount: "340500.49" },
    { public_body: "CÂMARA MUNICIPAL DE BARREIRAS", payments: 1, paid_amount: "7000.00" },
  ]);
  assert.equal(first.methodology_version, "municipal-payment-recipients/1.0.0");

  await assert.rejects(
    database.query("select * from api.get_public_payment_recipients(2023)"),
    /ano deve estar entre 2024 e 2100/,
  );
  const access = await database.query(`select
    has_function_privilege('anon', 'api.get_public_payment_recipients(integer)', 'EXECUTE') as anon,
    has_function_privilege('anon', 'finance.compute_payment_recipients(integer)', 'EXECUTE')
      as anon_compute,
    has_function_privilege('anon', 'finance.refresh_payment_recipients()', 'EXECUTE') as anon_refresh,
    has_function_privilege('collector_worker', 'finance.refresh_payment_recipients()', 'EXECUTE')
      as worker_refresh,
    has_table_privilege('anon', 'finance.payment_recipient_snapshots', 'SELECT') as anon_table`);
  assert.deepEqual(access.rows[0], {
    anon: true, anon_compute: false, anon_refresh: false, worker_refresh: true, anon_table: false,
  });
} finally {
  await database.close();
}

console.log("payment recipients migration test passed");
