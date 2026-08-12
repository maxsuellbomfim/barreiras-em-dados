import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { PGlite } from "@electric-sql/pglite";
import { pg_trgm } from "@electric-sql/pglite/contrib/pg_trgm";
import { pgcrypto } from "@electric-sql/pglite/contrib/pgcrypto";

const migrationsUrl = new URL("../../../supabase/migrations/", import.meta.url);
const migrationNames = (await readdir(fileURLToPath(migrationsUrl)))
  .filter((name) => name.endsWith(".sql"))
  .sort();
const migrations = await Promise.all(
  migrationNames.map((name) => readFile(fileURLToPath(new URL(name, migrationsUrl)), "utf8")),
);
const database = new PGlite({ extensions: { pgcrypto, pg_trgm } });

try {
  await database.exec(`
    create role anon nologin;
    create role authenticated nologin;
    create role authenticator nologin;
    create schema auth;
    create table auth.users (id uuid primary key);
    insert into auth.users (id) values
      ('1575c740-fcff-4b1a-89a9-e8e5a314880a'),
      ('27b3add6-f788-48e5-bf6f-50dfbd8cf198'),
      ('c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a');
    create function auth.uid() returns uuid language sql stable set search_path = ''
      as $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
    create schema storage;
    create table storage.buckets (
      id text primary key,
      name text not null,
      public boolean not null default false,
      file_size_limit bigint,
      allowed_mime_types text[]
    );
    create table storage.objects (
      id uuid primary key,
      bucket_id text not null references storage.buckets(id),
      name text not null,
      unique(bucket_id, name)
    );
    alter table storage.objects enable row level security;
    grant usage on schema storage to authenticated;
    grant select, insert, update, delete on storage.objects to authenticated;
  `);
  for (const migration of migrations) await database.exec(migration);

  const territorySchema = await database.query(`
    select to_regnamespace('territory')::text as territory_schema
  `);
  assert.deepEqual(territorySchema.rows, [{ territory_schema: "territory" }]);

  const contracts = await database.query(`
    select
      to_regclass('territory.parliamentary_transfers')::text as transfer_projection,
      to_regclass('raw.raw_records_transferegov_latest_idx')::text as latest_index,
      to_regclass('raw.raw_records_transferegov_proposal_idx')::text as proposal_index,
      to_regclass('raw.raw_records_transferegov_partnership_idx')::text as partnership_index,
      to_regclass('raw.raw_records_transferegov_document_idx')::text as document_index,
      to_regprocedure(
        'api.get_public_parliamentary_transfer_ranking(text,smallint,integer)'
      )::text as ranking_rpc,
      to_regprocedure(
        'api.get_public_parliamentary_transfers(smallint,text,integer)'
      )::text as detail_rpc,
      has_schema_privilege('anon', 'territory', 'USAGE') as anon_territory_usage,
      has_function_privilege(
        'anon',
        'api.get_public_parliamentary_transfer_ranking(text,smallint,integer)',
        'EXECUTE'
      ) as anon_ranking_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_parliamentary_transfers(smallint,text,integer)',
        'EXECUTE'
      ) as anon_detail_rpc
  `);
  assert.deepEqual(contracts.rows, [{
    transfer_projection: "territory.parliamentary_transfers",
    latest_index: "raw.raw_records_transferegov_latest_idx",
    proposal_index: "raw.raw_records_transferegov_proposal_idx",
    partnership_index: "raw.raw_records_transferegov_partnership_idx",
    document_index: "raw.raw_records_transferegov_document_idx",
    ranking_rpc:
      "api.get_public_parliamentary_transfer_ranking(text,smallint,integer)",
    detail_rpc: "api.get_public_parliamentary_transfers(smallint,text,integer)",
    anon_territory_usage: false,
    anon_ranking_rpc: true,
    anon_detail_rpc: true,
  }]);

  await database.exec(`
    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version, status
    ) values (
      '00000000-0000-0000-0000-000000009001',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'transferegov-parcerias'
         and endpoint.slug = 'propostas-barreiras'),
      'parliamentary-transfer-fixture-run', 'test/1', 'succeeded'
    );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, idempotency_key, artifact_kind,
      source_url, retrieved_at, byte_size, sha256, object_key, collector_version
    ) values (
      '00000000-0000-0000-0000-000000009002',
      '00000000-0000-0000-0000-000000009001',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'transferegov-parcerias'
         and endpoint.slug = 'propostas-barreiras'),
      'parliamentary-transfer-fixture-artifact', 'http_response',
      'https://api-publica.transferegov.gestao.gov.br/parcerias/proposta?cd_ibge_recebedor=2903201',
      '2026-08-12 18:00:00+00', 1000, '${"a".repeat(64)}',
      'fixtures/transferegov.json', 'test/1'
    );
    insert into raw.raw_records (
      id, raw_artifact_id, source_record_key, record_type, record_index,
      payload, payload_sha256, parser_version, idempotency_key, collected_at
    ) values
      (
        '00000000-0000-0000-0000-000000009010',
        '00000000-0000-0000-0000-000000009002', 'transferegov:proposta:9274',
        'transferegov_proposta', 0,
        '{"id_proposta":9274,"ano_proposta":2025,"ds_objeto":"Incremento da media e alta complexidade","vl_total_planejamento_gastos":250000,"nm_ente_recebedor":"Fundo Municipal de Saude de Barreiras","situacao_proposta":"Aprovada"}',
        '${"b".repeat(64)}', 'test/1', 'parliamentary-record-0001',
        '2026-08-12 18:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009011',
        '00000000-0000-0000-0000-000000009002', 'transferegov:distribuicao:14886',
        'transferegov_distribuicao_recurso', 1,
        '{"id_distribuicao_recurso_proposta":14886,"id_proposta":9274,"in_tipo_distribuicao":"Emenda","in_tipo_emenda_parlamentar_proposta":"Individual","nm_parlamentar_proposta":"RICARDO MAIA","nr_emenda_proposta":"2025.4460.0002","valor_emenda":250000}',
        '${"c".repeat(64)}', 'test/1', 'parliamentary-record-0002',
        '2026-08-12 18:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009012',
        '00000000-0000-0000-0000-000000009002', 'transferegov:proposta:30854',
        'transferegov_proposta', 2,
        '{"id_proposta":30854,"ano_proposta":2025,"ds_objeto":"Incremento da media e alta complexidade","vl_total_planejamento_gastos":5000000,"nm_ente_recebedor":"Fundo Municipal de Saude de Barreiras","situacao_proposta":"Aprovada"}',
        '${"d".repeat(64)}', 'test/1', 'parliamentary-record-0003',
        '2026-08-12 18:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009013',
        '00000000-0000-0000-0000-000000009002', 'transferegov:distribuicao:43389',
        'transferegov_distribuicao_recurso', 3,
        '{"id_distribuicao_recurso_proposta":43389,"id_proposta":30854,"in_tipo_distribuicao":"Emenda","in_tipo_emenda_parlamentar_proposta":"Comissao","nm_parlamentar_proposta":"COMISSAO DA SAUDE","nr_emenda_proposta":"2025.5041.0002","valor_emenda":5000000}',
        '${"e".repeat(64)}', 'test/1', 'parliamentary-record-0004',
        '2026-08-12 18:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009014',
        '00000000-0000-0000-0000-000000009002', 'transferegov:distribuicao:43389',
        'transferegov_distribuicao_recurso', 4,
        '{"id_distribuicao_recurso_proposta":43389,"id_proposta":30854,"in_tipo_distribuicao":"Emenda","in_tipo_emenda_parlamentar_proposta":"Comissao","nm_parlamentar_proposta":"COMISSAO DA SAUDE","nr_emenda_proposta":"2025.5041.0002","valor_emenda":5000000}',
        '${"f".repeat(64)}', 'test/2', 'parliamentary-record-0005',
        '2026-08-12 18:05:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009015',
        '00000000-0000-0000-0000-000000009002', 'transferegov:parceria:30785',
        'transferegov_parceria', 5,
        '{"id_parceria":30785,"id_proposta":30854,"cd_parceria":"202500030009","in_situacao_parceria":"Aprovada"}',
        '${"1".repeat(64)}', 'test/1', 'parliamentary-record-0006',
        '2026-08-12 18:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009016',
        '00000000-0000-0000-0000-000000009002', 'transferegov:empenho:11245',
        'transferegov_empenho', 6,
        '{"id_empenho_parceria":11245,"id_parceria":30785,"numero_empenho":"2025NE493599","data_emissao":"2025-10-13","valor_empenho":5000000}',
        '${"2".repeat(64)}', 'test/1', 'parliamentary-record-0007',
        '2026-08-12 18:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009017',
        '00000000-0000-0000-0000-000000009002', 'transferegov:documento-habil:5941',
        'transferegov_documento_habil', 7,
        '{"id_documento_habil":5941,"id_parceria":30785,"nr_documento_habil":"2025TF860130","dt_emissao":"2025-10-13","vl_documento_habil":5000000}',
        '${"3".repeat(64)}', 'test/1', 'parliamentary-record-0008',
        '2026-08-12 18:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009018',
        '00000000-0000-0000-0000-000000009002', 'transferegov:ordem-pagamento:5932',
        'transferegov_ordem_pagamento', 8,
        '{"id_op":5932,"id_documento_habil":5941,"nr_ordem_pagamento":"2025OP053944","dt_emissao_op":"2025-10-24","vl_ordem_pagamento":5000000,"in_situacao_op":"Paga","nr_ordem_bancaria":"2025OB055607","dt_emissao_ordem_bancaria":"2025-10-24"}',
        '${"4".repeat(64)}', 'test/1', 'parliamentary-record-0009',
        '2026-08-12 18:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009019',
        '00000000-0000-0000-0000-000000009002', 'transferegov:proposta:40000',
        'transferegov_proposta', 9,
        '{"id_proposta":40000,"ano_proposta":2025,"ds_objeto":"Apoio a atencao primaria","vl_total_planejamento_gastos":100000,"nm_ente_recebedor":"Fundo Municipal de Saude de Barreiras","situacao_proposta":"Aprovada"}',
        '${"5".repeat(64)}', 'test/1', 'parliamentary-record-0010',
        '2026-08-12 18:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009020',
        '00000000-0000-0000-0000-000000009002', 'transferegov:distribuicao:50000',
        'transferegov_distribuicao_recurso', 10,
        '{"id_distribuicao_recurso_proposta":50000,"id_proposta":40000,"in_tipo_distribuicao":"Emenda","in_tipo_emenda_parlamentar_proposta":"Individual","nm_parlamentar_proposta":"Ricardo Maia","nr_emenda_proposta":"2025.4460.0099","valor_emenda":100000}',
        '${"6".repeat(64)}', 'test/1', 'parliamentary-record-0011',
        '2026-08-12 18:00:00+00'
      );
  `);

  await database.exec("set role anon");
  const people = await database.query(`
    select author_name, author_kind, amendment_count, destination_amount,
      committed_amount, paid_amount, fully_paid_amendment_count,
      methodology_version
    from api.get_public_parliamentary_transfer_ranking('person', 2025::smallint, 50)
  `);
  const collectives = await database.query(`
    select author_name, author_kind, amendment_count, destination_amount,
      committed_amount, paid_amount, fully_paid_amendment_count,
      methodology_version
    from api.get_public_parliamentary_transfer_ranking('collective', 2025::smallint, 50)
  `);
  const transfers = await database.query(`
    select amendment_number, author_name, author_kind, destination_amount,
      committed_amount, paid_amount, bank_order_number,
      stage_attribution_status, source_url, artifact_sha256,
      methodology_version
    from api.get_public_parliamentary_transfers(2025::smallint, null, 100)
    order by destination_amount desc
  `);
  await database.exec("reset role");

  assert.deepEqual(people.rows, [{
    author_name: "RICARDO MAIA",
    author_kind: "person",
    amendment_count: 2,
    destination_amount: "350000.00",
    committed_amount: null,
    paid_amount: null,
    fully_paid_amendment_count: 0,
    methodology_version: "parliamentary-transfer-ranking/1.0.0",
  }]);
  assert.deepEqual(collectives.rows, [{
    author_name: "COMISSAO DA SAUDE",
    author_kind: "commission",
    amendment_count: 1,
    destination_amount: "5000000.00",
    committed_amount: "5000000.00",
    paid_amount: "5000000.00",
    fully_paid_amendment_count: 1,
    methodology_version: "parliamentary-transfer-ranking/1.0.0",
  }]);
  assert.deepEqual(transfers.rows, [
    {
      amendment_number: "2025.5041.0002",
      author_name: "COMISSAO DA SAUDE",
      author_kind: "commission",
      destination_amount: "5000000.00",
      committed_amount: "5000000.00",
      paid_amount: "5000000.00",
      bank_order_number: "2025OB055607",
      stage_attribution_status: "exact_single_distribution",
      source_url:
        "https://api-publica.transferegov.gestao.gov.br/parcerias/proposta?cd_ibge_recebedor=2903201",
      artifact_sha256: "a".repeat(64),
      methodology_version: "parliamentary-transfers/1.0.0",
    },
    {
      amendment_number: "2025.4460.0002",
      author_name: "RICARDO MAIA",
      author_kind: "person",
      destination_amount: "250000.00",
      committed_amount: null,
      paid_amount: null,
      bank_order_number: null,
      stage_attribution_status: "exact_single_distribution",
      source_url:
        "https://api-publica.transferegov.gestao.gov.br/parcerias/proposta?cd_ibge_recebedor=2903201",
      artifact_sha256: "a".repeat(64),
      methodology_version: "parliamentary-transfers/1.0.0",
    },
    {
      amendment_number: "2025.4460.0099",
      author_name: "Ricardo Maia",
      author_kind: "person",
      destination_amount: "100000.00",
      committed_amount: null,
      paid_amount: null,
      bank_order_number: null,
      stage_attribution_status: "exact_single_distribution",
      source_url:
        "https://api-publica.transferegov.gestao.gov.br/parcerias/proposta?cd_ibge_recebedor=2903201",
      artifact_sha256: "a".repeat(64),
      methodology_version: "parliamentary-transfers/1.0.0",
    },
  ]);

  await database.exec("set role anon");
  await assert.rejects(
    database.query("select * from territory.parliamentary_transfers"),
    /permission denied/,
  );
  await assert.rejects(
    database.query(
      "select * from api.get_public_parliamentary_transfer_ranking('all', 2025::smallint, 50)",
    ),
    /author_scope deve ser person ou collective/,
  );
  await database.exec("reset role");

  assert.equal(JSON.stringify(transfers.rows).includes("cpf"), false);
  assert.equal(JSON.stringify(transfers.rows).includes("solicitante"), false);
  console.log(
    "Emendas: autoria, estagios financeiros, deduplicacao e limites publicos verificados.",
  );
} finally {
  await database.close();
}
