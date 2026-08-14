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
      to_regclass('territory.reconciled_parliamentary_transfers')::text
        as reconciled_transfer_projection,
      to_regclass('territory.bahia_state_loa_execution_reconciliation')::text
        as state_loa_execution_reconciliation,
      to_regclass(
        'territory.bahia_state_loa_execution_reconciliation_snapshot'
      )::text as state_loa_execution_reconciliation_snapshot,
      to_regclass('political.parliamentary_transfer_author_crosswalk')::text
        as author_crosswalk,
      to_regclass('political.legislative_terms')::text as legislative_terms,
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
      to_regprocedure(
        'api.get_public_reconciled_parliamentary_transfers(smallint,text,integer)'
      )::text as reconciled_transfer_rpc,
      to_regprocedure(
        'api.get_public_reconciled_parliamentary_transfer_ranking(text,smallint,integer)'
      )::text as reconciled_ranking_rpc,
      to_regprocedure(
        'api.get_public_parliamentary_transfer_reconciliation_summary()'
      )::text as reconciliation_summary_rpc,
      to_regprocedure(
        'api.get_public_bahia_state_loa_execution(smallint,text,integer)'
      )::text as state_loa_execution_rpc,
      to_regprocedure(
        'api.get_public_bahia_state_loa_execution_summary(smallint)'
      )::text as state_loa_execution_summary_rpc,
      to_regprocedure(
        'api.get_public_bahia_state_loa_representative_contributions(integer)'
      )::text as state_loa_representative_contributions_rpc,
      to_regprocedure(
        'api.get_public_parliamentary_legislature_rankings(text,smallint,integer)'
      )::text as legislature_rankings_rpc,
      to_regprocedure(
        'territory.refresh_bahia_state_loa_execution_reconciliation_snapshot()'
      )::text as state_loa_execution_snapshot_refresh,
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
      ) as anon_territorial_scope_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_reconciled_parliamentary_transfers(smallint,text,integer)',
        'EXECUTE'
      ) as anon_reconciled_transfer_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_reconciled_parliamentary_transfer_ranking(text,smallint,integer)',
        'EXECUTE'
      ) as anon_reconciled_ranking_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_parliamentary_transfer_reconciliation_summary()',
        'EXECUTE'
      ) as anon_reconciliation_summary_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_bahia_state_loa_execution(smallint,text,integer)',
        'EXECUTE'
      ) as anon_state_loa_execution_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_bahia_state_loa_execution_summary(smallint)',
        'EXECUTE'
      ) as anon_state_loa_execution_summary_rpc,
      has_function_privilege(
        'anon',
        'api.get_public_bahia_state_loa_representative_contributions(integer)',
        'EXECUTE'
      ) as anon_state_loa_representative_contributions_rpc,
      has_table_privilege(
        'anon',
        'political.legislative_terms',
        'SELECT'
      ) as anon_legislative_terms_select,
      has_function_privilege(
        'anon',
        'api.get_public_parliamentary_legislature_rankings(text,smallint,integer)',
        'EXECUTE'
      ) as anon_legislature_rankings_rpc,
      has_function_privilege(
        'anon',
        'territory.refresh_bahia_state_loa_execution_reconciliation_snapshot()',
        'EXECUTE'
      ) as anon_state_loa_execution_snapshot_refresh,
      has_function_privilege(
        'collector_worker',
        'territory.refresh_bahia_state_loa_execution_reconciliation_snapshot()',
        'EXECUTE'
      ) as worker_state_loa_execution_snapshot_refresh
  `);
  assert.deepEqual(contracts.rows, [{
    transfer_projection: "territory.parliamentary_transfers",
    historical_proposal_projection: "territory.federal_transfer_proposals",
    historical_amendment_projection:
      "territory.historical_parliamentary_amendments",
    territorial_scope_projection: "territory.federal_transfer_proposal_scope",
    reconciled_transfer_projection:
      "territory.reconciled_parliamentary_transfers",
    state_loa_execution_reconciliation:
      "territory.bahia_state_loa_execution_reconciliation",
    state_loa_execution_reconciliation_snapshot:
      "territory.bahia_state_loa_execution_reconciliation_snapshot",
    author_crosswalk: "political.parliamentary_transfer_author_crosswalk",
    legislative_terms: "political.legislative_terms",
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
    reconciled_transfer_rpc:
      "api.get_public_reconciled_parliamentary_transfers(smallint,text,integer)",
    reconciled_ranking_rpc:
      "api.get_public_reconciled_parliamentary_transfer_ranking(text,smallint,integer)",
    reconciliation_summary_rpc:
      "api.get_public_parliamentary_transfer_reconciliation_summary()",
    state_loa_execution_rpc:
      "api.get_public_bahia_state_loa_execution(smallint,text,integer)",
    state_loa_execution_summary_rpc:
      "api.get_public_bahia_state_loa_execution_summary(smallint)",
    state_loa_representative_contributions_rpc:
      "api.get_public_bahia_state_loa_representative_contributions(integer)",
    legislature_rankings_rpc:
      "api.get_public_parliamentary_legislature_rankings(text,smallint,integer)",
    state_loa_execution_snapshot_refresh:
      "territory.refresh_bahia_state_loa_execution_reconciliation_snapshot()",
    anon_territory_usage: false,
    anon_ranking_rpc: true,
    anon_detail_rpc: true,
    anon_coverage_rpc: true,
    anon_historical_proposal_rpc: true,
    anon_historical_amendment_rpc: true,
    anon_historical_amendment_ranking_rpc: true,
    anon_territorial_scope_rpc: true,
    anon_reconciled_transfer_rpc: true,
    anon_reconciled_ranking_rpc: true,
    anon_reconciliation_summary_rpc: true,
    anon_state_loa_execution_rpc: true,
    anon_state_loa_execution_summary_rpc: true,
    anon_state_loa_representative_contributions_rpc: true,
    anon_legislative_terms_select: false,
    anon_legislature_rankings_rpc: true,
    anon_state_loa_execution_snapshot_refresh: false,
    worker_state_loa_execution_snapshot_refresh: true,
  }]);

  const stateLoaPublicFunctionDefinitions = await database.query(`
    select proname, pg_get_functiondef(procedure.oid) as definition
    from pg_proc as procedure
    join pg_namespace as namespace on namespace.oid = procedure.pronamespace
    where namespace.nspname = 'api'
      and procedure.proname in (
        'get_public_bahia_state_loa_execution',
        'get_public_bahia_state_loa_execution_summary',
        'get_public_bahia_state_loa_representative_contributions'
      )
    order by proname
  `);
  for (const row of stateLoaPublicFunctionDefinitions.rows) {
    assert.match(
      row.definition,
      /territory\.bahia_state_loa_execution_reconciliation_snapshot/,
      `${row.proname} deve ler a projecao materializada`,
    );
    assert.doesNotMatch(
      row.definition,
      /from territory\.bahia_state_loa_execution_reconciliation as reconciliation/,
      `${row.proname} nao pode recalcular JSON bruto em requisicao publica`,
    );
  }

  const legislatureRankingDefinition = await database.query(`
    select pg_get_functiondef(procedure.oid) as definition
    from pg_proc as procedure
    join pg_namespace as namespace on namespace.oid = procedure.pronamespace
    where namespace.nspname = 'api'
      and procedure.proname = 'get_public_parliamentary_legislature_rankings'
  `);
  assert.equal(legislatureRankingDefinition.rows.length, 1);
  assert.match(
    legislatureRankingDefinition.rows[0].definition,
    /territory\.bahia_state_loa_execution_reconciliation_snapshot/,
    "ranking por legislatura deve usar o snapshot estadual materializado",
  );
  assert.match(
    legislatureRankingDefinition.rows[0].definition,
    /territory\.reconciled_parliamentary_transfers/,
    "ranking federal deve usar a serie reconciliada",
  );
  assert.doesNotMatch(
    legislatureRankingDefinition.rows[0].definition,
    /raw\.(raw_records|extraction_results)/,
    "RPC publica nao pode recalcular registros brutos",
  );

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
      ),
      (
        '00000000-0000-0000-0000-000000009113',
        '00000000-0000-0000-0000-000000009102',
        'transferegov:historical-proposal:9274',
        'transferegov_historical_proposal', 3,
        '{"id_proposta":"9274","numero_proposta":"000003/2025","ano_proposta":2025,"data_proposta":"20/05/2025","cod_municipio_ibge":"2903201","municipio_proponente":"BARREIRAS","proponente":"MUNICIPIO DE BARREIRAS","proponente_cnpj":"13654405000195","situacao_proposta":"PROPOSTA APROVADA","situacao_projeto_basico":"APROVADO","modalidade":"TRANSFERENCIA ESPECIAL","objeto":"APOIO A BARREIRAS","item_investimento":"CUSTEIO","orgao":"MINISTERIO DA SAUDE","orgao_superior":"MINISTERIO DA SAUDE","valor_global":"250000.00","valor_repasse":"250000.00","valor_contrapartida":"0.00"}',
        '${"5".repeat(64)}', 'test/1', 'historical-record-0004',
        '2026-08-13 10:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009114',
        '00000000-0000-0000-0000-000000009102',
        'transferegov:historical-proposal:40000',
        'transferegov_historical_proposal', 4,
        '{"id_proposta":"40000","numero_proposta":"000004/2025","ano_proposta":2025,"data_proposta":"21/05/2025","cod_municipio_ibge":"2903201","municipio_proponente":"BARREIRAS","proponente":"FUNDO MUNICIPAL DE SAUDE DE BARREIRAS","proponente_cnpj":"13654405000195","situacao_proposta":"PROPOSTA APROVADA","situacao_projeto_basico":"APROVADO","modalidade":"TRANSFERENCIA ESPECIAL","objeto":"APOIO A ATENCAO PRIMARIA EM BARREIRAS","item_investimento":"CUSTEIO","orgao":"MINISTERIO DA SAUDE","orgao_superior":"MINISTERIO DA SAUDE","valor_global":"99999.00","valor_repasse":"99999.00","valor_contrapartida":"0.00"}',
        '${"4".repeat(64)}', 'test/1', 'historical-record-0005',
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
      ),
      (
        '00000000-0000-0000-0000-000000009214',
        '00000000-0000-0000-0000-000000009202',
        'transferegov:historical-amendment:9274:2025.4460.0002:person',
        'transferegov_historical_amendment', 4,
        '{"id_proposta":"9274","numero_emenda":"2025.4460.0002","autor_nome":"RICARDO MAIA","tipo_parlamentar":"INDIVIDUAL","codigo_programa_emenda":"3600020250017","impositiva":true,"valor_repasse_emenda":"250000","valor_repasse_proposta_emenda":"250000","beneficiario_tipo":"cnpj","beneficiario_ultimos_4":"0195"}',
        '${"0".repeat(64)}', 'test/1', 'historical-amendment-record-0005',
        '2026-08-13 11:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009215',
        '00000000-0000-0000-0000-000000009202',
        'transferegov:historical-amendment:40000:2025.4460.0099:person',
        'transferegov_historical_amendment', 5,
        '{"id_proposta":"40000","numero_emenda":"2025.4460.0099","autor_nome":"RICARDO MAIA","tipo_parlamentar":"INDIVIDUAL","codigo_programa_emenda":"3600020250018","impositiva":true,"valor_repasse_emenda":"99999","valor_repasse_proposta_emenda":"99999","beneficiario_tipo":"cnpj","beneficiario_ultimos_4":"0195"}',
        '${"f".repeat(64)}', 'test/1', 'historical-amendment-record-0006',
        '2026-08-13 11:00:00+00'
      );
  `);

  await database.exec(`
    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version, status
    ) values (
      '00000000-0000-0000-0000-000000009301',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'bahia-seplan-budget'
         and endpoint.slug = 'state-loa-amendment-annexes'),
      'state-loa-public-fixture-run', 'test/1', 'succeeded'
    );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, idempotency_key, artifact_kind,
      source_url, retrieved_at, byte_size, sha256, object_key, collector_version
    ) values (
      '00000000-0000-0000-0000-000000009302',
      '00000000-0000-0000-0000-000000009301',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'bahia-seplan-budget'
         and endpoint.slug = 'state-loa-amendment-annexes'),
      'state-loa-public-fixture-artifact', 'document',
      'https://www.ba.gov.br/seplan/loa-fixture.pdf',
      '2026-08-13 18:00:00+00', 1000, '${"7".repeat(64)}',
      'fixtures/bahia-loa.pdf', 'test/1'
    );
    insert into raw.extraction_jobs (
      id, raw_artifact_id, job_type, idempotency_key, status
    ) values
      (
        '00000000-0000-0000-0000-000000009310',
        '00000000-0000-0000-0000-000000009302',
        'bahia_state_loa_authorized_amendments_v1',
        'state-loa-public-fixture-job-ok', 'succeeded'
      ),
      (
        '00000000-0000-0000-0000-000000009311',
        '00000000-0000-0000-0000-000000009302',
        'bahia_state_loa_authorized_amendments_v1',
        'state-loa-public-fixture-job-failed', 'failed'
      );
    insert into raw.extraction_results (
      id, extraction_job_id, candidate_type, extractor_version,
      validator_version, result_payload, validation_status, validation_errors,
      created_at
    ) values
      (
        '00000000-0000-0000-0000-000000009320',
        '00000000-0000-0000-0000-000000009310',
        'bahia_state_loa_authorized_amendment',
        'bahia-state-loa-barreiras/1.1.0',
        'bahia-state-loa-deterministic/1.0.0',
        '{"fiscal_year":2022,"municipality":"Barreiras","amendment_number":"101","author_external_code":null,"author_name":"Antônio Henrique Jr.","authorized_amount":"100000","official_description":"Saúde em Barreiras","annex_code":"III","budget_unit_code":"1001","agency_code":"10","action_code":"2001","page_number":10,"evidence_text":"BARREIRAS ANTONIO HENRIQUE JR 100000","financial_stage":"authorized","source_url":"https://www.ba.gov.br/seplan/loa-fixture.pdf","source_artifact_sha256":"${"7".repeat(64)}","evidence_sha256":"${"a".repeat(64)}"}',
        'valid', '[]', '2026-08-13 18:01:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009321',
        '00000000-0000-0000-0000-000000009310',
        'bahia_state_loa_authorized_amendment',
        'bahia-state-loa-barreiras/1.1.0',
        'bahia-state-loa-deterministic/1.0.0',
        '{"fiscal_year":2026,"municipality":"Barreiras","amendment_number":"102","author_external_code":"500069","author_name":"Antonio Henrique Júnior","authorized_amount":"200000","official_description":"Educação em Barreiras","annex_code":"I","budget_unit_code":"1002","agency_code":"11","action_code":"2002","page_number":11,"evidence_text":"BARREIRAS ANTONIO HENRIQUE JUNIOR 200000","financial_stage":"authorized","source_url":"https://www.ba.gov.br/seplan/loa-fixture.pdf","source_artifact_sha256":"${"7".repeat(64)}","evidence_sha256":"${"b".repeat(64)}"}',
        'valid', '[]', '2026-08-13 18:02:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009322',
        '00000000-0000-0000-0000-000000009310',
        'bahia_state_loa_authorized_amendment',
        'bahia-state-loa-barreiras/1.1.0',
        'bahia-state-loa-deterministic/1.0.0',
        '{"fiscal_year":2026,"municipality":"Barreiras","amendment_number":"103","author_external_code":"500144","author_name":"Marcone Amaral","authorized_amount":"500000","official_description":"Infraestrutura em Barreiras","annex_code":"I","budget_unit_code":"1003","agency_code":"12","action_code":"2003","page_number":12,"evidence_text":"BARREIRAS MARCONE AMARAL 500000","financial_stage":"authorized","source_url":"https://www.ba.gov.br/seplan/loa-fixture.pdf","source_artifact_sha256":"${"7".repeat(64)}","evidence_sha256":"${"c".repeat(64)}"}',
        'valid', '[]', '2026-08-13 18:03:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009323',
        '00000000-0000-0000-0000-000000009310',
        'bahia_state_loa_authorized_amendment',
        'bahia-state-loa-barreiras/1.1.0',
        'bahia-state-loa-deterministic/1.0.0',
        '{"fiscal_year":2026,"municipality":"Barreiras","amendment_number":"102","author_external_code":"500069","author_name":"Antonio Henrique Júnior","authorized_amount":"200000","official_description":"Educação em Barreiras","annex_code":"I","budget_unit_code":"1002","agency_code":"11","action_code":"2002","page_number":11,"evidence_text":"BARREIRAS ANTONIO HENRIQUE JUNIOR 200000","financial_stage":"authorized","source_url":"https://www.ba.gov.br/seplan/loa-fixture.pdf","source_artifact_sha256":"${"7".repeat(64)}","evidence_sha256":"${"b".repeat(64)}"}',
        'valid', '[]', '2026-08-13 18:04:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009324',
        '00000000-0000-0000-0000-000000009311',
        'bahia_state_loa_authorized_amendment',
        'bahia-state-loa-barreiras/1.1.0',
        'bahia-state-loa-deterministic/1.0.0',
        '{"fiscal_year":2026,"municipality":"Barreiras","amendment_number":"999","author_name":"Registro com job falho","authorized_amount":"999999","official_description":"Não publicar","page_number":99,"evidence_text":"NAO PUBLICAR","financial_stage":"authorized","source_url":"https://www.ba.gov.br/seplan/loa-fixture.pdf","source_artifact_sha256":"${"7".repeat(64)}","evidence_sha256":"${"d".repeat(64)}"}',
        'valid', '[]', '2026-08-13 18:05:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009325',
        '00000000-0000-0000-0000-000000009310',
        'bahia_state_loa_authorized_amendment',
        'bahia-state-loa-barreiras/1.1.0',
        'bahia-state-loa-deterministic/1.0.0',
        '{"fiscal_year":2023,"municipality":"Barreiras","amendment_number":"104","author_name":"Capitão Alden","authorized_amount":"700000","official_description":"Segurança em Barreiras","annex_code":"II","budget_unit_code":"1004","agency_code":"13","action_code":"2004","page_number":13,"evidence_text":"BARREIRAS CAPITAO ALDEN 700000","financial_stage":"authorized","source_url":"https://www.ba.gov.br/seplan/loa-fixture.pdf","source_artifact_sha256":"${"7".repeat(64)}","evidence_sha256":"${"e".repeat(64)}"}',
        'valid', '[]', '2026-08-13 18:06:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009326',
        '00000000-0000-0000-0000-000000009310',
        'bahia_state_loa_authorized_amendment',
        'bahia-state-loa-barreiras/1.1.0',
        'bahia-state-loa-deterministic/1.0.0',
        '{"fiscal_year":2026,"municipality":"Barreiras","amendment_number":"105","author_external_code":"500123","author_name":"Diego Castro","authorized_amount":"600000","official_description":"Saúde em Barreiras","annex_code":"II","budget_unit_code":"1005","agency_code":"14","action_code":"2005","page_number":14,"evidence_text":"BARREIRAS DIEGO CASTRO 600000","financial_stage":"authorized","source_url":"https://www.ba.gov.br/seplan/loa-fixture.pdf","source_artifact_sha256":"${"7".repeat(64)}","evidence_sha256":"${"f".repeat(64)}"}',
        'valid', '[]', '2026-08-13 18:07:00+00'
      );
  `);

  await database.exec(`
    insert into raw.extraction_jobs (
      id, raw_artifact_id, job_type, idempotency_key, status
    ) values (
      '00000000-0000-0000-0000-000000009330',
      '00000000-0000-0000-0000-000000009302',
      'bahia_state_loa_authorized_amendments_and_scope_v2',
      'state-loa-scope-fixture-job-ok', 'succeeded'
    );
    insert into raw.extraction_results (
      id, extraction_job_id, candidate_type, extractor_version,
      validator_version, result_payload, validation_status, validation_errors,
      created_at
    ) values
      (
        '00000000-0000-0000-0000-000000009331',
        '00000000-0000-0000-0000-000000009330',
        'bahia_state_loa_2026_scope_row',
        'bahia-state-loa-scope/1.0.0',
        'bahia-state-loa-deterministic/1.0.0',
        '{"fiscal_year":2026,"amendment_number":"102","author_external_code":"500069","author_name":"Antonio Henrique Junior","agency_code":"11","budget_unit_code":"1002","action_code":"2002","page_number":11,"evidence_text":"ESCOPO 102","evidence_sha256":"${"1".repeat(64)}","source_url":"https://www.ba.gov.br/seplan/loa-fixture.pdf","source_artifact_sha256":"${"7".repeat(64)}","visibility":"private_reconciliation_scope"}',
        'valid', '[]', '2026-08-14 09:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009332',
        '00000000-0000-0000-0000-000000009330',
        'bahia_state_loa_2026_scope_row',
        'bahia-state-loa-scope/1.0.0',
        'bahia-state-loa-deterministic/1.0.0',
        '{"fiscal_year":2026,"amendment_number":"103","author_external_code":"500144","author_name":"Marcone Amaral","agency_code":"12","budget_unit_code":"1003","action_code":"2003","page_number":12,"evidence_text":"ESCOPO 103 A","evidence_sha256":"${"2".repeat(64)}","source_url":"https://www.ba.gov.br/seplan/loa-fixture.pdf","source_artifact_sha256":"${"7".repeat(64)}","visibility":"private_reconciliation_scope"}',
        'valid', '[]', '2026-08-14 09:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009333',
        '00000000-0000-0000-0000-000000009330',
        'bahia_state_loa_2026_scope_row',
        'bahia-state-loa-scope/1.0.0',
        'bahia-state-loa-deterministic/1.0.0',
        '{"fiscal_year":2026,"amendment_number":"999","author_external_code":"500144","author_name":"Marcone Amaral","agency_code":"12","budget_unit_code":"1003","action_code":"2003","page_number":99,"evidence_text":"ESCOPO 103 B","evidence_sha256":"${"3".repeat(64)}","source_url":"https://www.ba.gov.br/seplan/loa-fixture.pdf","source_artifact_sha256":"${"7".repeat(64)}","visibility":"private_reconciliation_scope"}',
        'valid', '[]', '2026-08-14 09:00:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009334',
        '00000000-0000-0000-0000-000000009330',
        'bahia_state_loa_2026_scope_row',
        'bahia-state-loa-scope/1.0.0',
        'bahia-state-loa-deterministic/1.0.0',
        '{"fiscal_year":2026,"amendment_number":"105","author_external_code":"500123","author_name":"Diego Castro","agency_code":"14","budget_unit_code":"1005","action_code":"2005","page_number":14,"evidence_text":"ESCOPO 105","evidence_sha256":"${"4".repeat(64)}","source_url":"https://www.ba.gov.br/seplan/loa-fixture.pdf","source_artifact_sha256":"${"7".repeat(64)}","visibility":"private_reconciliation_scope"}',
        'valid', '[]', '2026-08-14 09:00:00+00'
      );

    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version, status
    ) values (
      '00000000-0000-0000-0000-000000009340',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'bahia-open-data'
         and endpoint.slug = 'state-parliamentary-amendments'),
      'state-execution-fixture-run', 'test/1', 'succeeded'
    );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, idempotency_key, artifact_kind,
      source_url, retrieved_at, byte_size, sha256, object_key, collector_version
    ) values (
      '00000000-0000-0000-0000-000000009341',
      '00000000-0000-0000-0000-000000009340',
      (select endpoint.id
       from source.source_endpoints endpoint
       join source.data_sources source on source.id = endpoint.data_source_id
       where source.slug = 'bahia-open-data'
         and endpoint.slug = 'state-parliamentary-amendments'),
      'state-execution-fixture-artifact', 'archive',
      'https://dados.ba.gov.br/emendas-fixture.zip',
      '2026-08-14 09:10:00+00', 1000, '${"8".repeat(64)}',
      'fixtures/bahia-execution.zip', 'test/1'
    );
    insert into raw.extraction_jobs (
      id, raw_artifact_id, job_type, idempotency_key, status
    ) values (
      '00000000-0000-0000-0000-000000009342',
      '00000000-0000-0000-0000-000000009341',
      'bahia_state_execution_aggregates_v1',
      'state-execution-fixture-job-ok', 'succeeded'
    );
    insert into raw.extraction_results (
      id, extraction_job_id, candidate_type, extractor_version,
      validator_version, result_payload, validation_status, validation_errors,
      created_at
    ) values
      (
        '00000000-0000-0000-0000-000000009343',
        '00000000-0000-0000-0000-000000009342',
        'bahia_state_execution_aggregate',
        'bahia-state-execution-aggregate/1.0.0',
        'bahia-state-execution-deterministic/1.0.0',
        '{"fiscal_year":2026,"author_external_code":"500069","author_name":"Antonio Henrique Junior","agency_code":"11","budget_unit_code":"1002","action_code":"2002","execution_code":"2026.1.1.1.1.2002.500069.1","initial_budget_amount":"200000.00","current_budget_amount":"190000.00","committed_amount":"150000.00","liquidated_amount":"100000.00","paid_amount":"90000.00","evidence_text":"EXECUCAO 102","evidence_sha256":"${"5".repeat(64)}","source_url":"https://dados.ba.gov.br/emendas-fixture.zip","source_artifact_sha256":"${"8".repeat(64)}","source_collected_at":"2026-08-14T09:10:00+00:00","territorial_scope":"not_available_in_execution_archive"}',
        'valid', '[]', '2026-08-14 09:11:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009344',
        '00000000-0000-0000-0000-000000009342',
        'bahia_state_execution_aggregate',
        'bahia-state-execution-aggregate/1.0.0',
        'bahia-state-execution-deterministic/1.0.0',
        '{"fiscal_year":2026,"author_external_code":"500123","author_name":"Diego Castro","agency_code":"14","budget_unit_code":"1005","action_code":"2005","execution_code":"2026.1.1.1.1.2005.500123.1","initial_budget_amount":"600000.00","current_budget_amount":"600000.00","committed_amount":"300000.00","liquidated_amount":"200000.00","paid_amount":"100000.00","evidence_text":"EXECUCAO 105 A","evidence_sha256":"${"6".repeat(64)}","source_url":"https://dados.ba.gov.br/emendas-fixture.zip","source_artifact_sha256":"${"8".repeat(64)}","source_collected_at":"2026-08-14T09:10:00+00:00","territorial_scope":"not_available_in_execution_archive"}',
        'valid', '[]', '2026-08-14 09:11:00+00'
      ),
      (
        '00000000-0000-0000-0000-000000009345',
        '00000000-0000-0000-0000-000000009342',
        'bahia_state_execution_aggregate',
        'bahia-state-execution-aggregate/1.0.0',
        'bahia-state-execution-deterministic/1.0.0',
        '{"fiscal_year":2026,"author_external_code":"500123","author_name":"Diego Castro","agency_code":"14","budget_unit_code":"1005","action_code":"2005","execution_code":"2026.1.1.1.1.2005.500123.2","initial_budget_amount":"100000.00","current_budget_amount":"100000.00","committed_amount":"50000.00","liquidated_amount":"40000.00","paid_amount":"30000.00","evidence_text":"EXECUCAO 105 B","evidence_sha256":"${"9".repeat(64)}","source_url":"https://dados.ba.gov.br/emendas-fixture.zip","source_artifact_sha256":"${"8".repeat(64)}","source_collected_at":"2026-08-14T09:10:00+00:00","territorial_scope":"not_available_in_execution_archive"}',
        'valid', '[]', '2026-08-14 09:11:00+00'
      );
  `);

  const stateExecutionReconciliation = await database.query(`
    select amendment_number, reconciliation_status,
      loa_scope_occurrences, execution_occurrences,
      committed_amount, liquidated_amount, paid_amount,
      execution_evidence_sha256
    from territory.bahia_state_loa_execution_reconciliation
    order by amendment_number
  `);
  assert.deepEqual(stateExecutionReconciliation.rows, [
    {
      amendment_number: "101",
      reconciliation_status: "blocked_scope_year_not_indexed",
      loa_scope_occurrences: 0,
      execution_occurrences: 0,
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      execution_evidence_sha256: null,
    },
    {
      amendment_number: "102",
      reconciliation_status: "matched_bidirectional_unique",
      loa_scope_occurrences: 1,
      execution_occurrences: 1,
      committed_amount: "150000.00",
      liquidated_amount: "100000.00",
      paid_amount: "90000.00",
      execution_evidence_sha256: "5".repeat(64),
    },
    {
      amendment_number: "103",
      reconciliation_status: "blocked_non_unique_loa_key",
      loa_scope_occurrences: 2,
      execution_occurrences: 0,
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      execution_evidence_sha256: null,
    },
    {
      amendment_number: "104",
      reconciliation_status: "blocked_scope_year_not_indexed",
      loa_scope_occurrences: 0,
      execution_occurrences: 0,
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      execution_evidence_sha256: null,
    },
    {
      amendment_number: "105",
      reconciliation_status: "blocked_non_unique_execution_key",
      loa_scope_occurrences: 1,
      execution_occurrences: 2,
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      execution_evidence_sha256: null,
    },
  ]);

  const refreshedStateExecutionSnapshot = await database.query(`
    select territory.refresh_bahia_state_loa_execution_reconciliation_snapshot()
      as refreshed_rows
  `);
  assert.deepEqual(refreshedStateExecutionSnapshot.rows, [{ refreshed_rows: 5 }]);
  const stateExecutionSnapshot = await database.query(`
    select amendment_number, reconciliation_status,
      committed_amount, liquidated_amount, paid_amount
    from territory.bahia_state_loa_execution_reconciliation_snapshot
    order by amendment_number
  `);
  assert.equal(stateExecutionSnapshot.rows.length, 5);
  assert.deepEqual(
    stateExecutionSnapshot.rows.find((row) => row.amendment_number === "102"),
    {
      amendment_number: "102",
      reconciliation_status: "matched_bidirectional_unique",
      committed_amount: "150000.00",
      liquidated_amount: "100000.00",
      paid_amount: "90000.00",
    },
  );

  const publicStateExecution = await database.query(`
    select amendment_number, execution_status,
      loa_scope_occurrences, execution_occurrences,
      authorized_amount, committed_amount, liquidated_amount, paid_amount,
      execution_source_url, execution_evidence_sha256, methodology_version
    from api.get_public_bahia_state_loa_execution(2026::smallint, null, 200)
    order by amendment_number
  `);
  assert.deepEqual(publicStateExecution.rows, [
    {
      amendment_number: "102",
      execution_status: "execution_confirmed",
      loa_scope_occurrences: 1,
      execution_occurrences: 1,
      authorized_amount: "200000.00",
      committed_amount: "150000.00",
      liquidated_amount: "100000.00",
      paid_amount: "90000.00",
      execution_source_url: "https://dados.ba.gov.br/emendas-fixture.zip",
      execution_evidence_sha256: "5".repeat(64),
      methodology_version: "bahia-state-loa-public-execution/1.1.0",
    },
    {
      amendment_number: "103",
      execution_status: "ambiguous_official_key",
      loa_scope_occurrences: 2,
      execution_occurrences: 0,
      authorized_amount: "500000.00",
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      execution_source_url: null,
      execution_evidence_sha256: null,
      methodology_version: "bahia-state-loa-public-execution/1.1.0",
    },
    {
      amendment_number: "105",
      execution_status: "ambiguous_official_key",
      loa_scope_occurrences: 1,
      execution_occurrences: 2,
      authorized_amount: "600000.00",
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      execution_source_url: null,
      execution_evidence_sha256: null,
      methodology_version: "bahia-state-loa-public-execution/1.1.0",
    },
  ]);

  const historicalStateExecution = await database.query(`
    select amendment_number, execution_status, committed_amount,
      liquidated_amount, paid_amount, execution_source_url,
      methodology_version
    from api.get_public_bahia_state_loa_execution(2022::smallint, null, 200)
    order by amendment_number
  `);
  assert.deepEqual(historicalStateExecution.rows, [{
    amendment_number: "101",
    execution_status: "official_link_key_unavailable",
    committed_amount: null,
    liquidated_amount: null,
    paid_amount: null,
    execution_source_url: null,
    methodology_version: "bahia-state-loa-public-execution/1.1.0",
  }]);

  const publicStateExecutionSummary = await database.query(`
    select fiscal_year, total_amendment_count, matched_amendment_count,
      ambiguous_amendment_count, not_found_amendment_count,
      unavailable_scope_count, authorized_total,
      matched_authorized_total, committed_total, liquidated_total, paid_total,
      methodology_version
    from api.get_public_bahia_state_loa_execution_summary(2026::smallint)
  `);
  assert.deepEqual(publicStateExecutionSummary.rows, [{
    fiscal_year: 2026,
    total_amendment_count: 3,
    matched_amendment_count: 1,
    ambiguous_amendment_count: 2,
    not_found_amendment_count: 0,
    unavailable_scope_count: 0,
    authorized_total: "1300000.00",
    matched_authorized_total: "200000.00",
    committed_total: "150000.00",
    liquidated_total: "100000.00",
    paid_total: "90000.00",
    methodology_version: "bahia-state-loa-public-execution-summary/1.0.0",
  }]);

  const stateRepresentativeContributions = await database.query(`
    select representative_source_kind, representative_external_id,
      author_key, author_name, fiscal_year, amendment_count,
      authorized_amount, matched_amendment_count, matched_authorized_amount,
      committed_amount, liquidated_amount, paid_amount,
      blocked_amendment_count, methodology_version
    from api.get_public_bahia_state_loa_representative_contributions(200)
    order by representative_source_kind, representative_external_id,
      fiscal_year desc
  `);
  assert.deepEqual(stateRepresentativeContributions.rows, [
    {
      representative_source_kind: "federal",
      representative_external_id: "220690",
      author_key: "capitao alden",
      author_name: "Capitão Alden",
      fiscal_year: 2023,
      amendment_count: 1,
      authorized_amount: "700000.00",
      matched_amendment_count: 0,
      matched_authorized_amount: null,
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      blocked_amendment_count: 1,
      methodology_version:
        "bahia-state-loa-representative-contributions/1.0.1",
    },
    {
      representative_source_kind: "state",
      representative_external_id: "921264",
      author_key: "antonio henrique junior",
      author_name: "Antonio Henrique Júnior",
      fiscal_year: 2026,
      amendment_count: 1,
      authorized_amount: "200000.00",
      matched_amendment_count: 1,
      matched_authorized_amount: "200000.00",
      committed_amount: "150000.00",
      liquidated_amount: "100000.00",
      paid_amount: "90000.00",
      blocked_amendment_count: 0,
      methodology_version:
        "bahia-state-loa-representative-contributions/1.0.1",
    },
    {
      representative_source_kind: "state",
      representative_external_id: "921264",
      author_key: "antonio henrique junior",
      author_name: "Antônio Henrique Jr.",
      fiscal_year: 2022,
      amendment_count: 1,
      authorized_amount: "100000.00",
      matched_amendment_count: 0,
      matched_authorized_amount: null,
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      blocked_amendment_count: 1,
      methodology_version:
        "bahia-state-loa-representative-contributions/1.0.1",
    },
    {
      representative_source_kind: "state",
      representative_external_id: "932099",
      author_key: "diego castro",
      author_name: "Diego Castro",
      fiscal_year: 2026,
      amendment_count: 1,
      authorized_amount: "600000.00",
      matched_amendment_count: 0,
      matched_authorized_amount: null,
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      blocked_amendment_count: 1,
      methodology_version:
        "bahia-state-loa-representative-contributions/1.0.1",
    },
  ]);

  const stateLoaDetails = await database.query(`
    select fiscal_year, amendment_number, author_name, authorized_amount,
      financial_stage, source_artifact_sha256, evidence_sha256,
      methodology_version
    from api.get_public_bahia_state_loa_amendments(null, null, 200)
  `);
  const stateLoaRanking = await database.query(`
    select rank_position, author_key, author_name, author_external_code,
      representative_source_kind, representative_external_id,
      representative_profile_url, association_status,
      amendment_count, authorized_amount, first_year, last_year,
      financial_stage, methodology_version
    from api.get_public_bahia_state_loa_amendment_ranking(null, 50)
  `);
  assert.deepEqual(stateLoaDetails.rows, [
    {
      fiscal_year: 2026,
      amendment_number: "105",
      author_name: "Diego Castro",
      authorized_amount: "600000.00",
      financial_stage: "authorized",
      source_artifact_sha256: "7".repeat(64),
      evidence_sha256: "f".repeat(64),
      methodology_version: "bahia-state-loa-amendments/1.0.0",
    },
    {
      fiscal_year: 2026,
      amendment_number: "103",
      author_name: "Marcone Amaral",
      authorized_amount: "500000.00",
      financial_stage: "authorized",
      source_artifact_sha256: "7".repeat(64),
      evidence_sha256: "c".repeat(64),
      methodology_version: "bahia-state-loa-amendments/1.0.0",
    },
    {
      fiscal_year: 2026,
      amendment_number: "102",
      author_name: "Antonio Henrique Júnior",
      authorized_amount: "200000.00",
      financial_stage: "authorized",
      source_artifact_sha256: "7".repeat(64),
      evidence_sha256: "b".repeat(64),
      methodology_version: "bahia-state-loa-amendments/1.0.0",
    },
    {
      fiscal_year: 2023,
      amendment_number: "104",
      author_name: "Capitão Alden",
      authorized_amount: "700000.00",
      financial_stage: "authorized",
      source_artifact_sha256: "7".repeat(64),
      evidence_sha256: "e".repeat(64),
      methodology_version: "bahia-state-loa-amendments/1.0.0",
    },
    {
      fiscal_year: 2022,
      amendment_number: "101",
      author_name: "Antônio Henrique Jr.",
      authorized_amount: "100000.00",
      financial_stage: "authorized",
      source_artifact_sha256: "7".repeat(64),
      evidence_sha256: "a".repeat(64),
      methodology_version: "bahia-state-loa-amendments/1.0.0",
    },
  ]);
  assert.deepEqual(stateLoaRanking.rows, [
    {
      rank_position: 1,
      author_key: "capitao alden",
      author_name: "Capitão Alden",
      author_external_code: null,
      representative_source_kind: "federal",
      representative_external_id: "220690",
      representative_profile_url:
        "https://www.camara.leg.br/deputados/220690",
      association_status: "approved_official_crosswalk",
      amendment_count: 1,
      authorized_amount: "700000.00",
      first_year: 2023,
      last_year: 2023,
      financial_stage: "authorized",
      methodology_version: "bahia-state-loa-amendment-ranking/1.2.0",
    },
    {
      rank_position: 2,
      author_key: "diego castro",
      author_name: "Diego Castro",
      author_external_code: "500123",
      representative_source_kind: "state",
      representative_external_id: "932099",
      representative_profile_url:
        "https://www.al.ba.gov.br/deputados/deputado-estadual/932099",
      association_status: "approved_official_crosswalk",
      amendment_count: 1,
      authorized_amount: "600000.00",
      first_year: 2026,
      last_year: 2026,
      financial_stage: "authorized",
      methodology_version: "bahia-state-loa-amendment-ranking/1.2.0",
    },
    {
      rank_position: 3,
      author_key: "marcone amaral",
      author_name: "Marcone Amaral",
      author_external_code: "500144",
      representative_source_kind: null,
      representative_external_id: null,
      representative_profile_url: null,
      association_status: "not_linked",
      amendment_count: 1,
      authorized_amount: "500000.00",
      first_year: 2026,
      last_year: 2026,
      financial_stage: "authorized",
      methodology_version: "bahia-state-loa-amendment-ranking/1.2.0",
    },
    {
      rank_position: 4,
      author_key: "antonio henrique junior",
      author_name: "Antonio Henrique Júnior",
      author_external_code: "500069",
      representative_source_kind: "state",
      representative_external_id: "921264",
      representative_profile_url:
        "https://www.al.ba.gov.br/deputados/deputado-estadual/921264",
      association_status: "approved_official_crosswalk",
      amendment_count: 2,
      authorized_amount: "300000.00",
      first_year: 2022,
      last_year: 2026,
      financial_stage: "authorized",
      methodology_version: "bahia-state-loa-amendment-ranking/1.2.0",
    },
  ]);

  await database.exec("set role anon");
  const federalContributionProfile = await database.query(`
    select sphere, legislature_number, author_key, total_amendment_count,
      total_ranking_amount, row_position, fiscal_year, amendment_number,
      ranking_amount, execution_status, primary_source_url,
      methodology_version
    from api.get_public_parliamentary_legislature_contributions(
      'federal', 57::smallint, 'ricardo maia', 25, 0
    )
    order by row_position
  `);
  assert.deepEqual(federalContributionProfile.rows, [{
    sphere: "federal",
    legislature_number: 57,
    author_key: "ricardo maia",
    total_amendment_count: 1,
    total_ranking_amount: "250000.00",
    row_position: 1,
    fiscal_year: 2025,
    amendment_number: "2025.4460.0002",
    ranking_amount: "250000.00",
    execution_status: "matched_exact",
    primary_source_url:
      "https://api-publica.transferegov.gestao.gov.br/parcerias/proposta?cd_ibge_recebedor=2903201",
    methodology_version:
      "parliamentary-legislature-contributions/1.0.0",
  }]);

  const stateContributionProfile = await database.query(`
    select sphere, legislature_number, author_key, total_amendment_count,
      total_ranking_amount, total_committed_amount, total_liquidated_amount,
      total_paid_amount, row_position, fiscal_year, amendment_number,
      ranking_amount, execution_status, primary_source_url,
      methodology_version
    from api.get_public_parliamentary_legislature_contributions(
      'state', 20::smallint, 'antonio henrique junior', 25, 0
    )
    order by row_position
  `);
  assert.deepEqual(stateContributionProfile.rows, [{
    sphere: "state",
    legislature_number: 20,
    author_key: "antonio henrique junior",
    total_amendment_count: 1,
    total_ranking_amount: "200000.00",
    total_committed_amount: "150000.00",
    total_liquidated_amount: "100000.00",
    total_paid_amount: "90000.00",
    row_position: 1,
    fiscal_year: 2026,
    amendment_number: "102",
    ranking_amount: "200000.00",
    execution_status: "execution_confirmed",
    primary_source_url: "https://www.ba.gov.br/seplan/loa-fixture.pdf",
    methodology_version:
      "parliamentary-legislature-contributions/1.0.0",
  }]);

  const excludedTransitionContribution = await database.query(`
    select *
    from api.get_public_parliamentary_legislature_contributions(
      'state', 20::smallint, 'capitao alden', 25, 0
    )
  `);
  assert.equal(excludedTransitionContribution.rows.length, 0);

  await assert.rejects(
    database.query(`
      select * from api.get_public_parliamentary_legislature_contributions(
        'municipal', 20::smallint, 'autor', 25, 0
      )
    `),
    /esfera legislativa deve ser federal ou state/,
  );
  await assert.rejects(
    database.query(`
      select * from api.get_public_parliamentary_legislature_contributions(
        'state', 20::smallint, '', 25, 0
      )
    `),
    /autor legislativo invalido/,
  );
  await assert.rejects(
    database.query(`
      select * from api.get_public_parliamentary_legislature_contributions(
        'state', 20::smallint, 'autor', 101, 0
      )
    `),
    /limite de contribuicoes deve estar entre 1 e 100/,
  );
  const legislatureRankings = await database.query(`
    select sphere, legislature_number, rank_position, author_key,
      representative_source_kind, association_status, amendment_count,
      ranking_amount, committed_amount, liquidated_amount, paid_amount,
      first_year, last_year, ranking_amount_stage,
      excluded_transition_years::text as excluded_transition_years,
      methodology_version
    from api.get_public_parliamentary_legislature_rankings(null, null, 10)
    order by case sphere when 'state' then 0 else 1 end,
      legislature_number desc, rank_position
  `);
  assert.deepEqual(legislatureRankings.rows, [
    {
      sphere: "state",
      legislature_number: 20,
      rank_position: 1,
      author_key: "diego castro",
      representative_source_kind: "state",
      association_status: "approved_official_crosswalk",
      amendment_count: 1,
      ranking_amount: "600000.00",
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      first_year: 2026,
      last_year: 2026,
      ranking_amount_stage: "authorized",
      excluded_transition_years: "{2023}",
      methodology_version:
        "parliamentary-legislature-transfer-ranking/1.0.0",
    },
    {
      sphere: "state",
      legislature_number: 20,
      rank_position: 2,
      author_key: "marcone amaral",
      representative_source_kind: null,
      association_status: "not_linked",
      amendment_count: 1,
      ranking_amount: "500000.00",
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      first_year: 2026,
      last_year: 2026,
      ranking_amount_stage: "authorized",
      excluded_transition_years: "{2023}",
      methodology_version:
        "parliamentary-legislature-transfer-ranking/1.0.0",
    },
    {
      sphere: "state",
      legislature_number: 20,
      rank_position: 3,
      author_key: "antonio henrique junior",
      representative_source_kind: "state",
      association_status: "approved_official_crosswalk",
      amendment_count: 1,
      ranking_amount: "200000.00",
      committed_amount: "150000.00",
      liquidated_amount: "100000.00",
      paid_amount: "90000.00",
      first_year: 2026,
      last_year: 2026,
      ranking_amount_stage: "authorized",
      excluded_transition_years: "{2023}",
      methodology_version:
        "parliamentary-legislature-transfer-ranking/1.0.0",
    },
    {
      sphere: "state",
      legislature_number: 19,
      rank_position: 1,
      author_key: "antonio henrique junior",
      representative_source_kind: "state",
      association_status: "approved_official_crosswalk",
      amendment_count: 1,
      ranking_amount: "100000.00",
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      first_year: 2022,
      last_year: 2022,
      ranking_amount_stage: "authorized",
      excluded_transition_years: "{2023}",
      methodology_version:
        "parliamentary-legislature-transfer-ranking/1.0.0",
    },
    {
      sphere: "federal",
      legislature_number: 57,
      rank_position: 1,
      author_key: "ricardo maia",
      representative_source_kind: "federal",
      association_status: "approved_official_crosswalk",
      amendment_count: 1,
      ranking_amount: "250000.00",
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      first_year: 2025,
      last_year: 2025,
      ranking_amount_stage: "destination",
      excluded_transition_years: "{2023}",
      methodology_version:
        "parliamentary-legislature-transfer-ranking/1.0.0",
    },
    {
      sphere: "federal",
      legislature_number: 56,
      rank_position: 1,
      author_key: "afonso florence",
      representative_source_kind: null,
      association_status: "not_linked",
      amendment_count: 2,
      ranking_amount: "900000.00",
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      first_year: 2021,
      last_year: 2021,
      ranking_amount_stage: "destination",
      excluded_transition_years: "{2023}",
      methodology_version:
        "parliamentary-legislature-transfer-ranking/1.0.0",
    },
  ]);
  assert.equal(
    legislatureRankings.rows.some((row) =>
      row.first_year === 2023 || row.last_year === 2023
    ),
    false,
    "2023 nao pode ser atribuido a uma legislatura sem data individual da emenda",
  );
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
  const reconciledTransfers = await database.query(`
    select proposal_id, amendment_number, author_name, author_kind,
      reconciliation_status, destination_amount, current_destination_amount,
      historical_destination_amount, committed_amount, paid_amount,
      current_source_url, historical_source_url, methodology_version
    from api.get_public_reconciled_parliamentary_transfers(
      2025::smallint,
      null,
      100
    )
    order by proposal_id, amendment_number
  `);
  const reconciledPeople = await database.query(`
    select rank_position, author_name, author_kind,
      representative_external_id, association_status, amendment_count,
      proposal_count, destination_amount, committed_amount, paid_amount,
      methodology_version
    from api.get_public_reconciled_parliamentary_transfer_ranking(
      'person',
      null,
      50
    )
  `);
  const reconciliationSummary = await database.query(`
    select current_source_row_count, historical_source_row_count,
      consolidated_row_count, exact_match_count, current_only_count,
      historical_only_count, conflict_count, rankable_row_count,
      published_destination_amount, methodology_version
    from api.get_public_parliamentary_transfer_reconciliation_summary()
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
    candidate_proposal_count: 4,
    included_proposal_count: 3,
    excluded_regional_proposal_count: 1,
    candidate_amendment_count: 6,
    included_amendment_count: 5,
    excluded_regional_amendment_count: 1,
    excluded_regional_destination_amount: "700000.00",
    methodology_version: "federal-transfer-territorial-scope/1.0.0",
  }]);
  assert.deepEqual(reconciledTransfers.rows, [
    {
      proposal_id: "30854",
      amendment_number: "2025.5041.0002",
      author_name: "COMISSAO DA SAUDE",
      author_kind: "commission",
      reconciliation_status: "current_only",
      destination_amount: "5000000.00",
      current_destination_amount: "5000000.00",
      historical_destination_amount: null,
      committed_amount: "5000000.00",
      paid_amount: "5000000.00",
      current_source_url:
        "https://api-publica.transferegov.gestao.gov.br/parcerias/proposta?cd_ibge_recebedor=2903201",
      historical_source_url: null,
      methodology_version: "reconciled-parliamentary-transfers/1.0.0",
    },
    {
      proposal_id: "40000",
      amendment_number: "2025.4460.0099",
      author_name: "RICARDO MAIA",
      author_kind: "person",
      reconciliation_status: "conflict_source_divergence",
      destination_amount: null,
      current_destination_amount: "100000.00",
      historical_destination_amount: "99999.00",
      committed_amount: null,
      paid_amount: null,
      current_source_url:
        "https://api-publica.transferegov.gestao.gov.br/parcerias/proposta?cd_ibge_recebedor=2903201",
      historical_source_url:
        "https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/siconv_emenda.zip",
      methodology_version: "reconciled-parliamentary-transfers/1.0.0",
    },
    {
      proposal_id: "9274",
      amendment_number: "2025.4460.0002",
      author_name: "RICARDO MAIA",
      author_kind: "person",
      reconciliation_status: "matched_exact",
      destination_amount: "250000.00",
      current_destination_amount: "250000.00",
      historical_destination_amount: "250000.00",
      committed_amount: null,
      paid_amount: null,
      current_source_url:
        "https://api-publica.transferegov.gestao.gov.br/parcerias/proposta?cd_ibge_recebedor=2903201",
      historical_source_url:
        "https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/siconv_emenda.zip",
      methodology_version: "reconciled-parliamentary-transfers/1.0.0",
    },
  ]);
  assert.deepEqual(reconciledPeople.rows, [
    {
      rank_position: 1,
      author_name: "AFONSO FLORENCE",
      author_kind: "person",
      representative_external_id: null,
      association_status: "not_linked",
      amendment_count: 2,
      proposal_count: 1,
      destination_amount: "900000.00",
      committed_amount: null,
      paid_amount: null,
      methodology_version:
        "reconciled-parliamentary-transfer-ranking/1.0.0",
    },
    {
      rank_position: 2,
      author_name: "RICARDO MAIA",
      author_kind: "person",
      representative_external_id: "220694",
      association_status: "approved_official_crosswalk",
      amendment_count: 1,
      proposal_count: 1,
      destination_amount: "250000.00",
      committed_amount: null,
      paid_amount: null,
      methodology_version:
        "reconciled-parliamentary-transfer-ranking/1.0.0",
    },
  ]);
  assert.deepEqual(reconciliationSummary.rows, [{
    current_source_row_count: 3,
    historical_source_row_count: 5,
    consolidated_row_count: 6,
    exact_match_count: 1,
    current_only_count: 1,
    historical_only_count: 3,
    conflict_count: 1,
    rankable_row_count: 5,
    published_destination_amount: "6450000.00",
    methodology_version: "parliamentary-transfer-reconciliation/1.0.0",
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
    database.query("select * from political.legislative_terms"),
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
      "select * from api.get_public_parliamentary_legislature_rankings('municipal', null, 10)",
    ),
    /esfera legislativa deve ser federal ou state/,
  );
  await assert.rejects(
    database.query(
      "select * from api.get_public_parliamentary_legislature_rankings(null, null, 11)",
    ),
    /limite por legislatura deve estar entre 1 e 10/,
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
    database.query("select * from territory.reconciled_parliamentary_transfers"),
    /permission denied/,
  );
  await assert.rejects(
    database.query("select * from territory.bahia_state_loa_amendments"),
    /permission denied/,
  );
  await assert.rejects(
    database.query(
      "select * from territory.bahia_state_loa_execution_reconciliation",
    ),
    /permission denied/,
  );
  await assert.rejects(
    database.query(
      "select * from territory.bahia_state_loa_execution_reconciliation_snapshot",
    ),
    /permission denied/,
  );
  await assert.rejects(
    database.query(
      "select territory.refresh_bahia_state_loa_execution_reconciliation_snapshot()",
    ),
    /permission denied/,
  );
  await assert.rejects(
    database.query(
      "select * from api.get_public_bahia_state_loa_amendments(null, null, 201)",
    ),
    /limite de emendas estaduais da LOA invalido/,
  );
  await assert.rejects(
    database.query(
      "select * from api.get_public_bahia_state_loa_execution(2026::smallint, null, 201)",
    ),
    /limite da execucao estadual da LOA invalido/,
  );
  await assert.rejects(
    database.query(
      "select * from api.get_public_bahia_state_loa_representative_contributions(201)",
    ),
    /limite das contribuicoes estaduais por representante invalido/,
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
