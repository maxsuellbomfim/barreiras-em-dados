-- Catálogo estruturado da Prefeitura: edição, título, resumo e data.
-- O HTML é preservado em raw.raw_artifacts; cada publicação é um raw_record.

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
select
  source.id,
  'catalogo-publicacoes',
  'html',
  'https://pmbarreiras.diariomtransparente.com.br/publicacoes',
  'GET',
  10,
  30,
  true,
  jsonb_build_object(
    'territory_id', '2903201',
    'parser_version', 'barreiras-diario-catalog/1.0.0',
    'discovery', 'official catalogue with edition, title, summary and date'
  )
from source.data_sources as source
where source.slug = 'barreiras-diario-oficial'
on conflict (data_source_id, slug) do update
set
  base_url = excluded.base_url,
  endpoint_kind = excluded.endpoint_kind,
  rate_limit_per_minute = excluded.rate_limit_per_minute,
  request_timeout_seconds = excluded.request_timeout_seconds,
  enabled = excluded.enabled,
  config = excluded.config;

comment on table source.source_endpoints is
  'Endpoints oficiais e agregadores cadastrados com limites e parser versionado.';

