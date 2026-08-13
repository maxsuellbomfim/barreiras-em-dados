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
const migrationContents = await Promise.all(
  migrationNames.map((name) => readFile(fileURLToPath(new URL(name, migrationsUrl)), "utf8")),
);
const rankingMigrationIndex = migrationNames.indexOf(
  "20260812211202_parliamentary_transfer_rankings.sql",
);
assert.notEqual(rankingMigrationIndex, -1, "migration de ranking nao encontrada");
const baselineMigrations = migrationContents.slice(0, rankingMigrationIndex + 1);
const laterMigrations = migrationContents.slice(rankingMigrationIndex + 1);
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
  for (const migration of baselineMigrations) await database.exec(migration);

  const postgrestNotifications = [];
  const stopListening = await database.listen("pgrst", (payload) => {
    postgrestNotifications.push(payload);
  });
  for (const migration of laterMigrations) await database.exec(migration);
  await new Promise((resolve) => setImmediate(resolve));
  await stopListening();
  assert.ok(
    postgrestNotifications.includes("reload schema"),
    "migrations posteriores ao ranking devem recarregar o schema do PostgREST",
  );

  const territorySchema = await database.query(`
    select to_regnamespace('territory')::text as territory_schema
  `);
  assert.deepEqual(territorySchema.rows, [{ territory_schema: "territory" }]);

  const contracts = await database.query(`
    select
      to_regclass('territory.parliamentary_transfers')::text as transfer_projection,
      to_regclass('territory.federal_transfer_proposals')::text
        as historical_proposal_projection,
      to_regclass('territory.historical_parliamentary_amendments')::text
        as historical_amendment_projection,
      to_regclass('territory.federal_transfer_proposal_scope')::text
        as territorial_scope_projection,
      to_regclass('political.parliamentary_transfer_author_crosswalk')::text
        as author_crosswalk,
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
      to_regprocedure(
        'api.get_public_parliamentary_transfer_coverage(smallint,smallint)'
      )::text as coverage_rpc,
      to_regprocedure(
        'api.get_public_federal_transfer_proposals(smallint,text,integer)'
      )::text as historical_proposal_rpc,
      to_regprocedure(
        'api.get_public_historical_parliamentary_amendments(smallint,text,integer)'
      )::text as historical_amendment_rpc,
      to_regprocedure(
        'api.get_public_historical_parliamentary_amendment_ranking(text,smallint,integer)'
      )::text as historical_amendment_ranking_rpc,
      to_regprocedure(
        'api.get_public_federal_transfer_scope_summary()'
      )::text as territorial_scope_rpc,
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
      ) as anon_detail_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_parliamentary_transfer_coverage(smallint,smallint)',
        'EXECUTE'
      ) as anon_coverage_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_federal_transfer_proposals(smallint,text,integer)',
        'EXECUTE'
      ) as anon_historical_proposal_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_historical_parliamentary_amendments(smallint,text,integer)',
        'EXECUTE'
      ) as anon_historical_amendment_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_historical_parliamentary_amendment_ranking(text,smallint,integer)',
        'EXECUTE'
      ) as anon_historical_amendment_ranking_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_federal_transfer_scope_summary()',
        'EXECUTE'
      ) as anon_territorial_scope_rpc
  `);
  assert.deepEqual(contracts.rows, [{
    transfer_projection: "territory.parliamentary_transfers",
    historical_proposal_projection: "territory.federal_transfer_proposals",
    historical_amendment_projection:
      "territory.historical_parliamentary_amendments",
    territorial_scope_projection: "territory.federal_transfer_proposal_scope",
    author_crosswalk: "political.parliamentary_transfer_author_crosswalk",
    latest_index: "raw.raw_records_transferegov_latest_idx",
    proposal_index: "raw.raw_records_transferegov_proposal_idx",
    partnership_index: "raw.raw_records_transferegov_partnership_idx",
    document_index: "raw.raw_records_transferegov_document_idx",
    ranking_rpc:
      "api.get_public_parliamentary_transfer_ranking(text,smallint,integer)",
    detail_rpc: "api.get_public_parliamentary_transfers(smallint,text,integer)",
    coverage_rpc:
      "api.get_public_parliamentary_transfer_coverage(smallint,smallint)",
    historical_proposal_rpc:
      "api.get_public_federal_transfer_proposals(smallint,text,integer)",
    historical_amendment_rpc:
      "api.get_public_historical_parliamentary_amendments(smallint,text,integer)",
    historical_amendment_ranking_rpc:
      "api.get_public_historical_parliamentary_amendment_ranking(text,smallint,integer)",
    territorial_scope_rpc: "api.get_public_federal_transfer_scope_summary()",
    anon_territory_usage: false,
    anon_ranking_rpc: true,
    anon_detail_rpc: true,
    anon_coverage_rpc: true,
    anon_historical_proposal_rpc: true,
    anon_historical_amendment_rpc: true,
    anon_historical_amendment_ranking_rpc: true,
    anon_territorial_scope_rpc: true,
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
    insert into source.collection_partitions (
      source_endpoint_id, partition_key, period_start, period_end, status,
      observed_records, collection_run_id, checkpoint, last_attempted_at,
      completed_at
    ) values
      (
        (select endpoint.id
         from source.source_endpoints endpoint
         join source.data_sources source on source.id = endpoint.data_source_id
         where source.slug = 'transferegov-parcerias'
           and endpoint.slug = 'propostas-barreiras'),
        'fiscal-year:2021', '2021-01-01', '2021-12-31', 'empty', 0,
        '00000000-0000-0000-0000-000000009001',
        '{"fiscal_year":2021,"proposal_records":0}',
        '2026-08-12 17:00:00+00', '2026-08-12 17:00:01+00'
      ),
      (
        (select endpoint.id
         from source.source_endpoints endpoint
         join source.data_sources source on source.id = endpoint.data_source_id
         where source.slug = 'transferegov-parcerias'
           and endpoint.slug = 'propostas-barreiras'),
        'fiscal-year:2025', '2025-01-01', '2025-12-31', 'complete', 11,
        '00000000-0000-0000-0000-000000009001',
        '{"fiscal_year":2025,"proposal_records":3}',
        '2026-08-12 18:00:00+00', '2026-08-12 18:00:01+00'
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

  await database.exec(`
    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version, status
    ) values (
      '00000000-0000-0000-0000-000000009101',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'transferegov-downloads'
         and endpoint.slug = 'propostas-historicas'),
      'historical-proposal-fixture-run', 'test/1', 'succeeded'
    );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, idempotency_key, artifact_kind,
      source_url, retrieved_at, byte_size, sha256, object_key, collector_version
    ) values (
      '00000000-0000-0000-0000-000000009102',
      '00000000-0000-0000-0000-000000009101',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'transferegov-downloads'
         and endpoint.slug = 'propostas-historicas'),
      'historical-proposal-fixture-artifact', 'archive',
      'https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/siconv_proposta.zip',
      '2026-08-13 10:00:00+00', 205017763, '${"9".repeat(64)}',
      'fixtures/siconv_proposta.zip', 'test/1'
    );
    insert into raw.raw_records (
      id, raw_artifact_id, source_record_key, record_type, record_index,
      payload, payload_sha256, parser_version, idempotency_key, collected_at
    ) values
      (
        '00000000-0000-0000-0000-000000009110',
        '00000000-0000-0000-0000-000000009102',
        'transferegov:historical-proposal:9001',
        'transferegov_historical_proposal', 0,
        '{"id_proposta":"9001","numero_proposta":"000001/2021","ano_proposta":2021,"data_proposta":"15/06/2021","cod_municipio_ibge":"2903201","municipio_proponente":"BARREIRAS","proponente":"MUNICIPIO DE BARREIRAS","proponente_cnpj":"13654405000195","situacao_proposta":"PROPOSTA EM ANALISE","situacao_projeto_basico":"EM ANALISE","modalidade":"CONVENIO","objeto":"VERSAO ANTIGA","item_investimento":"INFRAESTRUTURA","orgao":"MINISTERIO DO DESENVOLVIMENTO","orgao_superior":"MINISTERIO DO DESENVOLVIMENTO","valor_global":"1250000.50","valor_repasse":"1200000.50","valor_contrapartida":"50000.00","agencia":"NAO PUBLICAR"}',
        '${"8".repeat(64)}', 'test/1', 'historical-record-0001',
        '2026-08-13 09:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009111',
        '00000000-0000-0000-0000-000000009102',
        'transferegov:historical-proposal:9001',
        'transferegov_historical_proposal', 1,
        '{"id_proposta":"9001","numero_proposta":"000001/2021","ano_proposta":2021,"data_proposta":"15/06/2021","cod_municipio_ibge":"2903201","municipio_proponente":"BARREIRAS","proponente":"MUNICIPIO DE BARREIRAS","proponente_cnpj":"13654405000195","situacao_proposta":"PROPOSTA APROVADA","situacao_projeto_basico":"APROVADO","modalidade":"CONVENIO","objeto":"CONSTRUIR EQUIPAMENTO PUBLICO","item_investimento":"INFRAESTRUTURA","orgao":"MINISTERIO DO DESENVOLVIMENTO","orgao_superior":"MINISTERIO DO DESENVOLVIMENTO","valor_global":"1250000.50","valor_repasse":"1200000.50","valor_contrapartida":"50000.00","conta":"NAO PUBLICAR"}',
        '${"7".repeat(64)}', 'test/2', 'historical-record-0002',
        '2026-08-13 10:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009112',
        '00000000-0000-0000-0000-000000009102',
        'transferegov:historical-proposal:9002',
        'transferegov_historical_proposal', 2,
        '{"id_proposta":"9002","numero_proposta":"000002/2021","ano_proposta":2021,"data_proposta":"16/06/2021","cod_municipio_ibge":"2903201","municipio_proponente":"BARREIRAS","proponente":"CONSORCIO MULTIFINALITARIO DO OESTE DA BAHIA","proponente_cnpj":"00000000000000","situacao_proposta":"PROPOSTA APROVADA","situacao_projeto_basico":"APROVADO","modalidade":"CONVENIO","objeto":"PAVIMENTACAO NO MUNICIPIO DE BARRA-BA","item_investimento":"INFRAESTRUTURA","orgao":"MINISTERIO DO DESENVOLVIMENTO","orgao_superior":"MINISTERIO DO DESENVOLVIMENTO","valor_global":"700000.00","valor_repasse":"700000.00","valor_contrapartida":"0.00"}',
        '${"6".repeat(64)}', 'test/1', 'historical-record-0003',
        '2026-08-13 10:00:00+00'
      );
  `);

  await database.exec(`
    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version, status
    ) values (
      '00000000-0000-0000-0000-000000009201',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'transferegov-downloads'
         and endpoint.slug = 'emendas-historicas'),
      'historical-amendment-fixture-run', 'test/1', 'succeeded'
    );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, idempotency_key, artifact_kind,
      source_url, retrieved_at, byte_size, sha256, object_key, collector_version
    ) values (
      '00000000-0000-0000-0000-000000009202',
      '00000000-0000-0000-0000-000000009201',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'transferegov-downloads'
         and endpoint.slug = 'emendas-historicas'),
      'historical-amendment-fixture-artifact', 'archive',
      'https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/siconv_emenda.zip',
      '2026-08-13 11:00:00+00', 8306000, '${"5".repeat(64)}',
      'fixtures/siconv_emenda.zip', 'test/1'
    );
    insert into raw.raw_records (
      id, raw_artifact_id, source_record_key, record_type, record_index,
      payload, payload_sha256, parser_version, idempotency_key, collected_at
    ) values
      (
        '00000000-0000-0000-0000-000000009210',
        '00000000-0000-0000-0000-000000009202',
        'transferegov:historical-amendment:9001:11110001:person',
        'transferegov_historical_amendment', 0,
        '{"id_proposta":"9001","numero_emenda":"11110001","autor_nome":"AFONSO FLORENCE","tipo_parlamentar":"INDIVIDUAL","codigo_programa_emenda":"5300020210017","impositiva":true,"valor_repasse_emenda":"400000","valor_repasse_proposta_emenda":"900000","beneficiario_tipo":"cnpj","beneficiario_ultimos_4":"0195"}',
        '${"4".repeat(64)}', 'test/1', 'historical-amendment-record-0001',
        '2026-08-13 11:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009211',
        '00000000-0000-0000-0000-000000009202',
        'transferegov:historical-amendment:9001:11110002:person',
        'transferegov_historical_amendment', 1,
        '{"id_proposta":"9001","numero_emenda":"11110002","autor_nome":"AFONSO FLORENCE","tipo_parlamentar":"INDIVIDUAL","codigo_programa_emenda":"5300020210017","impositiva":true,"valor_repasse_emenda":"500000","valor_repasse_proposta_emenda":"900000","beneficiario_tipo":"cnpj","beneficiario_ultimos_4":"0195"}',
        '${"3".repeat(64)}', 'test/1', 'historical-amendment-record-0002',
        '2026-08-13 11:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009212',
        '00000000-0000-0000-0000-000000009202',
        'transferegov:historical-amendment:9001:50070003:commission',
        'transferegov_historical_amendment', 2,
        '{"id_proposta":"9001","numero_emenda":"50070003","autor_nome":"COM. TURISMO","tipo_parlamentar":"COMISSAO","codigo_programa_emenda":"5400020210017","impositiva":false,"valor_repasse_emenda":"300000","valor_repasse_proposta_emenda":"300000","beneficiario_tipo":"cnpj","beneficiario_ultimos_4":"0195"}',
        '${"2".repeat(64)}', 'test/1', 'historical-amendment-record-0003',
        '2026-08-13 11:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009213',
        '00000000-0000-0000-0000-000000009202',
        'transferegov:historical-amendment:9002:50070004:commission',
        'transferegov_historical_amendment', 3,
        '{"id_proposta":"9002","numero_emenda":"50070004","autor_nome":"COM. TURISMO","tipo_parlamentar":"COMISSAO","codigo_programa_emenda":"5400020210018","impositiva":false,"valor_repasse_emenda":"700000","valor_repasse_proposta_emenda":"700000","beneficiario_tipo":"cnpj","beneficiario_ultimos_4":"0000"}',
        '${"1".repeat(64)}', 'test/1', 'historical-amendment-record-0004',
        '2026-08-13 11:00:00+00'
      );
  `);

  await database.exec("set role anon");
  const people = await database.query(`
    select author_name, author_kind, representative_source_kind,
      representative_external_id, representative_profile_url,
      association_status, amendment_count, destination_amount,
      committed_amount, paid_amount, fully_paid_amendment_count,
      methodology_version
    from api.get_public_parliamentary_transfer_ranking('person', 2025::smallint, 50)
  `);
  const collectives = await database.query(`
    select author_name, author_kind, representative_source_kind,
      representative_external_id, representative_profile_url,
      association_status, amendment_count, destination_amount,
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
  const coverage = await database.query(`
    select fiscal_year, coverage_status, proposal_count,
      published_amendment_count,
      to_char(
        last_attempted_at at time zone 'UTC',
        'YYYY-MM-DD"T"HH24:MI:SS"Z"'
      ) as last_attempted_at,
      methodology_version
    from api.get_public_parliamentary_transfer_coverage(
      2021::smallint,
      2025::smallint
    )
    where fiscal_year in (2021, 2022, 2025)
    order by fiscal_year
  `);
  const historicalProposals = await database.query(`
    select proposal_id, proposal_number, fiscal_year, proposal_date_text,
      proposal_status, basic_project_status, modality, object_description,
      investment_item, proponent_name, federal_body_name,
      superior_federal_body_name, global_amount, requested_transfer_amount,
      counterpart_amount, authorship_status, financial_stage,
      source_url, artifact_sha256, methodology_version
    from api.get_public_federal_transfer_proposals(
      2021::smallint,
      'PROPOSTA APROVADA',
      100
    )
  `);
  const historicalAmendments = await database.query(`
    select proposal_id, fiscal_year, amendment_number, author_name,
      author_kind, is_mandatory, destination_amount, beneficiary_name,
      object_description, financial_stage, source_url, artifact_sha256,
      methodology_version
    from api.get_public_historical_parliamentary_amendments(
      2021::smallint,
      null,
      100
    )
    order by destination_amount desc
  `);
  const historicalPeople = await database.query(`
    select rank_position, author_name, author_kind, amendment_count,
      proposal_count, destination_amount, first_year, last_year,
      financial_stage, methodology_version
    from api.get_public_historical_parliamentary_amendment_ranking(
      'person',
      2021::smallint,
      50
    )
  `);
  const historicalCollectives = await database.query(`
    select rank_position, author_name, author_kind, amendment_count,
      proposal_count, destination_amount, first_year, last_year,
      financial_stage, methodology_version
    from api.get_public_historical_parliamentary_amendment_ranking(
      'collective',
      2021::smallint,
      50
    )
  `);
  const territorialScope = await database.query(`
    select candidate_proposal_count, included_proposal_count,
      excluded_regional_proposal_count, candidate_amendment_count,
      included_amendment_count, excluded_regional_amendment_count,
      excluded_regional_destination_amount, methodology_version
    from api.get_public_federal_transfer_scope_summary()
  `);
  await database.exec("reset role");

  assert.deepEqual(people.rows, [{
    author_name: "RICARDO MAIA",
    author_kind: "person",
    representative_source_kind: "federal",
    representative_external_id: "220694",
    representative_profile_url: "https://www.camara.leg.br/deputados/220694",
    association_status: "approved_official_crosswalk",
    amendment_count: 2,
    destination_amount: "350000.00",
    committed_amount: null,
    paid_amount: null,
    fully_paid_amendment_count: 0,
    methodology_version: "parliamentary-transfer-ranking/1.1.0",
  }]);
  assert.deepEqual(collectives.rows, [{
    author_name: "COMISSAO DA SAUDE",
    author_kind: "commission",
    representative_source_kind: null,
    representative_external_id: null,
    representative_profile_url: null,
    association_status: "not_applicable_collective",
    amendment_count: 1,
    destination_amount: "5000000.00",
    committed_amount: "5000000.00",
    paid_amount: "5000000.00",
    fully_paid_amendment_count: 1,
    methodology_version: "parliamentary-transfer-ranking/1.1.0",
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
  assert.deepEqual(coverage.rows, [
    {
      fiscal_year: 2021,
      coverage_status: "empty",
      proposal_count: 0,
      published_amendment_count: 0,
      last_attempted_at: "2026-08-12T17:00:00Z",
      methodology_version: "parliamentary-transfer-coverage/1.0.0",
    },
    {
      fiscal_year: 2022,
      coverage_status: "unclassified",
      proposal_count: null,
      published_amendment_count: null,
      last_attempted_at: null,
      methodology_version: "parliamentary-transfer-coverage/1.0.0",
    },
    {
      fiscal_year: 2025,
      coverage_status: "complete",
      proposal_count: 3,
      published_amendment_count: 3,
      last_attempted_at: "2026-08-12T18:00:00Z",
      methodology_version: "parliamentary-transfer-coverage/1.0.0",
    },
  ]);
  assert.deepEqual(historicalProposals.rows, [{
    proposal_id: "9001",
    proposal_number: "000001/2021",
    fiscal_year: 2021,
    proposal_date_text: "15/06/2021",
    proposal_status: "PROPOSTA APROVADA",
    basic_project_status: "APROVADO",
    modality: "CONVENIO",
    object_description: "CONSTRUIR EQUIPAMENTO PUBLICO",
    investment_item: "INFRAESTRUTURA",
    proponent_name: "MUNICIPIO DE BARREIRAS",
    federal_body_name: "MINISTERIO DO DESENVOLVIMENTO",
    superior_federal_body_name: "MINISTERIO DO DESENVOLVIMENTO",
    global_amount: "1250000.50",
    requested_transfer_amount: "1200000.50",
    counterpart_amount: "50000.00",
    authorship_status: "not_available_in_proposal_source",
    financial_stage: "proposal_registered",
    source_url:
      "https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/siconv_proposta.zip",
    artifact_sha256: "9".repeat(64),
    methodology_version: "federal-transfer-proposals/1.0.0",
  }]);
  assert.deepEqual(historicalAmendments.rows, [
    {
      proposal_id: "9001",
      fiscal_year: 2021,
      amendment_number: "11110002",
      author_name: "AFONSO FLORENCE",
      author_kind: "person",
      is_mandatory: true,
      destination_amount: "500000.00",
      beneficiary_name: "MUNICIPIO DE BARREIRAS",
      object_description: "CONSTRUIR EQUIPAMENTO PUBLICO",
      financial_stage: "destination_identified_payment_not_verified",
      source_url:
        "https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/siconv_emenda.zip",
      artifact_sha256: "5".repeat(64),
      methodology_version: "historical-parliamentary-amendments/1.0.0",
    },
    {
      proposal_id: "9001",
      fiscal_year: 2021,
      amendment_number: "11110001",
      author_name: "AFONSO FLORENCE",
      author_kind: "person",
      is_mandatory: true,
      destination_amount: "400000.00",
      beneficiary_name: "MUNICIPIO DE BARREIRAS",
      object_description: "CONSTRUIR EQUIPAMENTO PUBLICO",
      financial_stage: "destination_identified_payment_not_verified",
      source_url:
        "https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/siconv_emenda.zip",
      artifact_sha256: "5".repeat(64),
      methodology_version: "historical-parliamentary-amendments/1.0.0",
    },
    {
      proposal_id: "9001",
      fiscal_year: 2021,
      amendment_number: "50070003",
      author_name: "COM. TURISMO",
      author_kind: "commission",
      is_mandatory: false,
      destination_amount: "300000.00",
      beneficiary_name: "MUNICIPIO DE BARREIRAS",
      object_description: "CONSTRUIR EQUIPAMENTO PUBLICO",
      financial_stage: "destination_identified_payment_not_verified",
      source_url:
        "https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/siconv_emenda.zip",
      artifact_sha256: "5".repeat(64),
      methodology_version: "historical-parliamentary-amendments/1.0.0",
    },
  ]);
  assert.deepEqual(historicalPeople.rows, [{
    rank_position: 1,
    author_name: "AFONSO FLORENCE",
    author_kind: "person",
    amendment_count: 2,
    proposal_count: 1,
    destination_amount: "900000.00",
    first_year: 2021,
    last_year: 2021,
    financial_stage: "destination_identified_payment_not_verified",
    methodology_version:
      "historical-parliamentary-amendment-ranking/1.0.0",
  }]);
  assert.deepEqual(historicalCollectives.rows, [{
    rank_position: 1,
    author_name: "COM. TURISMO",
    author_kind: "commission",
    amendment_count: 1,
    proposal_count: 1,
    destination_amount: "300000.00",
    first_year: 2021,
    last_year: 2021,
    financial_stage: "destination_identified_payment_not_verified",
    methodology_version:
      "historical-parliamentary-amendment-ranking/1.0.0",
  }]);
  assert.deepEqual(territorialScope.rows, [{
    candidate_proposal_count: 2,
    included_proposal_count: 1,
    excluded_regional_proposal_count: 1,
    candidate_amendment_count: 4,
    included_amendment_count: 3,
    excluded_regional_amendment_count: 1,
    excluded_regional_destination_amount: "700000.00",
    methodology_version: "federal-transfer-territorial-scope/1.0.0",
  }]);

  await database.exec("set role anon");
  await assert.rejects(
    database.query("select * from territory.parliamentary_transfers"),
    /permission denied/,
  );
  await assert.rejects(
    database.query("select * from political.parliamentary_transfer_author_crosswalk"),
    /permission denied/,
  );
  await assert.rejects(
    database.query("select * from source.collection_partitions"),
    /permission denied/,
  );
  await assert.rejects(
    database.query(
      "select * from api.get_public_parliamentary_transfer_ranking('all', 2025::smallint, 50)",
    ),
    /author_scope deve ser person ou collective/,
  );
  await assert.rejects(
    database.query(
      "select * from api.get_public_parliamentary_transfer_coverage(2025::smallint, 2024::smallint)",
    ),
    /intervalo fiscal invalido/,
  );
  await assert.rejects(
    database.query(
      "select * from api.get_public_federal_transfer_proposals(null, null, 201)",
    ),
    /limite de propostas invalido/,
  );
  await assert.rejects(
    database.query("select * from territory.federal_transfer_proposals"),
    /permission denied/,
  );
  await assert.rejects(
    database.query("select * from territory.federal_transfer_proposal_scope"),
    /permission denied/,
  );
  await assert.rejects(
    database.query("select * from territory.historical_parliamentary_amendments"),
    /permission denied/,
  );
  await assert.rejects(
    database.query(
      "select * from api.get_public_historical_parliamentary_amendment_ranking('all', null, 50)",
    ),
    /author_scope deve ser person ou collective/,
  );
  await assert.rejects(
    database.query(
      "select * from api.get_public_historical_parliamentary_amendments(null, null, 201)",
    ),
    /limite de emendas historicas invalido/,
  );
  await database.exec("reset role");

  assert.equal(JSON.stringify(transfers.rows).includes("cpf"), false);
  assert.equal(JSON.stringify(transfers.rows).includes("solicitante"), false);
  assert.equal(JSON.stringify(historicalProposals.rows).includes("cnpj"), false);
  assert.equal(JSON.stringify(historicalProposals.rows).includes("conta"), false);
  assert.equal(JSON.stringify(historicalProposals.rows).includes("agencia"), false);
  assert.equal(JSON.stringify(historicalAmendments.rows).includes("cnpj"), false);
  assert.equal(JSON.stringify(historicalAmendments.rows).includes("ultimos_4"), false);
  console.log(
    "Emendas: autoria, estagios financeiros, deduplicacao e limites publicos verificados.",
  );
} finally {
  await database.close();
}
