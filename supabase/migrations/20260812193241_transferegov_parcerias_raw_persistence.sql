-- Preservacao bruta da API publica de Gestao de Parcerias do Transferegov.
-- Esta etapa nao normaliza nem soma valores: somente registra a evidencia
-- oficial, seus metadados e a cobertura da execucao.

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
        'transferegov/parcerias/'
      ]
    )
  );

comment on constraint storage_workload_identities_object_prefix_check
  on audit.storage_workload_identities is
  'Corredores fechados por fonte; inclui respostas brutas de parcerias do Transferegov.';

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
  'transferegov-parcerias-collector',
  '1575c740-fcff-4b1a-89a9-e8e5a314880a',
  'raw-artifacts',
  'transferegov/parcerias/',
  true,
  true,
  'active',
  statement_timestamp(),
  jsonb_build_object(
    'purpose', 'transferegov_parcerias_raw_artifacts',
    'scope', 'barreiras_ibge_2903201',
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
  'transferegov-parcerias',
  'Transferegov - Gestao de Parcerias',
  'API oficial de propostas, distribuicoes de recursos e parcerias destinadas a Barreiras.',
  'official',
  true,
  'https://www.gov.br/transferegov/pt-br',
  'https://api-publica.transferegov.gestao.gov.br/parcerias/docs',
  'active',
  jsonb_build_object(
    'territory', 'Barreiras/BA',
    'ibge_code', 2903201,
    'publication', 'raw_only_until_normalization'
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
values
  (
    (select id from source.data_sources where slug = 'transferegov-parcerias'),
    'propostas-barreiras',
    'api',
    'https://api-publica.transferegov.gestao.gov.br/parcerias/proposta',
    'GET',
    30,
    60,
    true,
    jsonb_build_object(
      'required_filter', jsonb_build_object('cd_ibge_recebedor', 2903201),
      'parser_version', 'transferegov-parcerias-page/1.0.0',
      'contains_financial_stage', false
    )
  ),
  (
    (select id from source.data_sources where slug = 'transferegov-parcerias'),
    'distribuicoes-proposta',
    'api',
    'https://api-publica.transferegov.gestao.gov.br/parcerias/distribuicao-recurso-proposta',
    'GET',
    30,
    60,
    true,
    jsonb_build_object(
      'required_parent', 'validated_barreiras_proposal',
      'parser_version', 'transferegov-parcerias-page/1.0.0',
      'financial_semantics', 'distribution_is_not_payment'
    )
  ),
  (
    (select id from source.data_sources where slug = 'transferegov-parcerias'),
    'parcerias-proposta',
    'api',
    'https://api-publica.transferegov.gestao.gov.br/parcerias/parceria',
    'GET',
    30,
    60,
    true,
    jsonb_build_object(
      'required_parent', 'validated_barreiras_proposal',
      'parser_version', 'transferegov-parcerias-page/1.0.0',
      'financial_semantics', 'partnership_is_not_payment'
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
  'migration:transferegov-parcerias-raw-persistence',
  'storage_workload_identity.activated',
  'audit.storage_workload_identities',
  identity.slug,
  jsonb_build_object(
    'bucket_id', identity.bucket_id,
    'object_prefix', identity.object_prefix,
    'can_select', identity.can_select,
    'can_insert', identity.can_insert,
    'can_update', false,
    'can_delete', false
  ),
  jsonb_build_object(
    'source', 'explicit-transferegov-collector-corridor',
    'secret_values_persisted', false
  )
from audit.storage_workload_identities as identity
where identity.slug = 'transferegov-parcerias-collector';
