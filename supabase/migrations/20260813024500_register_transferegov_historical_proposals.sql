-- Endpoint privado para o ZIP nacional de propostas e seu recorte municipal.
-- A evidência integral permanece no bucket privado; a projeção exclui agência,
-- conta, endereço e demais campos sem necessidade para o rastro do recurso.

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
  'propostas-historicas',
  'file',
  'https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/siconv_proposta.zip',
  'GET',
  2,
  300,
  true,
  jsonb_build_object(
    'parser_version', 'transferegov-historical-proposals/1.0.0',
    'archive_name', 'siconv_proposta.zip',
    'archive_member', 'siconv_proposta.csv',
    'municipal_filter', jsonb_build_object(
      'field', 'COD_MUNIC_IBGE',
      'value', '2903201'
    ),
    'coverage_year_from', 2021,
    'raw_visibility', 'private',
    'excluded_projection_fields', jsonb_build_array(
      'CEP_PROPONENTE',
      'ENDERECO_PROPONENTE',
      'BAIRRO_PROPONENTE',
      'NM_BANCO',
      'SITUACAO_CONTA',
      'CD_AGENCIA',
      'CD_CONTA'
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

update source.data_sources
set metadata = metadata || jsonb_build_object(
  'municipal_filter_pending', false,
  'historical_proposals_period_start', 2021,
  'historical_raw_visibility', 'private'
)
where slug = 'transferegov-downloads';

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
  'migration:register-transferegov-historical-proposals',
  'source_endpoint.registered',
  'source.source_endpoints',
  endpoint.id,
  jsonb_build_object(
    'source_slug', source.slug,
    'endpoint_slug', endpoint.slug,
    'coverage_year_from', endpoint.config -> 'coverage_year_from',
    'municipal_filter', endpoint.config -> 'municipal_filter'
  ),
  jsonb_build_object(
    'raw_visibility', 'private',
    'bank_fields_public', false,
    'normalized_publication', 'pending_reconciliation'
  )
from source.source_endpoints as endpoint
join source.data_sources as source on source.id = endpoint.data_source_id
where source.slug = 'transferegov-downloads'
  and endpoint.slug = 'propostas-historicas';
