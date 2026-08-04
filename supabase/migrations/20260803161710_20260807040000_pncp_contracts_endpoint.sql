-- Endpoint pÃºblico do PNCP para contratos/empenhos vinculados a uma contrataÃ§Ã£o.
-- A coleta preserva o retorno bruto; a normalizaÃ§Ã£o financeira permanece em etapa
-- posterior, depois de validar o contrato observado em produÃ§Ã£o.

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
  'Portal Nacional de ContrataÃ§Ãµes PÃºblicas',
  'Cadastro, contrataÃ§Ãµes e contratos publicados por forÃ§a da Lei 14.133/2021.',
  'official',
  true,
  'https://pncp.gov.br/',
  'https://www.gov.br/pncp/pt-br/acesso-a-informacao/dados-abertos',
  'active'
)
on conflict (id) do update
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
  '00000000-0000-4000-8000-000000000112',
  '00000000-0000-4000-8000-000000000005',
  'contratos-api',
  'api',
  'https://pncp.gov.br/api/pncp/v1/orgaos/13654405000195/contratos/contratacao/',
  'GET',
  30,
  60,
  true,
  '{
    "cnpj": "13654405000195",
    "resource": "contratos-empenhos-de-contratacao",
    "retorno": "lista JSON",
    "observed_at": "2026-08-03",
    "documentation": "https://pncp.gov.br/manual/pt-br/latest/contrato_empenho/consultar_contratos_ou_empenhos_de_uma_contratacao.html"
  }'::jsonb
)
on conflict (data_source_id, slug) do update
set
  base_url = excluded.base_url,
  rate_limit_per_minute = excluded.rate_limit_per_minute,
  request_timeout_seconds = excluded.request_timeout_seconds,
  enabled = excluded.enabled,
  config = excluded.config;

;
