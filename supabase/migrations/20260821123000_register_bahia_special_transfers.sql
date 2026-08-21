begin;

-- A fonte contém CPF/CNPJ de credores em uma view. O ZIP permanece em
-- corredor privado; esta migration não cria projeção pública de linhas.

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
        'cgu/sancoes/'
      ]
    )
  );

comment on constraint storage_workload_identities_object_prefix_check
  on audit.storage_workload_identities is
  'Corredores fechados por fonte; Transferencias Especiais permanece privada por conter identificadores de credores.';

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
  'bahia-special-transfers-collector',
  'c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a',
  'raw-artifacts',
  'bahia/transferencias-especiais/',
  true,
  true,
  'active',
  statement_timestamp(),
  jsonb_build_object(
    'purpose', 'bahia_special_transfers_raw_artifacts',
    'raw_visibility', 'private',
    'restricted_identifier_column', true,
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
  'state-special-transfers',
  'file',
  'https://dados.ba.gov.br/dataset/f2ecd7fa-24ce-4be2-80d5-08e2c11e3e1c/resource/809f9b7d-c252-482d-9c92-f2169d48c29c/download/transferenciasespeciais.zip',
  'GET',
  6,
  120,
  true,
  jsonb_build_object(
    'catalog_url', 'https://dados.ba.gov.br/api/3/action/package_show?id=transferencias-especiais',
    'dataset_id', 'f2ecd7fa-24ce-4be2-80d5-08e2c11e3e1c',
    'resource_id', '809f9b7d-c252-482d-9c92-f2169d48c29c',
    'parser_version', 'bahia-special-transfer-archive/1.0.0',
    'required_member_count', 5,
    'territorial_scope', 'payment_object_text_only',
    'normalization', 'blocked_pending_deterministic_reconciliation',
    'raw_visibility', 'private',
    'restricted_identifier_column', 'CNPJ_CPF_CREDOR_PAGAMENTO'
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
  'migration:register-bahia-special-transfers',
  'source_endpoint.registered',
  'source.source_endpoints',
  endpoint.id,
  jsonb_build_object(
    'source_slug', source.slug,
    'endpoint_slug', endpoint.slug,
    'territorial_scope', endpoint.config -> 'territorial_scope'
  ),
  jsonb_build_object(
    'raw_visibility', 'private',
    'public_projection_created', false,
    'personal_identifiers_exposed', false,
    'secret_values_persisted', false
  )
from source.source_endpoints as endpoint
join source.data_sources as source on source.id = endpoint.data_source_id
where source.slug = 'bahia-open-data'
  and endpoint.slug = 'state-special-transfers';

commit;
