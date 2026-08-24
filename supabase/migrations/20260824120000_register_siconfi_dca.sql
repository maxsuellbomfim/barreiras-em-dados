begin;

-- A DCA é preservada como bruto privado. Esta migration cadastra a fonte e o
-- corredor de Storage, mas não cria indicador nem projeção pública financeira.

alter table audit.storage_workload_identities
  drop constraint if exists storage_workload_identities_object_prefix_check;

alter table audit.storage_workload_identities
  add constraint storage_workload_identities_object_prefix_check
  check (
    object_prefix = any (
      array[
        'querido-diario/gazettes/',
        'barreiras-diario/gazettes/',
        'pncp/procurement/',
        'camara-federal/deputados/',
        'alba/deputados/',
        'camara-municipal/vereadores/',
        'tse/votacao/',
        'municipal-transparency/',
        'prefeitura/executivo/',
        'transferegov/parcerias/',
        'bahia/emendas-estaduais/',
        'bahia/loa-emendas-estaduais/',
        'bahia/transferencias-especiais/',
        'cgu/emendas-federais/',
        'cgu/sancoes/',
        'siconfi/dca/'
      ]
    )
  );

comment on constraint storage_workload_identities_object_prefix_check
  on audit.storage_workload_identities is
  'Corredores privados fechados por fonte; inclui as páginas anuais da DCA do SICONFI.';

insert into audit.storage_workload_identities (
  slug,
  auth_user_id,
  bucket_id,
  object_prefix,
  can_select,
  can_insert,
  status,
  activated_at,
  metadata
)
values (
  'siconfi-dca-collector',
  'c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a',
  'raw-artifacts',
  'siconfi/dca/',
  true,
  true,
  'active',
  statement_timestamp(),
  jsonb_build_object(
    'purpose', 'siconfi_dca_raw_pages',
    'raw_visibility', 'private',
    'financial_grain', 'annual_source_line',
    'credentials', 'stored_outside_database_and_repository'
  )
)
on conflict (auth_user_id, object_prefix) do update
set
  slug = excluded.slug,
  can_select = excluded.can_select,
  can_insert = excluded.can_insert,
  status = excluded.status,
  activated_at = excluded.activated_at,
  metadata = excluded.metadata;

insert into source.data_sources (
  slug,
  name,
  description,
  authority_level,
  is_official,
  homepage_url,
  documentation_url,
  status,
  metadata
)
values (
  'siconfi-barreiras',
  'Tesouro Nacional - SICONFI',
  'Demonstrativos fiscais e contábeis oficiais de Barreiras publicados no SICONFI.',
  'official',
  true,
  'https://siconfi.tesouro.gov.br/siconfi/',
  'https://apidatalake.tesouro.gov.br/docs/siconfi/',
  'active',
  jsonb_build_object(
    'municipality_ibge_code', '2903201',
    'coverage_year_from', 2021,
    'first_resource', 'DCA',
    'grain', 'annual_source_line',
    'monthly_finance_substitute', false
  )
)
on conflict (slug) do update
set
  name = excluded.name,
  description = excluded.description,
  authority_level = excluded.authority_level,
  is_official = excluded.is_official,
  homepage_url = excluded.homepage_url,
  documentation_url = excluded.documentation_url,
  status = excluded.status,
  metadata = excluded.metadata;

insert into source.source_endpoints (
  data_source_id,
  slug,
  endpoint_kind,
  base_url,
  http_method,
  rate_limit_per_minute,
  request_timeout_seconds,
  enabled,
  config
)
values (
  (select id from source.data_sources where slug = 'siconfi-barreiras'),
  'dca',
  'api',
  'https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca',
  'GET',
  60,
  60,
  true,
  jsonb_build_object(
    'collector_version', 'siconfi-dca-collector/1.0.0',
    'parser_version', 'siconfi-dca-page/1.0.0',
    'municipality_ibge_code', '2903201',
    'coverage_year_from', 2021,
    'page_size', 5000,
    'grain', 'annual_source_line',
    'raw_visibility', 'private',
    'public_projection', 'pending_deterministic_reconciliation',
    'monthly_finance_substitute', false
  )
)
on conflict (data_source_id, slug) do update
set
  endpoint_kind = excluded.endpoint_kind,
  base_url = excluded.base_url,
  http_method = excluded.http_method,
  rate_limit_per_minute = excluded.rate_limit_per_minute,
  request_timeout_seconds = excluded.request_timeout_seconds,
  enabled = excluded.enabled,
  config = excluded.config;

insert into audit.audit_events (
  actor_type,
  actor_subject,
  action,
  target_type,
  target_id,
  after_state,
  metadata
)
select
  'administrator',
  'migration:register-siconfi-dca',
  'source_endpoint.registered',
  'source.source_endpoints',
  endpoint.id,
  jsonb_build_object(
    'source_slug', source.slug,
    'endpoint_slug', endpoint.slug,
    'grain', endpoint.config -> 'grain',
    'coverage_year_from', endpoint.config -> 'coverage_year_from'
  ),
  jsonb_build_object(
    'raw_visibility', 'private',
    'public_projection_created', false,
    'monthly_finance_substitute', false,
    'secret_values_persisted', false
  )
from source.source_endpoints as endpoint
join source.data_sources as source on source.id = endpoint.data_source_id
where source.slug = 'siconfi-barreiras'
  and endpoint.slug = 'dca';

commit;
