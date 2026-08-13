-- Catálogo oficial dos arquivos históricos de transferências discricionárias
-- e legais. Esta migration cadastra a fonte e o contrato; os ZIPs nacionais
-- continuam privados e só serão filtrados por Barreiras em etapa posterior.

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
  'transferegov-downloads',
  'Transferegov - Downloads de Dados Abertos',
  'Catálogo oficial dos arquivos históricos de transferências discricionárias e legais.',
  'official',
  true,
  'https://www.gov.br/transferegov/pt-br/ferramentas-gestao/dados-abertos',
  'https://api-publica.transferegov.gestao.gov.br/downloads',
  'active',
  jsonb_build_object(
    'scope', 'national_historical_download_catalog',
    'municipal_filter_pending', true,
    'publication', 'raw_catalog_only'
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
  (select id from source.data_sources where slug = 'transferegov-downloads'),
  'dados-abertos-catalogo',
  'file',
  'https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/',
  'GET',
  12,
  60,
  true,
  jsonb_build_object(
    'query', jsonb_build_object(
      'restype', 'container',
      'comp', 'list'
    ),
    'parser_version', 'transferegov-download-catalog/1.0.0',
    'required_files', jsonb_build_array(
      'siconv_convenio.zip',
      'siconv_desembolso.zip',
      'siconv_emenda.zip',
      'siconv_empenho.zip',
      'siconv_pagamento.zip',
      'siconv_proponentes.zip',
      'siconv_proposta.zip',
      'siconv_termo_aditivo.zip'
    ),
    'blob_host', 'trsfgovprodstrgaccpublic.blob.core.windows.net',
    'raw_only', true
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
  'migration:register-transferegov-download-catalog',
  'source_endpoint.registered',
  'source.source_endpoints',
  endpoint.id,
  jsonb_build_object(
    'source_slug', source.slug,
    'endpoint_slug', endpoint.slug,
    'required_file_count', jsonb_array_length(endpoint.config -> 'required_files')
  ),
  jsonb_build_object(
    'publication', 'raw_catalog_only',
    'downloads_started', false
  )
from source.source_endpoints as endpoint
join source.data_sources as source on source.id = endpoint.data_source_id
where source.slug = 'transferegov-downloads'
  and endpoint.slug = 'dados-abertos-catalogo';
