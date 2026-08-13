-- Endpoint privado para o ZIP nacional de emendas. O recorte só aceita
-- propostas de Barreiras já preservadas; o identificador integral do
-- beneficiário permanece exclusivamente no artefato bruto privado.

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
  (select id from source.data_sources where slug = 'transferegov-downloads'),
  'emendas-historicas',
  'file',
  'https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/siconv_emenda.zip',
  'GET',
  2,
  180,
  true,
  jsonb_build_object(
    'parser_version', 'transferegov-historical-amendments/1.0.0',
    'archive_name', 'siconv_emenda.zip',
    'archive_member', 'siconv_emenda.csv',
    'dependency', jsonb_build_object(
      'record_type', 'transferegov_historical_proposal',
      'join_field', 'ID_PROPOSTA',
      'municipality_ibge_code', '2903201'
    ),
    'coverage_year_from', 2021,
    'raw_visibility', 'private',
    'excluded_projection_fields', jsonb_build_array(
      'BENEFICIARIO_EMENDA'
    )
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
  'migration:register-transferegov-historical-amendments',
  'source_endpoint.registered',
  'source.source_endpoints',
  endpoint.id,
  jsonb_build_object(
    'source_slug', source.slug,
    'endpoint_slug', endpoint.slug,
    'coverage_year_from', endpoint.config -> 'coverage_year_from',
    'dependency', endpoint.config -> 'dependency'
  ),
  jsonb_build_object(
    'raw_visibility', 'private',
    'beneficiary_identifier_public', false,
    'normalized_publication', 'pending_reconciliation'
  )
from source.source_endpoints as endpoint
join source.data_sources as source on source.id = endpoint.data_source_id
where source.slug = 'transferegov-downloads'
  and endpoint.slug = 'emendas-historicas';
