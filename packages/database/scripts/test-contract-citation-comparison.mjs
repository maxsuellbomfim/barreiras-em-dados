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
assert.ok(migrationNames.some((name) => name.endsWith("_contract_citation_comparison.sql")));

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
    const id = `00000000-0000-4000-c000-${String(recordCount).padStart(12, "0")}`;
    statements.push(`insert into raw.raw_records (id, raw_artifact_id, source_record_key,
      record_type, record_index, payload, payload_sha256, parser_version, idempotency_key,
      collected_at) values ('${id}', '${artifact}', '${key}', '${type}', ${recordCount},
      '${JSON.stringify(payload).replaceAll("'", "''")}', '${sha(`p${recordCount}`)}',
      'parser/1', '${sha(`i${recordCount}`)}', now());`);
    return id;
  }
  function link(recordId, key, state, reason, excerpt, decidedAt = "2026-09-24T12:00:00Z") {
    statements.push(`insert into finance.commitment_contract_links (commitment_raw_record_id,
      commitment_key, state, reason, cited_excerpt, rule_version, decided_at)
      values ('${recordId}', '${key}', '${state}', '${reason}', '${excerpt}',
      'commitment-contract-link/1.0.0', '${decidedAt}');`);
  }
  const commitments = grid("municipal-commitments-webrun-grid", "2025-07", "2025-09-01T00:00:00Z");
  const oldCommitments = grid("municipal-commitments-webrun-grid", "2025-07", "2025-08-01T00:00:00Z");
  const payments = grid("municipal-payments-webrun-grid", "2025-07", "2025-09-01T00:00:00Z");
  const oldPayments = grid("municipal-payments-webrun-grid", "2025-07", "2025-08-01T00:00:00Z");
  const pncpArtifact = grid("pncp-contratos", "2025-07", "2025-09-01T00:00:00Z");
  const cited = (key, date, body, creditor, excerpt, artifact = commitments) => {
    const id = record(artifact, "municipal_commitment_webrun", `empenho:${key}:${artifact}`, {
      field1082407: date, field1082409: "Global", field1082412: "9.999,00",
      field1082413: body, field1144629: creditor, field1144631: key,
      field1144634: `Pagamento referente ao ${excerpt}.`,
    });
    return id;
  };
  const FMS = "FUNDO MUNICIPAL DE SAÚDE DE BARREIRAS";
  const pay = (artifact, key, amount) => record(artifact, "municipal_payment_webrun",
    `pagamento:${key}:${amount}:${artifact}`,
    { field1082587: "20/07/2025", field1082592: amount, field1082596: key });

  const clinic = cited("O-1", "10/07/2025", FMS, "CLINICA SANTA LTDA",
    "Contrato nº 338/2020 CPF 123.456.789-01");
  link(clinic, "O-1", "citacao_sem_confirmacao", "nenhum_contrato",
    "Contrato nº 338/2020 CPF 123.456.789-01");
  pay(payments, "O-1", "1.000,50");
  pay(payments, "O-1", "499,50");
  pay(payments, "O-1", "ilegível");
  pay(oldPayments, "O-1", "7.777,00");
  const clinicTwo = cited("O-2", "12/07/2025", FMS, "CLINICA SANTA LTDA", "contrato n° 0338/2020");
  link(clinicTwo, "O-2", "citacao_sem_confirmacao", "nenhum_contrato", "contrato n° 0338/2020");
  // Pessoa física e MEI com nome de pessoa: só no agregado, sem nome.
  const person = cited("O-3", "13/07/2025", FMS, "GABRIELA DE ALMEIDA FERNANDES",
    "Contrato de nº 070/2025");
  link(person, "O-3", "citacao_sem_confirmacao", "nenhum_contrato", "Contrato de nº 070/2025");
  pay(payments, "O-3", "300,00");
  const mei = cited("O-4", "14/07/2025", FMS, "COSME SOUZA MEDRADO - ME", "contrato 060-FMS/2023");
  link(mei, "O-4", "citacao_sem_confirmacao", "nenhum_contrato", "contrato 060-FMS/2023");
  // Mesmo número e mesmo fornecedor no PNCP: categoria à parte.
  const pncpCase = cited("O-5", "15/07/2025", "PREFEITURA MUNICIPAL DE BARREIRAS",
    "EMPRESA YPSILON LTDA", "contrato 132/2025");
  link(pncpCase, "O-5", "citacao_sem_confirmacao", "nenhum_contrato", "contrato 132/2025");
  record(pncpArtifact, "pncp_contrato", "pncp:1", {
    numeroContratoEmpenho: "132/2025", nomeRazaoSocialFornecedor: "Empresa Ypsilon Ltda.",
    niFornecedor: "00000000000191", numeroControlePNCP: "13654405000195-2-000032/2025",
  });
  // Câmara, outro ano e decisão posterior que liga o empenho ficam de fora.
  const council = cited("O-6", "16/07/2025", "CÂMARA MUNICIPAL DE BARREIRAS",
    "GRAFICA ZETA LTDA", "contrato 001/2025");
  link(council, "O-6", "citacao_sem_confirmacao", "nenhum_contrato", "contrato 001/2025");
  const otherYear = cited("O-7", "16/07/2024", FMS, "GRAFICA ZETA LTDA", "contrato 308/2023");
  link(otherYear, "O-7", "citacao_sem_confirmacao", "nenhum_contrato", "contrato 308/2023");
  const superseded = cited("O-8", "17/07/2025", FMS, "GRAFICA ZETA LTDA", "contrato 009/2025",
    oldCommitments);
  link(superseded, "O-8", "citacao_sem_confirmacao", "nenhum_contrato", "contrato 009/2025",
    "2026-09-24T12:00:00Z");
  const relinked = cited("O-8", "17/07/2025", FMS, "GRAFICA ZETA LTDA", "contrato 009/2025");
  link(relinked, "O-8", "sem_citacao", "", "", "2026-10-01T12:00:00Z");
  await database.exec(statements.join("\n"));

  const comparison = (await database.query(`select commitment_key, creditor_is_entity,
    cited_number, cited_excerpt, list_read_on::text, paid_amount::text, payments,
    unreadable_payments, category, pncp_url
    from finance.contract_citation_comparison_v1(2025) order by commitment_key`)).rows;
  assert.deepEqual(comparison.map((row) => row.commitment_key), ["O-1", "O-2", "O-3", "O-4", "O-5"]);
  assert.deepEqual(comparison[0], {
    commitment_key: "O-1", creditor_is_entity: true, cited_number: "338/2020",
    cited_excerpt: "Contrato nº 338/2020 CPF ***.***.***-**", list_read_on: "2026-09-24",
    paid_amount: "1500.00", payments: 2, unreadable_payments: 1,
    category: "sem_correspondencia", pncp_url: null,
  }, "pago exato da grade mais recente; parcela ilegível contada à parte");
  assert.equal(comparison[1].cited_number, "338/2020", "zero à esquerda não separa o grupo");
  assert.deepEqual(comparison.slice(2, 4).map((row) => row.creditor_is_entity), [false, false]);
  assert.equal(comparison[3].cited_number, "60-FMS/2023");
  assert.equal(comparison[4].category, "publicado_no_pncp");
  assert.equal(comparison[4].pncp_url, "https://pncp.gov.br/app/contratos/13654405000195/2025/32");

  const publicRows = async () => (await database.query(
    "select * from api.get_public_contract_citations(2025)")).rows;
  const waiting = await publicRows();
  assert.equal(waiting.length, 1);
  assert.equal(waiting[0].review_state, "awaiting_review");
  assert.equal(waiting[0].creditor_name, null, "nada é publicado antes da conferência");

  await assert.rejects(
    database.query("select * from api.get_contract_citation_review_sample()"),
    /revisores ativos/,
  );
  await database.exec(`
    insert into audit.reviewer_identities (auth_user_id, display_name, status, activated_at)
    values ('1575c740-fcff-4b1a-89a9-e8e5a314880a', 'Revisor de Teste', 'active',
      statement_timestamp());
    select set_config('request.jwt.claim.sub', '1575c740-fcff-4b1a-89a9-e8e5a314880a', false);
  `);
  const sample = (await database.query(
    "select * from api.get_contract_citation_review_sample()")).rows;
  assert.deepEqual(
    sample.filter((row) => row.sample_reason === "exemplo da medição")
      .map((row) => row.cited_number).sort(),
    ["308/2023", "338/2020"],
    "os dois exemplos da medição entram sempre, de qualquer ano",
  );
  assert.equal(sample.find((row) => row.cited_number === "338/2020").commitments, 2);
  assert.equal(sample.length, 5, "amostra junta todos os anos e deixa a Câmara de fora");
  assert.deepEqual(sample, (await database.query(
    "select * from api.get_contract_citation_review_sample()")).rows, "semente fixa");

  const review = (decision, note, groups) => database.query(
    "select * from api.review_contract_citation_comparison($1, $2, $3)", [decision, note, groups]);
  await assert.rejects(review("approved", "ok", 22), /justificativa/);
  await assert.rejects(review("approved", "Conferido no portal.", 0), /ao menos um grupo/);
  await review("approved", "Conferi 22 grupos no portal de contratos.", 22);

  const approved = await publicRows();
  assert.ok(approved.every((row) => row.review_state === "approved" && row.approved_at));
  assert.deepEqual(
    approved.map((row) => [row.row_kind, row.category, row.public_body, row.creditor_name,
      row.cited_number, row.commitments, row.paid_amount]),
    [
      ["entity", "sem_correspondencia", FMS, "CLINICA SANTA LTDA", "338/2020", 2, "1500.00"],
      ["pf_aggregate", "sem_correspondencia", FMS, null, null, 2, "300.00"],
      ["entity", "publicado_no_pncp", "PREFEITURA MUNICIPAL DE BARREIRAS",
        "EMPRESA YPSILON LTDA", "132/2025", 1, "0.00"],
    ],
  );
  const aggregate = approved.find((row) => row.row_kind === "pf_aggregate");
  assert.equal(aggregate.cited_excerpt, null);
  assert.equal(aggregate.latest_commitment_key, null);

  await review("withdrawn", "Retirada para nova conferência.", 0);
  assert.equal((await publicRows())[0].review_state, "awaiting_review");

  const access = await database.query(`select
    has_function_privilege('anon', 'api.get_public_contract_citations(integer)', 'EXECUTE') as public,
    has_function_privilege('anon', 'api.get_contract_citation_review_sample()', 'EXECUTE') as sample,
    has_function_privilege('anon', 'api.review_contract_citation_comparison(text, text, integer)', 'EXECUTE') as review,
    has_function_privilege('anon', 'finance.contract_citation_comparison_v1(integer)', 'EXECUTE') as internal,
    has_function_privilege('authenticated', 'finance.contract_citation_comparison_v1(integer)', 'EXECUTE') as internal_auth`);
  assert.deepEqual(access.rows[0],
    { public: true, sample: false, review: false, internal: false, internal_auth: false });
} finally {
  await database.close();
}

console.log("contract citation comparison migration test passed");
