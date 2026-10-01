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
assert.ok(migrationNames.some((name) => name.endsWith("_payment_recipients_liquidated.sql")));

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
  function grid(month, retrievedAt, schema = "municipal-payments-webrun-grid") {
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
  function liquidation(artifact, date, amount, creditor, nature, key = "O-500") {
    recordCount += 1;
    const payload = {
      field1089483: date, field1089487: key, field1089488: amount,
      field1135672: nature, field1144939: creditor,
    };
    statements.push(`insert into raw.raw_records (raw_artifact_id, source_record_key,
      record_type, record_index, payload, payload_sha256, parser_version, idempotency_key,
      collected_at) values ('${artifact}', 'liquidacao:${recordCount}',
      'municipal_liquidation_webrun', ${recordCount}, '${JSON.stringify(payload).replaceAll("'", "''")}',
      '${sha(`p${recordCount}`)}', 'parser/1', '${sha(`i${recordCount}`)}', now());`);
  }
  function commitmentSql(key, date, code) {
    recordCount += 1;
    const payload = { field1144631: key, field1082407: date };
    if (code) payload.field1144633 = code;
    return `insert into raw.raw_records (raw_artifact_id, source_record_key,
      record_type, record_index, payload, payload_sha256, parser_version, idempotency_key,
      collected_at) values ('${july2024Grid}', 'empenho:${recordCount}', 'municipal_commitment_webrun',
      ${recordCount}, '${JSON.stringify(payload)}',
      '${sha(`p${recordCount}`)}', 'parser/1', '${sha(`i${recordCount}`)}', now());`;
  }
  let july2024Grid = null;
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
  july2024Grid = july2024;
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
  const liquidationJuly = grid("2025-07", "2025-09-01T00:00:00Z",
    "municipal-liquidations-webrun-grid");
  liquidation(liquidationJuly, "09/07/2025", "400000", "RODE BEM LTDA", services);
  liquidation(liquidationJuly, "10/07/2025", "50", "NOVA EMPRESA LTDA", services);
  liquidation(liquidationJuly, "11/07/2025", "10", "CARLA SERVIDORA", salary);
  liquidation(liquidationJuly, "31/12/2024", "999", "OUTRO ANO LTDA", services);
  liquidation(liquidationJuly, "12/07/2025", "7", "EXTRA LTDA", services, "E-1");
  // Recoleta antiga do mesmo mês: não conta em dobro.
  payment(oldJuly, "10/07/2025", "333200", "RODE BEM LTDA", services);
  payment(july2024, "10/07/2024", "10", "OUTRO ANO LTDA", services);          // O-12
  payment(july2024, "11/07/2024", "5", "OUTRO ANO LTDA", services);           // O-13
  payment(july2024, "12/07/2024", "3", "JOSE PEREIRA", salary);
  payment(july2024, "15/07/2024", "4", "ANA LIMA", "OUTROS SERVIÇOS DE TERCEIROS - PESSOA FÍSICA");
  payment(july2024, "16/07/2024", "6", "BRUNO COSTA", "OUTROS SERVIÇOS DE TERCEIROS - PESSOA FÍSICA");
  commitment(july2024, "O-1", "02/12/2024");
  commitment(july, "O-2", "01/07/2025");
  commitment(july, "O-5", "01/07/2025");
  await database.exec(statements.join("\n"));

  // Contratos, cadastro da Receita e ligações confirmadas (ADR 0086/0093/0094).
  const recordId = (type, field, value) => `(select id from raw.raw_records
    where record_type = '${type}' and payload ->> '${field}' = '${value}' limit 1)`;
  const insertRecord = (type, key, payload) => `insert into raw.raw_records (raw_artifact_id,
    source_record_key, record_type, record_index, payload, payload_sha256, parser_version,
    idempotency_key, collected_at) values ('${july}', '${key}', '${type}', ${(recordCount += 1)},
    '${JSON.stringify(payload)}', '${sha(key)}', 'parser/1', '${sha(`i-${key}`)}', now());`;
  const link = (commitmentKey, state, reason, contractPortal) => `insert into
    finance.commitment_contract_links (commitment_raw_record_id, commitment_key, state, reason,
      contract_raw_record_id, contract_portal_id, rule_version)
    values (${recordId("municipal_commitment_webrun", "field1144631", commitmentKey)},
      '${commitmentKey}', '${state}', '${reason}',
      ${contractPortal ? recordId("municipal_transparency_contratos", "id", contractPortal) : "null"},
      ${contractPortal ? `'${contractPortal}'` : "null"}, 'commitment-contract-link/1.0.0');`;
  await database.exec([
    insertRecord("municipal_transparency_contratos", "contrato:C1",
      { id: "C1", documento: "11.222.333/0001-81" }),
    insertRecord("municipal_transparency_contratos", "contrato:C2",
      { id: "C2", documento: "44.555.666/0001-99" }),
    insertRecord("receita_cnpj_registry", "receita:1", {
      cnpj: "11222333000181", razao_social: "RODE BEM LOCACAO DE MAQUINAS LTDA",
      natureza_juridica: "2062", natureza_juridica_descricao: "Sociedade Empresária Limitada",
      registry_month: "2026-09",
    }),
    insertRecord("municipal_transparency_contratos", "contrato:C3",
      { id: "C3", documento: "77.888.999/0001-00" }),
    insertRecord("receita_cnpj_registry", "receita:3", {
      cnpj: "77888999000100", razao_social: "UNIAO - MINISTERIO DAS CIDADES",
      natureza_juridica: "1015", natureza_juridica_descricao: "Órgão Público do Poder Executivo Federal",
      registry_month: "2026-09",
    }),
    commitmentSql("O-7", "01/08/2025", "777"),
    commitmentSql("O-99", "01/03/2025", "777"),
    insertRecord("receita_cnpj_registry", "receita:2", {
      cnpj: "44555666000199", razao_social: "OUTRA EMPRESA LTDA",
      natureza_juridica: "2062", natureza_juridica_descricao: "Sociedade Empresária Limitada",
      registry_month: "2026-09",
    }),
    commitmentSql("O-12", "01/07/2024"),
    commitmentSql("O-13", "01/07/2024"),
    link("O-1", "ligado", "", "C1"),
    link("O-2", "citacao_sem_confirmacao", "favorecido_divergente", null),
    `insert into editorial.editorial_reviews (target_type, target_id, reviewer_subject,
      review_type, decision, rationale, checklist)
      select 'finance.commitment_contract_links', id, 'automated:commitment-registry-name',
        'data_quality', 'approved', 'teste',
        jsonb_build_object('contract_raw_record_id',
          ${recordId("municipal_transparency_contratos", "id", "C1")}::text)
      from finance.commitment_contract_links where commitment_key = 'O-2';`,
    link("O-12", "ligado", "", "C1"),
    link("O-13", "ligado", "", "C2"),
    link("O-99", "ligado", "", "C3"),
  ].join("\n"));

  assert.equal((await database.query(
    "select count(*)::integer as n from api.get_public_payment_recipients(2025)")).rows[0].n, 0,
    "sem atualização, nada é publicado");
  const refreshed = (await database.query(
    "select finance.refresh_payment_recipients() as n")).rows[0].n;
  assert.equal(refreshed, 9, "2025 (6 linhas) e 2024 (3 linhas)");
  const people2024 = (await database.query(`select payment_group, main_nature, creditors,
      paid_amount from finance.payment_recipient_snapshots
    where fiscal_year = 2024 and creditor_name is null order by row_order`)).rows;
  assert.deepEqual(people2024, [
    { payment_group: "compras_servicos", main_nature: "OUTROS SERVIÇOS DE TERCEIROS - PESSOA FÍSICA",
      creditors: 2, paid_amount: "10.00" },
    { payment_group: "pessoal", main_nature: "VENCIMENTOS E SALÁRIOS", creditors: 1,
      paid_amount: "3.00" },
  ], "pessoas físicas agregadas por natureza, sem nome");
  const registry = (await database.query(`select fiscal_year, creditor_name, registry_cnpj,
      registry_legal_name, registry_legal_nature, registry_month
    from finance.payment_recipient_snapshots where registry_cnpj is not null`)).rows;
  assert.deepEqual(registry, [{
    fiscal_year: 2025, creditor_name: "RODE BEM LTDA", registry_cnpj: "11222333000181",
    registry_legal_name: "RODE BEM LOCACAO DE MAQUINAS LTDA",
    registry_legal_nature: "Sociedade Empresária Limitada", registry_month: "2026-09",
  }, {
    fiscal_year: 2025, creditor_name: "MINISTERIO DAS CIDADES", registry_cnpj: "77888999000100",
    registry_legal_name: "UNIAO - MINISTERIO DAS CIDADES",
    registry_legal_nature: "Órgão Público do Poder Executivo Federal", registry_month: "2026-09",
  }], "pelo código do credor; 2024: duas ligações com CNPJs diferentes não dão CNPJ");
  const audit = (await database.query(`select after_state from audit.audit_events
    where action = 'source_snapshot.refreshed'
      and target_type = 'finance.payment_recipient_snapshots'
    order by occurred_at, id`)).rows;
  const latest = audit.at(-1).after_state;
  assert.ok(audit.length >= 2, "as migrations e esta atualização ficam auditadas");
  assert.equal(latest.row_count, 9);
  assert.match(latest.content_sha256, /^[0-9a-f]{64}$/);
  assert.equal((await database.query(
    "select finance.refresh_payment_recipients() as n")).rows[0].n, 9, "atualizar de novo não duplica");

  const rows = (await database.query(
    "select * from api.get_public_payment_recipients(2025)")).rows;
  assert.ok(rows.every((row) => row.refreshed_at instanceof Date));
  assert.deepEqual(
    rows.map((row) => [
      row.payment_group, row.creditor_name, row.creditors, row.payments, row.paid_amount,
      row.liquidations, row.liquidated_amount,
    ]),
    [
      ["compras_servicos", "RODE BEM LTDA", 1, 2, "334200.50", 1, "400000.00"],
      ["compras_servicos", "NOVA EMPRESA LTDA", 1, 0, "0.00", 1, "50.00"],
      ["compras_servicos", null, 2, 2, "299.99", 0, "0.00"],
      ["pessoal", "PREFEITURA MUNICIPAL DE BARREIRAS", 1, 1, "7000.00", 0, "0.00"],
      ["pessoal", null, 2, 1, "5000.00", 1, "10.00"],
      ["restituicoes", "MINISTERIO DAS CIDADES", 1, 1, "1000.00", 0, "0.00"],
    ],
  );
  assert.ok(rows.every((row) => !/123\.456|JOANA|MARIA/.test(row.creditor_name ?? "")),
    "pessoa física e CPF nunca saem pelo nome");
  const [first] = rows;
  assert.equal(rows[1].first_payment_date, null, "só liquidação: sem data de pagamento");
  assert.deepEqual(
    [first.year_liquidations, first.year_liquidated_amount, first.year_liquidation_grid_months,
      first.group_liquidated_amount],
    [3, "400060.00", 1, "400050.00"],
    "liquidação de outro ano e extraorçamentária ficam fora",
  );
  assert.equal(first.main_nature, "OUTROS SERVIÇOS DE TERCEIROS - PESSOA JURÍDICA");
  assert.equal(first.first_payment_date.toISOString().slice(0, 10), "2025-07-10");
  assert.equal(first.last_payment_date.toISOString().slice(0, 10), "2025-08-05");
  assert.match(first.grid_artifact_sha256, /^[0-9a-f]{64}$/);
  assert.deepEqual(
    [first.group_payments, first.group_creditors, first.group_paid_amount],
    [4, 4, "334500.49"],
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
  assert.equal(first.year_uncollected_commitment_amount, "7299.99");
  assert.deepEqual(first.year_bodies, [
    { public_body: "PREFEITURA MUNICIPAL DE BARREIRAS", payments: 6, paid_amount: "340500.49" },
    { public_body: "CÂMARA MUNICIPAL DE BARREIRAS", payments: 1, paid_amount: "7000.00" },
  ]);
  assert.equal(first.methodology_version, "municipal-payment-recipients/1.3.0");

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
