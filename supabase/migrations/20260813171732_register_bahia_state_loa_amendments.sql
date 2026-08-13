begin;

-- Os anexos da LOA possuem municipio e autor, mas representam autorizacao
-- orcamentaria. Nenhuma linha desta migration e publicada como paga ou recebida.

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
        'bahia/loa-emendas-estaduais/'
      ]
    )
  );

comment on constraint storage_workload_identities_object_prefix_check
  on audit.storage_workload_identities is
  'Corredores fechados por fonte; inclui PDFs privados dos anexos anuais da LOA da Bahia.';

update storage.buckets
set allowed_mime_types = array(
  select distinct mime_type
  from unnest(
    coalesce(allowed_mime_types, array[]::text[])
    || array['application/pdf']::text[]
  ) as mime_type
  order by mime_type
)
where id = 'raw-artifacts';

insert into audit.storage_workload_identities (
  slug, auth_user_id, bucket_id, object_prefix, can_select, can_insert,
  status, activated_at, metadata
)
values (
  'bahia-state-loa-amendments-collector',
  'c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a',
  'raw-artifacts',
  'bahia/loa-emendas-estaduais/',
  true,
  true,
  'active',
  statement_timestamp(),
  jsonb_build_object(
    'purpose', 'bahia_state_loa_amendment_annex_raw_artifacts',
    'budget_stage', 'authorized',
    'territorial_scope', 'municipality_explicit',
    'credentials', 'stored_outside_database_and_repository'
  )
)
on conflict (auth_user_id, object_prefix) do update
set slug = excluded.slug,
    can_select = excluded.can_select,
    can_insert = excluded.can_insert,
    status = excluded.status,
    activated_at = excluded.activated_at,
    metadata = excluded.metadata;

insert into source.data_sources (
  slug, name, description, authority_level, is_official, homepage_url,
  documentation_url, status, metadata
)
values (
  'bahia-seplan-budget',
  'Secretaria do Planejamento do Estado da Bahia - LOA',
  'Anexos oficiais da Lei Orcamentaria Anual com emendas parlamentares individuais por municipio e autor.',
  'official',
  true,
  'https://www.ba.gov.br/seplan/orcamento/historico-de-loa',
  'https://www.ba.gov.br/seplan/orcamento/historico-de-loa',
  'active',
  jsonb_build_object(
    'document_family', 'loa_individual_amendment_annexes',
    'supported_years', jsonb_build_array(2022, 2023, 2024, 2025, 2026),
    'blocked_years', jsonb_build_object(
      '2021', 'official_2021_annex_iii_link_points_to_2020_document'
    ),
    'budget_stage', 'authorized',
    'territorial_scope', 'municipality_explicit',
    'publication', 'raw_only_until_document_processing'
  )
)
on conflict (slug) do update
set name = excluded.name,
    description = excluded.description,
    authority_level = excluded.authority_level,
    is_official = excluded.is_official,
    homepage_url = excluded.homepage_url,
    documentation_url = excluded.documentation_url,
    status = excluded.status,
    metadata = excluded.metadata;

insert into source.source_endpoints (
  data_source_id, slug, endpoint_kind, base_url, http_method,
  rate_limit_per_minute, request_timeout_seconds, enabled, config
)
values (
  (select id from source.data_sources where slug = 'bahia-seplan-budget'),
  'state-loa-amendment-annexes',
  'file',
  'https://www.ba.gov.br/seplan/orcamento/historico-de-loa',
  'GET',
  6,
  120,
  true,
  jsonb_build_object(
    'collector_version', 'bahia-state-loa-amendment-annex-collector/1.0.0',
    'parser_version', 'bahia-state-loa-amendment-annex/1.0.0',
    'supported_years', jsonb_build_array(2022, 2023, 2024, 2025, 2026),
    'blocked_years', jsonb_build_object(
      '2021', 'official_2021_annex_iii_link_points_to_2020_document'
    ),
    'budget_stage', 'authorized',
    'territorial_scope', 'municipality_explicit',
    'raw_visibility', 'private',
    'financial_values_normalized', false
  )
)
on conflict (data_source_id, slug) do update
set endpoint_kind = excluded.endpoint_kind,
    base_url = excluded.base_url,
    http_method = excluded.http_method,
    rate_limit_per_minute = excluded.rate_limit_per_minute,
    request_timeout_seconds = excluded.request_timeout_seconds,
    enabled = excluded.enabled,
    config = excluded.config;

insert into audit.audit_events (
  actor_type, actor_subject, action, target_type, target_id,
  after_state, metadata
)
select
  'administrator',
  'migration:register-bahia-state-loa-amendments',
  'source_endpoint.registered',
  'source.source_endpoints',
  endpoint.id,
  jsonb_build_object(
    'source_slug', source.slug,
    'endpoint_slug', endpoint.slug,
    'budget_stage', endpoint.config -> 'budget_stage',
    'territorial_scope', endpoint.config -> 'territorial_scope'
  ),
  jsonb_build_object(
    'raw_visibility', 'private',
    'public_ranking_created', false,
    'financial_values_normalized', false,
    'secret_values_persisted', false
  )
from source.source_endpoints as endpoint
join source.data_sources as source on source.id = endpoint.data_source_id
where source.slug = 'bahia-seplan-budget'
  and endpoint.slug = 'state-loa-amendment-annexes';

commit;
