begin;

-- Primeira etapa estadual: preservar o catálogo CKAN e o ZIP integral. As
-- cinco views atuais não publicam município; nenhuma linha é atribuída a
-- Barreiras ou exposta como ranking por esta migration.

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
        'bahia/emendas-estaduais/'
      ]
    )
  );

comment on constraint storage_workload_identities_object_prefix_check
  on audit.storage_workload_identities is
  'Corredores fechados por fonte; inclui catálogo e ZIP privado de emendas estaduais da Bahia.';

update storage.buckets
set allowed_mime_types = array(
  select distinct mime_type
  from unnest(
    coalesce(allowed_mime_types, array[]::text[])
    || array['application/json', 'application/zip', 'application/octet-stream']::text[]
  ) as mime_type
  order by mime_type
)
where id = 'raw-artifacts';

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
  'bahia-state-amendments-collector',
  '1575c740-fcff-4b1a-89a9-e8e5a314880a',
  'raw-artifacts',
  'bahia/emendas-estaduais/',
  true,
  true,
  'active',
  statement_timestamp(),
  jsonb_build_object(
    'purpose', 'bahia_state_amendment_raw_artifacts',
    'territorial_scope', 'not_available_in_archive',
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
  'bahia-open-data',
  'Portal de Dados Abertos do Estado da Bahia',
  'Catálogo e arquivo diário de emendas parlamentares estaduais originados no FIPLAN/SEFAZ-BA.',
  'official',
  true,
  'https://dados.ba.gov.br/pt_BR/dataset/emendas-parlamentares',
  'https://dados.ba.gov.br/api/3/action/package_show?id=emendas-parlamentares',
  'active',
  jsonb_build_object(
    'dataset_id', '1436b3e7-6594-4683-bfa5-b2e3a6c69e07',
    'publisher_system', 'FIPLAN',
    'declared_update_frequency', 'daily_previous_day',
    'territorial_scope', 'not_available_in_archive',
    'publication', 'raw_only_until_official_territorial_key'
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
  (select id from source.data_sources where slug = 'bahia-open-data'),
  'state-parliamentary-amendments',
  'file',
  'https://dados.ba.gov.br/dataset/1436b3e7-6594-4683-bfa5-b2e3a6c69e07/resource/2d284f2e-79cc-4e3c-a45b-6fc903a6e2d0/download/emendasparlamentares.zip',
  'GET',
  6,
  120,
  true,
  jsonb_build_object(
    'catalog_url', 'https://dados.ba.gov.br/api/3/action/package_show?id=emendas-parlamentares',
    'dataset_id', '1436b3e7-6594-4683-bfa5-b2e3a6c69e07',
    'resource_id', '2d284f2e-79cc-4e3c-a45b-6fc903a6e2d0',
    'parser_version', 'bahia-state-amendment-archive/1.1.0',
    'required_member_count', 5,
    'territorial_scope', 'not_available_in_archive',
    'normalization', 'blocked_until_official_territorial_key',
    'raw_visibility', 'private'
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
  'migration:register-bahia-state-amendments',
  'source_endpoint.registered',
  'source.source_endpoints',
  endpoint.id,
  jsonb_build_object(
    'source_slug', source.slug,
    'endpoint_slug', endpoint.slug,
    'territorial_scope', endpoint.config -> 'territorial_scope',
    'required_member_count', endpoint.config -> 'required_member_count'
  ),
  jsonb_build_object(
    'raw_visibility', 'private',
    'public_ranking_created', false,
    'financial_values_normalized', false,
    'secret_values_persisted', false
  )
from source.source_endpoints as endpoint
join source.data_sources as source on source.id = endpoint.data_source_id
where source.slug = 'bahia-open-data'
  and endpoint.slug = 'state-parliamentary-amendments';

commit;
