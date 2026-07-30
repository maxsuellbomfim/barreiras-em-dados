insert into source.data_sources (
  id,
  slug,
  name,
  description,
  authority_level,
  is_official,
  homepage_url,
  documentation_url,
  status
)
values (
  '00000000-0000-4000-8000-000000000001',
  'querido-diario',
  'Querido Diário',
  'Agregador de diários oficiais municipais mantido pela Open Knowledge Brasil.',
  'official_aggregator',
  false,
  'https://queridodiario.ok.org.br/',
  'https://docs.queridodiario.ok.org.br/',
  'active'
)
on conflict (slug) do update
set
  name = excluded.name,
  description = excluded.description,
  documentation_url = excluded.documentation_url,
  status = excluded.status;

insert into source.source_endpoints (
  id,
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
  '00000000-0000-4000-8000-000000000101',
  '00000000-0000-4000-8000-000000000001',
  'gazettes-api',
  'api',
  'https://api.queridodiario.ok.org.br/gazettes',
  'GET',
  60,
  30,
  true,
  '{"territory_id":"2903201","municipality":"Barreiras","state_code":"BA"}'::jsonb
)
on conflict (data_source_id, slug) do update
set
  base_url = excluded.base_url,
  rate_limit_per_minute = excluded.rate_limit_per_minute,
  request_timeout_seconds = excluded.request_timeout_seconds,
  enabled = excluded.enabled,
  config = excluded.config;

insert into source.data_sources (
  id,
  slug,
  name,
  description,
  authority_level,
  is_official,
  homepage_url,
  documentation_url,
  status
)
values
(
  '00000000-0000-4000-8000-000000000002',
  'prefeitura-barreiras-transparencia',
  'Portal da Transparência da Prefeitura de Barreiras',
  'API oficial de contratos, processos, documentos fiscais, RH e prestação de contas.',
  'official',
  true,
  'https://portaldatransparencia.barreiras.ba.gov.br/',
  'https://portaldatransparencia.barreiras.ba.gov.br/dados-abertos/',
  'active'
),
(
  '00000000-0000-4000-8000-000000000003',
  'camara-barreiras-transparencia',
  'Portal da Transparência da Câmara Municipal de Barreiras',
  'API oficial de contratos, atos, documentos, RH e atividade legislativa.',
  'official',
  true,
  'https://portaldatransparencia.cmbarreiras.ba.gov.br/',
  'https://portaldatransparencia.cmbarreiras.ba.gov.br/dados-abertos/',
  'active'
)
on conflict (slug) do update
set
  name = excluded.name,
  description = excluded.description,
  documentation_url = excluded.documentation_url,
  status = excluded.status;

insert into source.source_endpoints (
  id,
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
  '00000000-0000-4000-8000-000000000102',
  (
    select id
    from source.data_sources
    where slug = 'prefeitura-barreiras-transparencia'
  ),
  'dados-abertos-api',
  'api',
  'https://portaldatransparencia.barreiras.ba.gov.br/api',
  'GET',
  10,
  30,
  true,
  '{
    "resource_count_observed": 51,
    "observed_at": "2026-07-30",
    "pagination": {
      "limit": 50,
      "offset": 0,
      "count_semantics": "returned_rows",
      "total_available": false
    },
    "rate_limit_basis": "conservative-local-policy"
  }'::jsonb
),
(
  '00000000-0000-4000-8000-000000000103',
  (
    select id
    from source.data_sources
    where slug = 'camara-barreiras-transparencia'
  ),
  'dados-abertos-api',
  'api',
  'https://portaldatransparencia.cmbarreiras.ba.gov.br/api',
  'GET',
  10,
  30,
  true,
  '{
    "resource_count_observed": 28,
    "observed_at": "2026-07-30",
    "pagination": {
      "limit": 50,
      "offset": 0,
      "count_semantics": "returned_rows",
      "total_available": false
    },
    "rate_limit_basis": "conservative-local-policy"
  }'::jsonb
)
on conflict (data_source_id, slug) do update
set
  base_url = excluded.base_url,
  rate_limit_per_minute = excluded.rate_limit_per_minute,
  request_timeout_seconds = excluded.request_timeout_seconds,
  enabled = excluded.enabled,
  config = excluded.config;

insert into storage.buckets (
  id,
  name,
  public,
  file_size_limit,
  allowed_mime_types
)
values (
  'raw-artifacts',
  'raw-artifacts',
  false,
  104857600,
  array[
    'application/json',
    'application/pdf',
    'application/octet-stream',
    'text/html',
    'text/plain'
  ]::text[]
)
on conflict (id) do update
set
  public = false,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;
