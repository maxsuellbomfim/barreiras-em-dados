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
  '00000000-0000-4000-8000-000000000004',
  'barreiras-diario-oficial',
  'Diário Oficial do Município de Barreiras',
  'Edições oficiais em PDF publicadas pela Prefeitura, coletadas direto da origem.',
  'official',
  true,
  'https://barreiras.ba.gov.br/diario-oficial/',
  'https://pmbarreiras.diariomtransparente.com.br/publicacoes',
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
  '00000000-0000-4000-8000-000000000104',
  '00000000-0000-4000-8000-000000000004',
  'pdf-direto',
  'file',
  'https://barreiras.ba.gov.br/diario/pdf/',
  'GET',
  10,
  60,
  true,
  '{
    "territory_id": "2903201",
    "url_pattern": "https://barreiras.ba.gov.br/diario/pdf/{ano}/diario{edicao}.pdf",
    "edition_numbering": "sequential",
    "observed_at": "2026-08-01",
    "discovery": "docs/reviews/STAGE_1B_DIRECT_DIARY_DISCOVERY.md"
  }'::jsonb
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
values (
  '00000000-0000-4000-8000-000000000005',
  'pncp',
  'Portal Nacional de Contratações Públicas',
  'Cadastro, contratações e contratos publicados por força da Lei 14.133/2021.',
  'official',
  true,
  'https://pncp.gov.br/',
  'https://www.gov.br/pncp/pt-br/acesso-a-informacao/dados-abertos',
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
  '00000000-0000-4000-8000-000000000105',
  '00000000-0000-4000-8000-000000000005',
  'registry-api',
  'api',
  'https://pncp.gov.br/api/pncp/v1/orgaos/',
  'GET',
  10,
  35,
  true,
  '{
    "cnpj": "13654405000195",
    "resources": ["orgao", "unidades"],
    "observed_at": "2026-08-01",
    "discovery": "docs/reviews/STAGE_2_PNCP_DISCOVERY.md"
  }'::jsonb
)
on conflict (data_source_id, slug) do update
set
  base_url = excluded.base_url,
  rate_limit_per_minute = excluded.rate_limit_per_minute,
  request_timeout_seconds = excluded.request_timeout_seconds,
  enabled = excluded.enabled,
  config = excluded.config;

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
  '00000000-0000-4000-8000-000000000106',
  '00000000-0000-4000-8000-000000000005',
  'consulta-contratacoes',
  'api',
  'https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao',
  'GET',
  10,
  60,
  true,
  '{
    "cnpj": "13654405000195",
    "pagination": {"tamanhoPagina": 50, "total_fields": ["totalRegistros", "totalPaginas"]},
    "modalidades": "1-13",
    "observed_at": "2026-08-01",
    "timeout_note": "API degradada respondeu 200 em 31,5s em 01/08/2026"
  }'::jsonb
)
on conflict (data_source_id, slug) do update
set
  base_url = excluded.base_url,
  rate_limit_per_minute = excluded.rate_limit_per_minute,
  request_timeout_seconds = excluded.request_timeout_seconds,
  enabled = excluded.enabled,
  config = excluded.config;

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
  '00000000-0000-4000-8000-000000000107',
  '00000000-0000-4000-8000-000000000005',
  'compras-api',
  'api',
  'https://pncp.gov.br/api/pncp/v1/orgaos/13654405000195/compras/',
  'GET',
  30,
  60,
  true,
  '{
    "cnpj": "13654405000195",
    "resources": ["itens", "resultados", "contratos-empenhos"],
    "pagination": {"tamanhoPagina": 50, "raiz": "lista JSON"},
    "observed_at": "2026-08-01",
    "discovery": "docs/reviews/STAGE_2_PNCP_DISCOVERY.md"
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
