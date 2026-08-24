begin;

-- O catálogo mensal do e-TCM é bruto privado. Esta migration cadastra a
-- fonte e autoriza apenas o prefixo fechado usado pelo worker.
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
        'siconfi/dca/',
        'tcm-ba/monthly/'
      ]
    )
  );

comment on constraint storage_workload_identities_object_prefix_check
  on audit.storage_workload_identities is
  'Corredores privados fechados por fonte; inclui o catálogo mensal do e-TCM.';

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
  'tcm-ba-monthly-catalog-collector',
  'c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a',
  'raw-artifacts',
  'tcm-ba/monthly/',
  true,
  true,
  'active',
  statement_timestamp(),
  jsonb_build_object(
    'purpose', 'tcm_ba_monthly_catalog_raw_responses',
    'raw_visibility', 'private',
    'municipality', 'Barreiras',
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
  'tcm-ba',
  'Tribunal de Contas dos Municípios da Bahia',
  'Prestações de contas e documentos mensais remetidos pelos municípios ao TCM-BA.',
  'official',
  true,
  'https://www.tcm.ba.gov.br/',
  'https://e.tcm.ba.gov.br/epp/ConsultaPublica/listView.seam',
  'active',
  jsonb_build_object(
    'municipality', 'Barreiras',
    'municipality_ibge_code', '2903201',
    'coverage_month_from', '2021-01',
    'first_validated_competence', '2023-04',
    'raw_visibility', 'private'
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
  (select id from source.data_sources where slug = 'tcm-ba'),
  'prestacoes-contas-mensais',
  'html',
  'https://e.tcm.ba.gov.br/epp/ConsultaPublica/listView.seam',
  'GET',
  30,
  45,
  true,
  jsonb_build_object(
    'collector_version', 'tcm-ba-monthly-catalog-collector/1.0.0',
    'parser_version', 'tcm-ba-monthly-catalog/1.0.0',
    'municipality', 'BARREIRAS',
    'accounting_unit', 'Prefeitura Municipal de BARREIRAS',
    'periodicity', 'Mensal',
    'session_http_methods', jsonb_build_array('GET', 'POST'),
    'coverage_month_from', '2021-01',
    'page_size', 10,
    'raw_visibility', 'private',
    'public_projection', 'pending_deterministic_reconciliation'
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
  'migration:register-tcm-ba-monthly-catalog',
  'source_endpoint.registered',
  'source.source_endpoints',
  endpoint.id,
  jsonb_build_object(
    'source_slug', source.slug,
    'endpoint_slug', endpoint.slug,
    'coverage_month_from', endpoint.config -> 'coverage_month_from'
  ),
  jsonb_build_object(
    'raw_visibility', 'private',
    'public_projection_created', false,
    'secret_values_persisted', false
  )
from source.source_endpoints as endpoint
join source.data_sources as source on source.id = endpoint.data_source_id
where source.slug = 'tcm-ba'
  and endpoint.slug = 'prestacoes-contas-mensais';

commit;
